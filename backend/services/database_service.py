from pymongo import MongoClient
from backend.config.settings import Config
import re

# Connect to MongoDB Atlas
client = MongoClient(Config.MONGO_URI)
db = client.homeless_resources
resources_collection = db.resources

def get_resources(resource_type=None):
    """
    Fetch resources from MongoDB based on type.
    If no type is provided, fetch all resources.
    :param resource_type: (str) e.g., "shelter", "food", etc.
    :return: List of matching resources
    """
    if resource_type:
        # Match substring inside the stringified list
        regex = re.compile(rf"\b{re.escape(resource_type)}\b", re.IGNORECASE)
        query = {"services": regex}
    else:
        query = {}

    return list(resources_collection.find(query, {"_id": 0}))
