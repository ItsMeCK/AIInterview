from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.services.db_services import get_db_connection, generate_id
from app import bcrypt  # Import bcrypt from the app factory

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    company_name = data.get('companyName')
    admin_name = data.get('adminName')
    email = data.get('email')
    password = data.get('password')

    if not all([company_name, admin_name, email, password]):
        return jsonify({"message": "Missing required fields"}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor()

    try:
        # Check if email already exists
        cursor.execute("SELECT id FROM admins WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"message": "Email address already registered"}), 409

        # Create new company
        company_id = generate_id("comp_")
        cursor.execute("INSERT INTO companies (id, name) VALUES (%s, %s)", (company_id, company_name))

        # Create new admin
        admin_id = generate_id("admin_")
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        cursor.execute(
            "INSERT INTO admins (id, company_id, name, email, password_hash) VALUES (%s, %s, %s, %s, %s)",
            (admin_id, company_id, admin_name, email, hashed_password)
        )

        conn.commit()
        return jsonify({"message": "Company and admin registered successfully"}), 201

    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Registration Error: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred during registration"}), 500
    finally:
        cursor.close()
        conn.close()


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admin_data = cursor.fetchone()

        if admin_data and bcrypt.check_password_hash(admin_data['password_hash'], password):
            from app.models import Admin
            admin = Admin(id=admin_data['id'], email=admin_data['email'], name=admin_data['name'],
                          company_id=admin_data['company_id'])
            login_user(admin)
            return jsonify({
                "message": "Login successful",
                "admin": {
                    "id": admin.id,
                    "name": admin.name,
                    "email": admin.email,
                    "company_id": admin.company_id
                }
            }), 200
        else:
            return jsonify({"message": "Invalid email or password"}), 401

    except Exception as e:
        current_app.logger.error(f"Login Error: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred during login"}), 500
    finally:
        cursor.close()
        conn.close()


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route('/status', methods=['GET'])
@login_required
def status():
    return jsonify({
        "is_logged_in": True,
        "admin": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "company_id": current_user.company_id
        }
    }), 200
