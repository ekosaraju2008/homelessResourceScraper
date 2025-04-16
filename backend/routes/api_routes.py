from flask import Blueprint, request, jsonify
from backend.services.database_service import get_resources
from backend.services.geolocation import calculate_distance
import os

# Define a Blueprint (modular routing)
api_bp = Blueprint('api', __name__)

@api_bp.route("/resources", methods=["GET"])
def fetch_resources():
    resource_type = request.args.get("type")
    user_lat = request.args.get("latitude", type=float)
    user_lon = request.args.get("longitude", type=float)

    print(f"📥 Request: type={resource_type}, lat={user_lat}, lon={user_lon}")

    # Fetch all resources matching the service type
    resources = get_resources(resource_type)
    print(f"📦 Total resources with '{resource_type}': {len(resources)}")

    # If no lat/lon, return all results for that type
    if user_lat is None or user_lon is None:
        return jsonify(resources)

    user_location = (user_lat, user_lon)
    nearby = []

    for r in resources:
        try:
            lat, lon = r.get("latitude"), r.get("longitude")
            if lat is not None and lon is not None:
                distance = calculate_distance(user_location, (lat, lon))
                r["distance"] = distance
                if distance <= 50:
                    nearby.append(r)
        except Exception as e:
            print(f"❌ Distance calc failed for {r.get('site_name')}: {e}")

    nearby = sorted(nearby, key=lambda x: x["distance"])
    print(f"✅ Found {len(nearby)} nearby resources within 50 miles")

    return jsonify(nearby)



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
