from flask import Blueprint, request, jsonify, url_for, render_template
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Admin
from app import bcrypt, mail
from app.services.db_services import get_db_connection
import traceback
from flask import current_app
from flask_mail import Message
import secrets

auth_bp = Blueprint('auth_bp', __name__)


def send_verification_email(admin_email, token):
    """Sends the verification email."""
    link = url_for('auth_bp.verify_email', token=token, _external=True)
    msg = Message(
        'Verify Your AI Interview Portal Account',
        sender=('AI Interview Portal', current_app.config['MAIL_USERNAME']),
        recipients=[admin_email]
    )
    msg.body = f'Welcome! Please click the following link to verify your account and get started: {link}'
    mail.send(msg)


@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['name', 'company_name', 'email', 'password']):
            return jsonify({'message': 'Missing required fields.'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': 'Database connection failed.'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM admins WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            conn.close()
            return jsonify({'message': 'Email address already registered.'}), 409

        cursor.execute("SELECT id FROM companies WHERE name = %s", (data['company_name'],))
        company = cursor.fetchone()
        if not company:
            cursor.execute("INSERT INTO companies (name) VALUES (%s)", (data['company_name'],))
            company_id = cursor.lastrowid
        else:
            company_id = company['id']

        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        verification_token = secrets.token_urlsafe(32)

        cursor.execute(
            "INSERT INTO admins (name, email, password_hash, company_id, verification_token) VALUES (%s, %s, %s, %s, %s)",
            (data['name'], data['email'], hashed_password, company_id, verification_token)
        )

        send_verification_email(data['email'], verification_token)

        conn.commit()
        conn.close()

        return jsonify({'message': 'Registration successful! Please check your email to verify your account.'}), 201
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
                company_id=admin_data['company_id'],
                role=admin_data['role'],
                interview_limit=admin_data['interview_limit'],
                is_verified=admin_data['is_verified']
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
    return redirect(url_for('main_bp.index'))


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
                "company_id": current_user.company_id,
                "role": current_user.role,
                "is_verified": current_user.is_verified
            }
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"is_logged_in": False, "error": "Session check failed"}), 500


@auth_bp.route('/verify/<token>')
def verify_email(token):
    conn = get_db_connection()
    if not conn: return "Database connection failed.", 500
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM admins WHERE verification_token = %s", (token,))
        admin_id = cursor.fetchone()

        if admin_id:
            cursor.execute("UPDATE admins SET is_verified = 1, verification_token = NULL WHERE id = %s", (admin_id[0],))
            conn.commit()
            return render_template('verification_success.html')
        else:
            return render_template('verification_failed.html', message="Invalid or expired verification link.")
    except Exception as e:
        current_app.logger.error(f"Verification error: {e}")
        return render_template('verification_failed.html', message="An error occurred during verification.")
    finally:
        if conn.is_connected(): conn.close()


@auth_bp.route('/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    if current_user.is_verified:
        return jsonify({"message": "Account already verified."}), 400

    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admins SET verification_token = %s WHERE id = %s", (token, current_user.id))
    conn.commit()
    conn.close()

    send_verification_email(current_user.email, token)
    return jsonify({"message": "A new verification email has been sent."}), 200
