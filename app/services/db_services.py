import mysql.connector
from flask import current_app
import datetime
import uuid
import os
import json


def get_db_connection():
    """
    Establishes a connection to the database, handling both local and Cloud SQL environments.
    This function is "cloud-aware".
    """
    try:
        # Try to get config from current_app first, fallback to environment variables
        try:
            db_host = current_app.config.get('DB_HOST') if current_app else os.environ.get('DB_HOST', 'localhost')
            db_user = current_app.config.get('DB_USER') if current_app else os.environ.get('DB_USER')
            db_password = current_app.config.get('DB_PASSWORD') if current_app else os.environ.get('DB_PASSWORD')
            db_name = current_app.config.get('DB_NAME') if current_app else os.environ.get('DB_NAME')
        except RuntimeError:
            # current_app is not available, use environment variables
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            db_name = os.environ.get('DB_NAME')

        # Check if the DB_HOST environment variable is set and looks like a Cloud SQL socket path
        if db_host and db_host.startswith('/cloudsql/'):
            # Use the Unix socket for a secure, direct connection within Google Cloud
            conn_config = {
                'unix_socket': db_host,
                'user': db_user,
                'password': db_password,
                'database': db_name
            }
        else:
            # Fallback to standard TCP connection for local development
            conn_config = {
                'host': db_host,
                'user': db_user,
                'password': db_password,
                'database': db_name
            }

        # Log the connection attempt (without password)
        if current_app:
            current_app.logger.info(f"Attempting database connection to {conn_config.get('host', conn_config.get('unix_socket', 'unknown'))} with user {conn_config['user']}")
        
        conn = mysql.connector.connect(**conn_config)
        
        if current_app:
            current_app.logger.info("Database connection successful")
        return conn
    except mysql.connector.Error as err:
        if current_app:
            current_app.logger.error(f"Error connecting to MySQL: {err}")
            current_app.logger.error(f"Connection config (without password): host={conn_config.get('host', conn_config.get('unix_socket', 'unknown'))}, user={conn_config['user']}, database={conn_config['database']}")
        else:
            print(f"Error connecting to MySQL: {err}")
        return None
    except Exception as e:
        if current_app:
            current_app.logger.error(f"Unexpected error in database connection: {e}")
        else:
            print(f"Unexpected error in database connection: {e}")
        return None


def generate_id(prefix="item_"):
    """Generates a unique ID with a given prefix."""
    return prefix + str(uuid.uuid4())


def serialize_datetime_in_obj(obj):
    """
    Recursively traverses a dictionary or list and converts any
    datetime.datetime objects to ISO 8601 formatted strings.
    """
    if isinstance(obj, dict):
        return {k: serialize_datetime_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_datetime_in_obj(elem) for elem in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return obj


def parse_resume_from_file(resume_filepath_db):
    """
    Placeholder function for resume parsing.
    In a real-world application, this would use libraries like PyPDF2 (for PDFs)
    or python-docx (for DOCX files) to extract text from the actual resume file.
    """
    if not resume_filepath_db:
        return "No resume provided."

    # This is a placeholder summary. A real implementation would involve text extraction
    # and possibly another AI call to summarize the extracted text.
    filename = os.path.basename(resume_filepath_db)
    return f"The candidate's resume ({filename}) indicates strong skills in Python, Flask, and project management. They have 5 years of experience in backend development."

