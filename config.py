import os
from google.cloud import secretmanager

# Load environment variables for local development from .env file
from dotenv import load_dotenv

load_dotenv()

# --- GCP Configuration ---
# Your Google Cloud Project ID
PROJECT_ID = os.environ.get('GCP_PROJECT')


def get_secret(secret_id, project_id=PROJECT_ID):
    """Fetches a secret from Google Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(name=name)
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        # Fallback for local development or if secret is not found
        print(f"Could not fetch secret {secret_id}. Trying environment variable. Error: {e}")
        return os.environ.get(secret_id)


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24))

    # In production, get secrets from Secret Manager
    # In local development, it will fall back to the .env file
    OPENAI_API_KEY = get_secret('OPENAI_API_KEY')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')  # Read directly from environment variable

    # Database Configuration - for Cloud SQL
    DB_USER = os.environ.get('DB_USER')
    DB_NAME = os.environ.get('DB_NAME')

    # The DB_HOST is set via an environment variable in Cloud Run
    # For local dev, it would be 'localhost'
    DB_HOST = os.environ.get('DB_HOST', 'localhost')

    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = get_secret('MAIL_PASSWORD')

    # File Upload Configuration (will be updated for Cloud Storage later)
    UPLOAD_FOLDER = 'uploads'
    RESUME_FOLDER = os.path.join(UPLOAD_FOLDER, 'resumes')
    SCREENSHOT_FOLDER = os.path.join(UPLOAD_FOLDER, 'screenshots')
