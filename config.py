import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24))

    # OpenAI Configuration
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

    # Database Configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')

    # File Upload Configuration
    UPLOAD_FOLDER = 'uploads'
    RESUME_FOLDER = os.path.join(UPLOAD_FOLDER, 'resumes')
    SCREENSHOT_FOLDER = os.path.join(UPLOAD_FOLDER, 'screenshots')