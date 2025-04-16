from pymongo import MongoClient
from backend.config.settings import Config
import re

# Connect to MongoDB Atlas
client = MongoClient(Config.MONGO_URI)
db = client.homeless_resources
resources_collection = db.resources

def get_resources(resource_type=None):
    """
    Fetch resources from MongoDB based on service type.
    """
    query = {"services": resource_type} if resource_type else {}
    return list(resources_collection.find(query, {"_id": 0}))
