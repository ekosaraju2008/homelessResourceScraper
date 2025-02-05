import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration settings for the backend application"""

    # MongoDB Connection URI (stored in .env file for security)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/homeless_resources")

    # Flask Debug Mode (Set to False in production)
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

    # Secret Key (used for security, optional for authentication)
    SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")

