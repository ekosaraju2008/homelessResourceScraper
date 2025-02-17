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

# 🔧 Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='homeless_services_scraper.log'
)
logger = logging.getLogger(__name__)

# 🤖 Configure Google Gemini API
genai.configure(api_key='')
model = genai.GenerativeModel('gemini-1.5-flash')

# 🧠 Load SpaCy model for NER
try:
    nlp = spacy.load("en_core_web_lg")
except OSError:
    # Download the model if not installed
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_lg"])
    nlp = spacy.load("en_core_web_lg")

# 💾 Database connection with error handling
try:
    engine = create_engine('sqlite:///homeless_services.db')
    # Test connection
    with engine.connect() as conn:
        pass
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    engine = None

# 🔍 Compile regex patterns
phone_pattern = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
eligibility_pattern = re.compile(r'\b(must be \d+(?:\+| or older| years old)|\d+ years or older|veterans|women only|men only|families only|low-income|residents of|proof of|income below|qualifying|eligible|experiencing homelessness)\b', re.IGNORECASE)
pet_pattern = re.compile(r'\b(pets allowed|no pets|service animals|emotional support animals|pet friendly)\b', re.IGNORECASE)
address_pattern = re.compile(r'\b\d+\s+[A-Za-z\s]+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Route|Rt|Highway|Hwy|Circle|Cir|Court|Ct|Place|Pl|Way)[,.\s]+[A-Za-z\s]+,?\s*[A-Z]{2}\s*[-\s]*\d{5}\b', re.IGNORECASE)

# 🌐 Base URLs for shelter directory
STATE_URL = "https://www.homelessshelterdirectory.org/state/ohio"
BASE_URL = "https://www.homelessshelterdirectory.org"
MAX_ITERATIONS = 30

def clean_entity(text):
    """Clean and format entity text."""
    if not text:
        return None
        
    # Remove extra whitespace and newlines
    cleaned = re.sub(r'\s+', ' ', text.strip())
    
    # Remove common unwanted prefixes
    prefixes_to_remove = ['Address:', 'Name:', 'Website:', 'Phone:', 'Email:']
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    
    # Remove special characters but keep basic punctuation
    cleaned = re.sub(r'[^\w\s\-.,:#@()/]', '', cleaned)
    
    # Remove multiple periods or commas
    cleaned = re.sub(r'[.,]+', '.', cleaned)
    
    return cleaned.strip()

def extract_structured_data(soup):
    """Extract structured data from HTML metadata."""
    if not soup:
        return {}
        
    structured_data = {}
    
    # Try to find JSON-LD data
    json_ld = soup.find_all('script', type='application/ld+json')
    for script in json_ld:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            if isinstance(data, dict):
                structured_data.update(data)
        except (json.JSONDecodeError, AttributeError):
            continue
    
    # Try to find meta tags
    meta_mappings = {
        'og:title': 'name',
        'og:description': 'description',
        'og:url': 'url',
        'og:image': 'image'
    }
    
    for meta in soup.find_all('meta'):
        property = meta.get('property', '')
        content = meta.get('content', '')
        if property in meta_mappings and content:
            structured_data[meta_mappings[property]] = content
    
    # Try to find microdata
    for element in soup.find_all(attrs={'itemtype': True}):
        item_type = element['itemtype']
        if 'organization' in item_type.lower() or 'localbusiness' in item_type.lower():
            for prop in element.find_all(attrs={'itemprop': True}):
                structured_data[prop['itemprop']] = prop.get('content', prop.text.strip())
    
    return structured_data

