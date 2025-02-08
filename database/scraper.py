import pandas as pd
import requests
from bs4 import BeautifulSoup
import spacy
from sqlalchemy import create_engine
import time
import random
import json
import logging
import re
from urllib.parse import urlparse
from datetime import datetime
from pprint import pprint
import google.generativeai as genai

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='homeless_services_scraper.log'
)
logger = logging.getLogger(__name__)

# Configure Google Gemini API
genai.configure(api_key='AIzaSyBOaVvyuqnPOg4II9zF3oPjN8J0x8O16AM')
model = genai.GenerativeModel('gemini-1.5-flash')

# Load SpaCy model for NER
try:
    nlp = spacy.load("en_core_web_lg")
except OSError:
    # Download the model if not installed
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_lg"])
    nlp = spacy.load("en_core_web_lg")

# Database connection with error handling
try:
    engine = create_engine('sqlite:///homeless_services.db')
    # Test connection
    with engine.connect() as conn:
        pass
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    engine = None

# Compile regex patterns
phone_pattern = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
service_pattern = re.compile(r'\b(emergency shelter|food assistance|mental health|job training|substance abuse|counseling|housing|meals|therapy|rehabilitation|employment|treatment)\b', re.IGNORECASE)
eligibility_pattern = re.compile(r'\b(must be \d+(?:\+| or older| years old)|\d+ years or older|veterans|women only|men only|families only|low-income|residents of|proof of|income below|qualifying|eligible|experiencing homelessness)\b', re.IGNORECASE)

def clean_entity(text):
    """Clean and normalize extracted entity text."""
    if not isinstance(text, str):
        text = str(text)
    return ' '.join(text.split()).strip()

def extract_structured_data(soup):
    """Extract structured data from Schema.org markup if available."""
    structured_data = {}
    schema_tags = soup.find_all('script', type='application/ld+json')
    
    for tag in schema_tags:
        try:
            if not tag.string:
                continue
            data = json.loads(tag.string)
            if isinstance(data, dict):
                if data.get('@type') in ['LocalBusiness', 'Organization', 'NGO']:
                    structured_data['name'] = data.get('name')
                    structured_data['address'] = data.get('address')
                    structured_data['telephone'] = data.get('telephone')
                    structured_data['openingHours'] = data.get('openingHours')
                    structured_data['description'] = data.get('description')
                    structured_data['serviceType'] = data.get('serviceType')
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Error parsing structured data: {str(e)}")
            continue
            
    return structured_data

def merge_entity_data(ner_entities, structured_data):
    """Merge NER extracted entities with structured data."""
    if structured_data.get('name'):
        ner_entities['site_name'] = clean_entity(structured_data['name'])
    if structured_data.get('address'):
        ner_entities['addresses'].append(clean_entity(str(structured_data['address'])))
    if structured_data.get('telephone'):
        phone = clean_entity(structured_data['telephone'])
        if len(ner_entities['contact_info']) > 0:
            ner_entities['contact_info'][0]['phone'] = phone
        else:
            ner_entities['contact_info'].append({'phone': phone, 'email': None})
    if structured_data.get('openingHours'):
        hours = structured_data['openingHours']
        if isinstance(hours, list):
            formatted_hours = "Times Open: " + ", ".join(hours)
        else:
            formatted_hours = f"Times Open: {hours}"
        ner_entities['times'].append(clean_entity(formatted_hours))

    # Map structured data to service categories
    if structured_data.get('description'):
        desc = structured_data['description']
        service_matches = service_pattern.findall(desc)
        ner_entities['service_types'].extend([s.title() for s in service_matches])
        
        # Extract eligibility from description
        eligibility_matches = eligibility_pattern.findall(desc)
        if eligibility_matches:
            for e in eligibility_matches:
                if 'experiencing homelessness' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Experiencing homelessness")
                elif 'veterans' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Veterans only")
                elif 'women only' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Women only") 
                elif 'men only' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Men only")
                elif 'families only' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Families only")
                elif 'low-income' in e.lower():
                    ner_entities['eligibility'].append("Requirements: Low income")
                elif any(age in e.lower() for age in ['18+', '21+', 'years old', 'or older']):
                    age = re.search(r'\d+', e).group()
                    ner_entities['eligibility'].append(f"Requirements: {age}+")
            
    if structured_data.get('serviceType'):
        service_type = structured_data['serviceType']
        if isinstance(service_type, list):
            ner_entities['service_types'].extend([s.title() for s in service_type])
        else:
            ner_entities['service_types'].append(service_type.title())
            
    return ner_entities

