from flask import Flask
from flask_cors import CORS
from config.settings import Config
from routes.api_routes import api_bp
import os

# Debug: print startup info
print("📦 Booting Flask App...")
print("📦 MONGO_URI:", os.getenv("MONGO_URI"))

# Initialize Flask app
app = Flask(__name__)

# Enable CORS to allow frontend requests from different domains
CORS(app)

# Load configuration settings from settings.py
try:
    app.config.from_object(Config)
except Exception as e:
    print("❌ Error loading config:", e)

# Register API routes
app.register_blueprint(api_bp)

@app.route("/", methods=["GET"])
def home():
    """Health check route to confirm API is running."""
    return {"message": "Homeless Resource API is running!"}, 200

if __name__ == "__main__":
    # Heroku requires binding to 0.0.0.0 and $PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
