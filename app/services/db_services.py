import mysql.connector
from flask import current_app
import datetime
import uuid
import os

def get_db_connection():
    """Establishes a connection to the database."""
    try:
        conn = mysql.connector.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME']
        )
        return conn
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error connecting to MySQL: {err}")
        return None

def generate_id(prefix="item_"):
    """Generates a unique ID."""
    return prefix + str(uuid.uuid4())

def serialize_datetime_in_obj(obj):
    """Recursively converts datetime objects in an object to ISO format strings."""
    if isinstance(obj, dict):
        return {k: serialize_datetime_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_datetime_in_obj(elem) for elem in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return obj

def parse_resume_from_file(resume_filepath_db):
    """
    In a real app, this would use libraries like PyPDF2 or python-docx
    to extract text from the actual resume file.
    For this demo, we return placeholder text.
    """
    if not resume_filepath_db: return "No resume provided."
    filename = os.path.basename(resume_filepath_db)
    # This is a placeholder. A real implementation would involve text extraction.
    return f"The candidate's resume ({filename}) indicates strong skills in Python, Flask, and project management. They have 5 years of experience in backend development."

