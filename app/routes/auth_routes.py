from flask import Blueprint, request, jsonify, url_for
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Admin
from app import bcrypt
from app.services.db_services import get_db_connection
import traceback
from flask import current_app

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        current_app.logger.info(f"Received registration attempt with data: {data}")

        if not data:
            current_app.logger.error("Registration failed because the request body was not JSON or was empty.")
            return jsonify({'message': 'Invalid request format. Expected JSON.'}), 400

        required_fields = ['name', 'company_name', 'email', 'password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            error_message = f"Registration failed. Missing or empty fields: {', '.join(missing_fields)}."
            current_app.logger.error(error_message)
            return jsonify({'message': 'Missing required fields. Please fill out the entire form.', 'details': error_message}), 400

        conn = get_db_connection()
        if not conn:
            current_app.logger.error("Registration failed due to a database connection error.")
            return jsonify({'message': 'Database connection failed.'}), 500

        cursor = conn.cursor(dictionary=True)
        
        # Check if email already exists
        cursor.execute("SELECT id FROM admins WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            conn.close()
            return jsonify({'message': 'Email address already registered.'}), 409

        # Get or create company
        cursor.execute("SELECT id FROM companies WHERE name = %s", (data['company_name'],))
        company = cursor.fetchone()
        if not company:
            cursor.execute("INSERT INTO companies (name) VALUES (%s)", (data['company_name'],))
            company_id = cursor.lastrowid
        else:
            company_id = company['id']

        # Create admin
        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        cursor.execute(
            "INSERT INTO admins (name, email, password_hash, company_id) VALUES (%s, %s, %s, %s)",
            (data['name'], data['email'], hashed_password, company_id)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Registration successful! Please log in.'}), 201
    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            conn.close()
        traceback.print_exc()
        return jsonify({'message': 'An internal server error occurred during registration.'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        conn = get_db_connection()
        if not conn:
            return jsonify({'message': 'Database connection failed.'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE email = %s", (data['email'],))
        admin_data = cursor.fetchone()
        conn.close()

        if admin_data and bcrypt.check_password_hash(admin_data['password_hash'], data['password']):
            admin = Admin(
                id=admin_data['id'],
                email=admin_data['email'],
                name=admin_data['name'],
                company_id=admin_data['company_id']
            )
            login_user(admin, remember=True)
            return jsonify({'message': 'Login successful', 'redirect_url': url_for('main_bp.admin_dashboard')}), 200
        else:
            return jsonify({'message': 'Invalid credentials. Please try again.'}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({'message': 'An internal error occurred.'}), 500


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful', 'redirect_url': '/'}), 200


@auth_bp.route('/status', methods=['GET'])
@login_required
def status():
    try:
        return jsonify({
            "is_logged_in": True,
            "admin": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "company_id": current_user.company_id
            }
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"is_logged_in": False, "error": "Session check failed"}), 500