def analyze_services(text_content, summary=None):
    """Extract services using Gemini AI, NER, and pattern matching for verification."""
    try:
        combined_text = f"{summary}\n\n{text_content}" if summary else text_content
        
        # First, get a detailed analysis from Gemini
        service_prompt = """
        Analyze this text and list ONLY the services that are explicitly mentioned as being provided by this organization. 
        The first paragraph is an AI-generated summary - use this as the primary source of truth.
        
        Focus on these specific categories:
        - food (meals, food pantry, soup kitchen)
        - shelter (housing, emergency shelter)
        - transportation
        - healthcare (medical services, health clinic)
        - mental health (counseling, therapy)
        - job support (employment assistance, job training)
        - sanitary supplies (hygiene kits, toiletries)
        - financial aid (utility assistance, rent assistance)

        Only include services that are clearly stated as being offered. Do not infer services.
        Format your response as a simple list of confirmed services, one per line.

        Text to analyze:
        {text}
        """
        
        response = model.generate_content(service_prompt.format(text=combined_text[:5000]))
        ai_services = [service.strip().lower() for service in response.text.split('\n') if service.strip()]
        
        # Use NER to verify AI-identified services
        doc = nlp(text_content[:1000000])
        
        # Define service-related keywords for verification
        service_keywords = {
            'food': ['food pantry', 'meals', 'soup kitchen', 'food bank', 'breakfast', 'lunch', 'dinner'],
            'shelter': ['shelter', 'housing', 'emergency shelter', 'temporary housing'],
            'transportation': ['transportation', 'bus', 'transit assistance'],
            'healthcare': ['medical', 'health clinic', 'healthcare', 'medical services'],
            'mental health': ['counseling', 'therapy', 'mental health', 'psychiatric'],
            'job support': ['employment', 'job training', 'career services', 'job placement'],
            'sanitary supplies': ['hygiene', 'toiletries', 'personal care'],
            'financial aid': ['financial assistance', 'utility assistance', 'rent assistance']
        }
        
        # Verify services using NER and pattern matching
        verified_services = set()
        
        for service in ai_services:
            # Check if the service appears in our keyword mappings
            for category, keywords in service_keywords.items():
                if any(keyword in service for keyword in keywords):
                    # Verify with NER entities
                    for ent in doc.ents:
                        if ent.label_ in ['ORG', 'PRODUCT', 'FAC']:
                            if any(keyword in ent.text.lower() for keyword in keywords):
                                verified_services.add(category)
                                break
                    
                    # Additional verification with regex patterns
                    service_text = text_content.lower()
                    # Look for service indicators like "we provide", "we offer", "available"
                    for keyword in keywords:
                        pattern = fr'\b(?:provide|offer|available|assist with|help with)[^.]*?{keyword}'
                        if re.search(pattern, service_text, re.I):
                            verified_services.add(category)
                            break
        
        return list(verified_services)
        
    except Exception as e:
        logger.error(f"Error analyzing services: {str(e)}")
        return []

def extract_contact_info(soup):
    """📞 Extract all contact information from page source."""
    contact_info = {
        'phone': None,
        'email': None,
        'twitter': None,
        'facebook': None,
        'instagram': None
    }
    
    # Look for phone numbers in any <a> tags with tel: links
    phone_links = soup.find_all('a', href=lambda x: x and 'tel:' in x)
    if phone_links:
        contact_info['phone'] = phone_links[0]['href'].replace('tel:', '')
    
    # Look for email addresses in any <a> tags with mailto: links
    email_links = soup.find_all('a', href=lambda x: x and 'mailto:' in x)
    if email_links:
        contact_info['email'] = email_links[0]['href'].replace('mailto:', '')
        
    # Look for social media links
    social_links = soup.find_all('a', href=True)
    for link in social_links:
        href = link['href'].lower()
        if 'twitter.com' in href:
            contact_info['twitter'] = href
        elif 'facebook.com' in href:
            contact_info['facebook'] = href
        elif 'instagram.com' in href:
            contact_info['instagram'] = href
            
    # Look for phone numbers in text content
    text_content = soup.get_text()
    phone_matches = phone_pattern.findall(text_content)
    if phone_matches and not contact_info['phone']:
        contact_info['phone'] = phone_matches[0]
        
    # Look for email addresses in text content
    email_matches = email_pattern.findall(text_content)
    if email_matches and not contact_info['email']:
        contact_info['email'] = email_matches[0]
        
    return contact_info

