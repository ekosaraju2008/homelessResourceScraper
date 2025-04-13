from flask import Flask
from flask_cors import CORS
import os

# Debug: Show that app is attempting to start
print("🔥 STARTING: backend.app.py")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Try loading config
try:
    from backend.config.settings import Config
    app.config.from_object(Config)
    print("✅ Loaded config successfully")
except Exception as e:
    print("❌ Failed to load config:", e)

# Try loading routes
try:
    from backend.routes.api_routes import api_bp
    app.register_blueprint(api_bp)
    print("✅ Registered API routes successfully")
except Exception as e:
    print("❌ Failed to register routes:", e)

@app.route("/", methods=["GET"])
def home():
    return {"message": "Homeless Resource API is running!"}, 200

# Heroku-safe launch
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
