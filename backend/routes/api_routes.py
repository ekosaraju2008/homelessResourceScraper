from flask import Blueprint, request, jsonify
from backend.services.database_service import get_resources
from backend.services.geolocation import calculate_distance
import os

# Define a Blueprint (modular routing)
api_bp = Blueprint('api', __name__)

@api_bp.route("/resources", methods=["GET"])
def fetch_resources():
    """
    Fetch shelters, food banks, or other resources based on:
      - type (shelter, food, medical)
      - optional user location (latitude & longitude)
    
    Example Request:
      GET /resources?type=shelter&latitude=40.7128&longitude=-74.0060

    Returns:
      JSON list of matching resources (sorted by proximity if location provided)
    """
    resource_type = request.args.get("type")
    user_lat = request.args.get("latitude", type=float)
    user_lon = request.args.get("longitude", type=float)

    # Fetch matching resources from MongoDB
    resources = get_resources(resource_type)

    # If user provided location, calculate distances and sort results
    if user_lat and user_lon:
        for resource in resources:
            resource["distance"] = calculate_distance(
                (user_lat, user_lon), 
                (resource["latitude"], resource["longitude"])
            )
        # Sort resources by closest distance
        resources = sorted(resources, key=lambda x: x["distance"])

    return jsonify(resources)

@api_bp.route("/health", methods=["GET"])
def health_check():
    """Simple endpoint to check if the API is running"""
    return jsonify({"status": "API is running"}), 200

@api_bp.route("/test-env", methods=["GET"])
def test_env():
    """Check if the MONGO_URI environment variable is accessible"""
    mongo_uri = os.getenv("MONGO_URI")
    return jsonify({
        "MONGO_URI": mongo_uri if mongo_uri else "❌ Not found"
    })