def get_city_links(state_url):
    """🏙️ Extract all city URLs from the state page."""
    city_links = []
    response = requests.get(state_url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        city_elements = soup.select("td a")
        
        for city in city_elements:
            link = city.get("href")
            if link and "/city/" in link:
                city_links.append(BASE_URL + link if not link.startswith("http") else link)
                logger.info(f"Found city link: {link}")
    
    return city_links

def get_shelter_urls(city_url):
    """🏠 Get shelter URLs for a given city URL."""
    shelter_urls = []
    
    try:
        response = requests.get(city_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            shelter_sections = soup.select("div.layout_post_2.clearfix")
            
            for section in shelter_sections:
                shelter_link = section.select_one("a.btn.btn_red")
                if shelter_link:
                    shelter_url = shelter_link["href"]
                    if not shelter_url.startswith("http"):
                        shelter_url = BASE_URL + shelter_url
                    
                    # Get the actual website URL from shelter page
                    website_link = get_shelter_website(shelter_url)
                    shelter_urls.append({
                        'directory_url': shelter_url,
                        'website': website_link  # Can be None if no website found
                    })
                    logger.info(f"Added shelter URL: {shelter_url}")
                    
        logger.info(f"Retrieved {len(shelter_urls)} shelter URLs from {city_url}")
        return shelter_urls

    except Exception as e:
        logger.error(f"Error getting shelter URLs from {city_url}: {str(e)}")
        return []

def get_shelter_website(shelter_url):
    """🔗 Extract official website link from shelter directory page."""
    try:
        response = requests.get(shelter_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            website_link = soup.select_one("a.btn[href^='http']")
            
            if website_link:
                return website_link['href']
                
    except Exception as e:
        logger.error(f"Error extracting website from {shelter_url}: {str(e)}")
    return None

def extract_and_format_schedules(text_content):
    """Extract and format schedules from text using both regex and AI."""
    try:
        # First try to extract structured schedules
        schedules = {}
        
        # Common schedule patterns
        patterns = [
            (r'(?:soup\s+kitchen|meals?)[^.]*?(?:M-F|Mon(?:day)?-Fri(?:day)?)[^.]*?(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.))?)\s*(?:-|to|through)\s*(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.)))', 'Soup Kitchen'),
            (r'(?:food\s+pantry)[^.]*?(?:M-F|Mon(?:day)?-Fri(?:day)?)[^.]*?(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.))?)\s*(?:-|to|through)\s*(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.)))', 'Food Pantry'),
            (r'(?:shelter|housing)[^.]*?(?:M-F|Mon(?:day)?-Fri(?:day)?)[^.]*?(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.))?)\s*(?:-|to|through)\s*(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|a\.m\.|p\.m\.)))', 'Shelter Hours')
        ]
        
        # Extract schedules using patterns
        for pattern, service_type in patterns:
            matches = re.finditer(pattern, text_content, re.I | re.DOTALL)
            for match in matches:
                if service_type not in schedules:
                    schedules[service_type] = []
                schedules[service_type].append({
                    'days': 'Monday-Friday',  # Default for M-F
                    'time': f"{match.group(1)} - {match.group(2)}"
                })

        # Use Gemini to extract and structure any remaining schedule information
        prompt = """
        Please analyze this text and extract any schedule or timing information. Format the output as a structured list of services and their schedules. Only include services that have specific times mentioned.

        For example:
        Soup Kitchen:
        - Days: Monday-Friday
        - Time: 4:30 PM - 5:30 PM

        Food Pantry:
        - Days: Monday-Friday
        - Time: 1:00 PM - 3:00 PM

        Text to analyze:
        {text}
        """
        
        response = model.generate_content(prompt.format(text=text_content[:5000]))
        ai_schedules = response.text.strip()
        
        # Combine regex-found schedules with AI-parsed schedules
        formatted_schedules = []
        
        # Add regex-found schedules
        for service_type, schedule_list in schedules.items():
            formatted_schedules.append(f"\n{service_type}:")
            for schedule in schedule_list:
                formatted_schedules.append(f"Days: {schedule['days']}")
                formatted_schedules.append(f"Time: {schedule['time']}")
        
        # Add AI-parsed schedules (if they don't overlap with regex-found ones)
        if ai_schedules and ai_schedules != "No specific schedules found.":
            for line in ai_schedules.split('\n'):
                if line.strip() and not any(service in line for service in schedules.keys()):
                    formatted_schedules.append(line)
        
        return formatted_schedules if formatted_schedules else ["No specific schedules found."]
        
    except Exception as e:
        logger.error(f"Error extracting schedules: {str(e)}")
        return ["Error extracting schedule information."]

def scrape_service_data(shelter_info):
    """📝 Scrape data from both directory page and official website."""
    try:
        directory_url = shelter_info['directory_url']
        website_url = shelter_info['website']
        
        # Add random delay
        time.sleep(random.uniform(2, 5))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        # First get data from directory page
        dir_response = requests.get(directory_url, headers=headers, timeout=30)
        dir_soup = BeautifulSoup(dir_response.text, 'html.parser')
        
        # Initialize web_soup as None
        web_soup = None
        
        # Only try to get website data if website_url exists
        if website_url:
            try:
                web_response = requests.get(website_url, headers=headers, timeout=30)
                web_soup = BeautifulSoup(web_response.text, 'html.parser')
            except Exception as e:
                logger.warning(f"Could not fetch website {website_url}: {str(e)}")
        
        # Extract contact info from both sources if available
        dir_contacts = extract_contact_info(dir_soup)
        web_contacts = extract_contact_info(web_soup) if web_soup else {'phone': None, 'email': None, 'twitter': None, 'facebook': None, 'instagram': None}
        
        # Merge contact info, preferring directory info
        contact_info = {
            'phone': dir_contacts['phone'] or web_contacts['phone'],
            'email': dir_contacts['email'] or web_contacts['email'],
            'twitter': dir_contacts['twitter'] or web_contacts['twitter'],
            'facebook': dir_contacts['facebook'] or web_contacts['facebook'],
            'instagram': dir_contacts['instagram'] or web_contacts['instagram']
        }
        
        # Combine text content from both sources
        text_content = dir_soup.get_text()
        if web_soup:
            text_content += " " + web_soup.get_text()
            
        # Get AI summary first
        try:
            summary_prompt = """
            Please provide a detailed 3-4 sentence summary of this homeless shelter.
            Focus on what specific services they provide and any key eligibility requirements.
            Only include information that is explicitly stated in the text.

            Text to analyze:
            {text}
            """
            
            response = model.generate_content(summary_prompt.format(text=text_content[:5000]))
            summary = response.text if response.text else None
        except Exception as e:
            logger.error(f"Error getting summary: {str(e)}")
            summary = None

        # Now use the summary along with the full text to verify services
        verified_services = analyze_services(text_content, summary)
        
        # Initialize entities dictionary
        entities = {}
        
        # Get structured data from both sources
        dir_structured = extract_structured_data(dir_soup)
        web_structured = extract_structured_data(web_soup) if web_soup else {}
        
        # Look for site name in entry title first
        entry_title = dir_soup.select_one("h1.entry_title")
        if entry_title:
            entities['site_name'] = clean_entity(entry_title.text)
        # Fallback to structured data if no entry title
        elif dir_structured.get('name') or web_structured.get('name'):
            entities['site_name'] = clean_entity(dir_structured.get('name') or web_structured.get('name'))
            
        entities['official_website'] = website_url
        entities['directory_url'] = directory_url
        
        if any(contact_info.values()):
            entities['contact_info'] = [contact_info]
            
        # Update entities with verified services
        if verified_services:
            entities['service_types'] = verified_services
        
        pet_policies = list(set(pet_pattern.findall(text_content)))
        if pet_policies:
            entities['pet_policy'] = pet_policies
        
        # Process eligibility requirements
        eligibility_reqs = []
        for e in set(eligibility_pattern.findall(text_content)):
            if 'veterans' in e.lower():
                eligibility_reqs.append("Requirements: Veterans only")
            elif 'women only' in e.lower():
                eligibility_reqs.append("Requirements: Women only")
            elif 'men only' in e.lower():
                eligibility_reqs.append("Requirements: Men only")
            elif 'families only' in e.lower():
                eligibility_reqs.append("Requirements: Families only")
            elif 'low-income' in e.lower():
                eligibility_reqs.append("Requirements: Low income")
            elif any(age in e.lower() for age in ['18+', '21+', 'years old', 'or older']):
                age = re.search(r'\d+', e)
                if age:
                    eligibility_reqs.append(f"Requirements: {age.group()}+")
        
        if eligibility_reqs:
            entities['eligibility'] = eligibility_reqs
                
        # Extract address from directory page HTML structure
        addresses = []
        address_element = dir_soup.select_one("p strong:contains('Address')")
        if address_element:
            address_text = address_element.find_parent('p').get_text(separator='\n', strip=True)
            addresses.append(clean_entity(address_text.replace('Address', '')))
        else:
            # Fallback to regex pattern if structured address not found
            regex_addresses = address_pattern.findall(text_content)
            if regex_addresses:
                addresses.extend([clean_entity(addr) for addr in regex_addresses])
            else:
                # Last resort: use NER
                doc = nlp(text_content[:1000000])
                seen_addresses = set()
                for ent in doc.ents:
                    if ent.label_ == 'GPE':
                        clean_addr = clean_entity(ent.text)
                        if clean_addr not in seen_addresses:
                            addresses.append(clean_addr)
                            seen_addresses.add(clean_addr)
                            
        if addresses:
            entities['addresses'] = addresses

        # Extract and format schedules
        formatted_schedules = extract_and_format_schedules(text_content)
        
        if formatted_schedules:
            entities['times'] = formatted_schedules
        
        if summary:
            entities['summary'] = summary
                
        print(f"\n🏠 Extracted data for {entities.get('site_name', 'Unknown Site')}")
        pprint(entities)
        return entities
        
    except Exception as e:
        logger.error(f"Error scraping service data: {str(e)}")
        return None

def process_cities(batch_size=10):
    """🌆 Process Ohio cities and extract shelter information."""
    all_services = []
    processed_count = 0
    
    print("\n" + "="*50)
    print("🔍 Starting Ohio Shelter Directory Scan")
    print("="*50 + "\n")
    
    city_links = get_city_links(STATE_URL)
    
    for city_url in city_links[:MAX_ITERATIONS]:
        try:
            city = city_url.split('/')[-1].replace('-', ' ').title()
            print(f"\n🏙️ Processing: {city}, OH")
            print("-"*30)
            
            time.sleep(random.uniform(2, 5))
            
            shelter_urls = get_shelter_urls(city_url)
            
            for shelter in shelter_urls:
                try:
                    service_data = scrape_service_data(shelter)
                    if service_data:
                        service_data['city'] = city
                        service_data['state'] = 'OH'
                        all_services.append(service_data)
                        
                        site_name = service_data.get('site_name', 'Unknown Site')
                        print(f"✅ Successfully scraped: {site_name}")
                        
                        # Export to CSV after each successful scrape
                        df = pd.DataFrame(all_services)
                        df.to_csv('ohio_shelters_live.csv', index=False)
                        print(f"💾 Updated CSV with {len(all_services)} records")
                            
                except Exception as e:
                    logger.error(f"❌ Error processing shelter: {str(e)}")
                    continue
                    
            processed_count += 1
            if processed_count >= MAX_ITERATIONS:
                break
                
        except Exception as e:
            logger.error(f"❌ Error processing {city}: {str(e)}")
            continue
    
    # Final CSV export
    if all_services:
        final_df = pd.DataFrame(all_services)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_filename = f'ohio_shelters_final_{timestamp}.csv'
        final_df.to_csv(final_filename, index=False)
        print(f"\n📊 Statistics:")
        print(f"   - Total shelters processed: {len(final_df)}")
        print(f"   - Data saved to: {final_filename}")
    
    return all_services

def save_to_database(services):
    """💾 Save scraped services to database and CSV."""
    if not services:
        return
        
    try:
        # Convert to DataFrame
        df = pd.DataFrame(services)
        
        # Save to CSV (as backup)
        df.to_csv('ohio_shelters_backup.csv', mode='a', header=False, index=False)
        
        if engine:
            # Convert lists and dicts to strings for SQLite
            for col in df.columns:
                df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
            
            # Save to SQLite database
            df.to_sql('shelters', engine, if_exists='append', index=False)
            print(f"✅ Saved {len(services)} records to database")
        else:
            print("⚠️ Database connection not available, saved to CSV only")
            
    except Exception as e:
        print(f"❌ Error saving to database: {str(e)}")
        # Save to error log file as backup
        with open('failed_saves.json', 'a') as f:
            json.dump(services, f)
            f.write('\n')

if __name__ == "__main__":
    try:
        print("\n" + "="*50)
        print("🏠 Ohio Homeless Shelter Directory Scraper")
        print("="*50 + "\n")
        
        results = process_cities()
        
        print("\n" + "="*50)
        print(f"🎉 Success! Processed {len(results)} shelters")
        print("="*50)
        
    except Exception as e:
        logger.error(f"❌ Main execution error: {str(e)}")
