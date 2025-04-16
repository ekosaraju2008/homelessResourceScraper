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

    print(f"📥 Request received: type={resource_type}, lat={user_lat}, lon={user_lon}")

    # Fetch all resources of that type
    resources = get_resources(resource_type)
    print(f"📦 Total resources with '{resource_type}': {len(resources)}")

    if user_lat is not None and user_lon is not None:
        user_location = (user_lat, user_lon)
        filtered = []

        for r in resources:
            try:
                if "latitude" in r and "longitude" in r:
                    r["distance"] = calculate_distance(user_location, (r["latitude"], r["longitude"]))
                    if r["distance"] <= 50:  # Radius filter
                        filtered.append(r)
            except Exception as e:
                print(f"❌ Error for {r.get('site_name')}: {e}")

        resources = sorted(filtered, key=lambda x: x["distance"])
        print(f"✅ Found {len(resources)} nearby shelters:")
        for i, r in enumerate(resources[:5]):
            print(f"{i+1}. {r['site_name']} - {r['distance']:.2f} miles away")

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
