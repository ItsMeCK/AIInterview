from flask import Blueprint, send_from_directory, abort, current_app, render_template, redirect, url_for
from flask_login import current_user, login_required
import os

main_bp = Blueprint('main_bp', __name__)


@main_bp.route('/')
def index():
    """
    If the user is logged in, redirect to the admin dashboard.
    Otherwise, show the login page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main_bp.admin_dashboard'))
    return render_template('login.html')


@main_bp.route('/register')
def register():
    """Serves the registration page."""
    if current_user.is_authenticated:
        return redirect(url_for('main_bp.admin_dashboard'))
    return render_template('register.html')


@main_bp.route('/admin_dashboard')
@login_required
def admin_dashboard():
    """Serves the main admin dashboard page, protected by login."""
    return render_template('admin_dashboard.html')


@main_bp.route('/comparison_dashboard')
@login_required
def comparison_dashboard():
    """Serves the candidate comparison page, protected by login."""
    return render_template('comparison_dashboard.html')


@main_bp.route('/candidate_interview.html')
def candidate_interview():
    """Serves the candidate interview page. This is public."""
    return render_template('candidate_interview.html')


@main_bp.route('/uploads/<path:folder>/<path:filename>')
def serve_uploaded_file(folder, filename):
    if '..' in folder or '..' in filename:
        abort(404)

    # Construct the full path securely
    safe_folder_path = os.path.abspath(os.path.join(current_app.config['UPLOAD_FOLDER'], folder))

    # Security check: ensure the path is within the intended upload directory
    if not safe_folder_path.startswith(os.path.abspath(current_app.config['UPLOAD_FOLDER'])):
        abort(403)

    try:
        return send_from_directory(safe_folder_path, filename)
    except FileNotFoundError:
        abort(404)
