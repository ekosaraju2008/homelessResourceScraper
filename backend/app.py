from flask import Flask
from flask_cors import CORS
from config.settings import Config
from routes.api_routes import api_bp

# Initialize Flask app
app = Flask(__name__)

# Enable CORS to allow frontend requests from different domains
CORS(app)

# Load configuration settings from settings.py
app.config.from_object(Config)

# Register API routes
app.register_blueprint(api_bp)

@app.route("/", methods=["GET"])
def home():
    """Health check route to confirm API is running."""
    return {"message": "Homeless Resource API is running!"}, 200

if __name__ == "__main__":
    # Start the Flask app
    app.run(debug=Config.DEBUG)
