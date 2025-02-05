import json
from pymongo import MongoClient
from config.settings import Config

# Connect to MongoDB Atlas
client = MongoClient(Config.MONGO_URI)
db = client.homeless_resources  # Database name
resources_collection = db.resources  # Collection name

def initialize_db():
    """
    Load sample data into MongoDB.
    Ensures the 'resources' collection exists and has data.
    """
    # Check if the collection is empty
    if resources_collection.count_documents({}) == 0:
        with open("database/seed_data.json") as f:
            data = json.load(f)
            resources_collection.insert_many(data)
            print("Database initialized with sample resources.")
    else:
        print("Database already contains data. Skipping initialization.")

if __name__ == "__main__":
    initialize_db()
