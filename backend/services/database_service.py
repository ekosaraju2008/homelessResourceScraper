from pymongo import MongoClient
from backend.config.settings import Config
import re

# Connect to MongoDB Atlas
client = MongoClient(Config.MONGO_URI)
db = client.homeless_resources
resources_collection = db.resources

def get_resources(resource_type=None):
    query = {"services": resource_type} if resource_type else {}
    print(f"📡 MongoDB Query: {query}")
    result = list(resources_collection.find(query, {"_id": 0}))
    print(f"📄 Result count: {len(result)}")
    return result