def get_service_urls(city, state):
    """Get service URLs for a given city and state."""
    # Example URLs for testing - replace with actual URL gathering logic
    test_urls = {
        ("Cleveland", "OH"): [
            "https://www.lutheranmetro.org/",
            "https://www.neoch.org/",
            "https://www.frontlineservice.org/"
        ],
        ("Chicago", "IL"): [
            "https://www.chicagohomeless.org/", 
            "https://www.pacificgarden.org/"
        ],
        ("Los Angeles", "CA"): [
            "https://www.lahsa.org/",
            "https://www.midnightmission.org/",
            "https://www.unionrescuemission.org/"
        ],
        ("New York", "NY"): [
            "https://www.bowery.org/",
            "https://www.coalitionforthehomeless.org/",
            "https://www.helpusa.org/"
        ],
        ("Dallas", "TX"): [
            "https://www.austinstreet.org/",
            "https://www.dallaslife.org/",
            "https://www.vogeldallas.org/"
        ]
    }
    return test_urls.get((city, state), [])

def scrape_service_data(url):
    """Scrape data from a service provider website and extract entities."""
    try:
        if not url or not isinstance(url, str):
            logger.error("Invalid URL provided")
            return None
            
        # Add random delay with exponential backoff
        time.sleep(random.uniform(2, 5))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract structured data if available
        structured_data = extract_structured_data(soup)
        
        # Get all text content
        text_content = soup.get_text(separator=' ', strip=True)
        
        # Get summary using Gemini
        try:
            response = model.generate_content(
                f"Please provide a concise summary of this organization and the services they provide, based on the following content:\n\n{text_content[:5000]}"
            )
            summary = response.text if response.text else None
        except Exception as e:
            logger.error(f"Error getting summary: {str(e)}")
            summary = None
        
        # Perform NER
        doc = nlp(text_content[:1000000])  # Limit text length to prevent memory issues
        
        # Initialize entities dictionary
        entities = {
            'locations': [],
            'times': [],
            'contact_info': [],
            'service_types': [],
            'eligibility': [],
            'addresses': [],
            'site_name': '',
            'summary': summary
        }
        
        # Try to get site name from meta tag
        og_site_name = soup.find('meta', property='og:site_name')
        if og_site_name and og_site_name.get('content'):
            entities['site_name'] = clean_entity(og_site_name['content'])
        
        # Extract entities with confidence scores
        seen_locations = set()
        for ent in doc.ents:
            confidence = ent.label_ if hasattr(ent._, 'confidence') else 1.0
            if confidence < 0.5:
                continue
                
            if ent.label_ in ['GPE', 'LOC', 'FAC']:
                # Normalize location name and check if we've seen it
                norm_location = clean_entity(ent.text).lower()
                if norm_location not in seen_locations:
                    entities['locations'].append(clean_entity(ent.text))
                    seen_locations.add(norm_location)
            elif ent.label_ in ['TIME', 'DATE']:
                time_text = clean_entity(ent.text)
                if any(day in time_text.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                    entities['times'].append(f"Times Open: {time_text}")

        # Extract service types using regex
        service_matches = service_pattern.findall(text_content)
        entities['service_types'].extend([s.title() for s in service_matches])

        # Extract eligibility requirements
        eligibility_matches = eligibility_pattern.findall(text_content)
        if eligibility_matches:
            for e in eligibility_matches:
                if 'experiencing homelessness' in e.lower():
                    entities['eligibility'].append("Requirements: Experiencing homelessness")
                elif 'veterans' in e.lower():
                    entities['eligibility'].append("Requirements: Veterans only")
                elif 'women only' in e.lower():
                    entities['eligibility'].append("Requirements: Women only")
                elif 'men only' in e.lower():
                    entities['eligibility'].append("Requirements: Men only")
                elif 'families only' in e.lower():
                    entities['eligibility'].append("Requirements: Families only")
                elif 'low-income' in e.lower():
                    entities['eligibility'].append("Requirements: Low income")
                elif any(age in e.lower() for age in ['18+', '21+', 'years old', 'or older']):
                    age = re.search(r'\d+', e).group()
                    entities['eligibility'].append(f"Requirements: {age}+")

        # Use SpaCy to identify service-related phrases and eligibility
        for sent in doc.sents:
            # Service types
            if any(token.text.lower() in ['provide', 'offer', 'service', 'program', 'assistance'] for token in sent):
                for chunk in sent.noun_chunks:
                    if any(service_term in chunk.text.lower() for service_term in ['shelter', 'food', 'health', 'counseling', 'training']):
                        entities['service_types'].append(clean_entity(chunk.text).title())
            
            # Eligibility requirements
            if any(token.text.lower() in ['eligible', 'qualify', 'requirement', 'must', 'need', 'restricted'] for token in sent):
                sent_text = sent.text.strip()
                if any(term in sent_text.lower() for term in ['age', 'year', 'old', 'veteran', 'income', 'resident', 'family', 'woman', 'man']):
                    if 'veterans' in sent_text.lower():
                        entities['eligibility'].append("Requirements: Veterans only")
                    elif 'women only' in sent_text.lower():
                        entities['eligibility'].append("Requirements: Women only")
                    elif 'men only' in sent_text.lower():
                        entities['eligibility'].append("Requirements: Men only")
                    elif 'families only' in sent_text.lower():
                        entities['eligibility'].append("Requirements: Families only")
                    elif 'low-income' in sent_text.lower():
                        entities['eligibility'].append("Requirements: Low income")
                    elif any(age in sent_text.lower() for age in ['18+', '21+', 'years old', 'or older']):
                        age = re.search(r'\d+', sent_text).group()
                        entities['eligibility'].append(f"Requirements: {age}+")
        
        # Extract phone numbers and emails using regex and combine into contact_info
        phones = phone_pattern.findall(text_content)
        emails = email_pattern.findall(text_content)
        
        if phones or emails:
            entities['contact_info'].append({
                'phone': phones[0] if phones else None,
                'email': emails[0] if emails else None
            })
        
        # If no site name from meta tag, get from URL
        if not entities['site_name']:
            parsed_url = urlparse(url)
            site_name = parsed_url.netloc.replace('www.', '')
            entities['site_name'] = site_name
        
        # Merge with structured data
        if structured_data:
            entities = merge_entity_data(entities, structured_data)
        
        # Remove duplicates and clean up
        for key in entities:
            if isinstance(entities[key], list) and key != 'contact_info':
                entities[key] = list(set(entities[key]))
        
        print("\nExtracted entities from", url)
        # Only print non-empty fields and eligibility if it exists
        filtered_entities = {k:v for k,v in entities.items() if v and (k != 'eligibility' or len(v) > 0)}
        pprint(filtered_entities)
        return entities
        
    except requests.RequestException as e:
        logger.error(f"Request error for {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return None

def process_cities(cities_df, batch_size=10):
    """Process multiple cities and extract service information."""
    if engine is None:
        logger.error("Database connection not available")
        return pd.DataFrame()
        
    if not isinstance(cities_df, pd.DataFrame):
        logger.error("Invalid input: cities_df must be a pandas DataFrame")
        return pd.DataFrame()
        
    if 'city' not in cities_df.columns or 'state' not in cities_df.columns:
        logger.error("Required columns 'city' and 'state' not found in DataFrame")
        return pd.DataFrame()
    
    all_services = []
    
    for idx, row in cities_df.iterrows():
        try:
            city = row['city']
            state = row['state']
            logger.info(f"Processing {city}, {state}")
            
            search_urls = get_service_urls(city, state)
            
            for url in search_urls:
                try:
                    service_data = scrape_service_data(url)
                    if service_data:
                        service_data.update({
                            'city': city,
                            'state': state,
                            'source_url': url
                        })
                        all_services.append(service_data)
                        
                        # Batch processing to database
                        if len(all_services) >= batch_size:
                            save_to_database(all_services)
                            all_services = []
                            
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error processing {city}, {state}: {str(e)}")
            continue
    
    # Save any remaining services
    if all_services:
        save_to_database(all_services)
    
    return get_all_services()

def save_to_database(services):
    """Save services to database with error handling."""
    if not services or not engine:
        return
        
    try:
        services_df = pd.DataFrame(services)
        services_df.to_sql('services', engine, if_exists='append', index=False)
        logger.info(f"Successfully saved {len(services)} services to database")
    except Exception as e:
        logger.error(f"Error saving to database: {str(e)}")

def get_all_services():
    """Retrieve all services from database."""
    if not engine:
        return pd.DataFrame()
    try:
        services_df = pd.read_sql('SELECT * FROM services', engine)
        print("\nAll services from database:")
        print(services_df)
        return services_df
    except Exception as e:
        logger.error(f"Error retrieving services: {str(e)}")
        return pd.DataFrame()

# Example usage
if __name__ == "__main__":
    try:
        cities_df = pd.read_csv('cities.csv')
        results = process_cities(cities_df)
        logger.info(f"Successfully processed {len(results)} total services")
    except Exception as e:
        logger.error(f"Main execution error: {str(e)}")
