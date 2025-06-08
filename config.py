import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration."""
    # Used for session security, CSRF protection, etc.
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24))

    # OpenAI Configuration
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

    # Database Configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')

    # Email Configuration
    # IMPORTANT: Update these values in your .env file
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'True').lower() in ['true', '1', 't']
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').lower() in ['true', '1', 't']

    # The email address that will send the emails
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')

    # The password for the email account.
    # For Gmail, this MUST be a 16-character "App Password", not your regular password.
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    # File Upload Configuration
    UPLOAD_FOLDER = 'uploads'
    RESUME_FOLDER = os.path.join(UPLOAD_FOLDER, 'resumes')
    SCREENSHOT_FOLDER = os.path.join(UPLOAD_FOLDER, 'screenshots')

