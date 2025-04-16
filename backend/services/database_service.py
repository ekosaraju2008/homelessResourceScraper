from pymongo import MongoClient
from backend.config.settings import Config 

# Connect to MongoDB Atlas
client = MongoClient(Config.MONGO_URI)
db = client.homeless_resources  # Database name
resources_collection = db.resources  # Collection name

def get_resources(resource_type=None):
    """
    Fetch resources from MongoDB based on service type.
    If no type is provided, fetch all resources.

    :param resource_type: (str) "shelter", "food", etc.
    :return: List of matching resources (as dictionaries)
    """
    query = {"services": {"$in": [resource_type]}} if resource_type else {}
    return list(resources_collection.find(query, {"_id": 0}))
