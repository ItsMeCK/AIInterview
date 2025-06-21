from flask import Blueprint, send_from_directory, abort, current_app, render_template, redirect, url_for
from flask_login import current_user, login_required
import os
import traceback

main_bp = Blueprint('main_bp', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main_bp.admin_dashboard'))
    return redirect(url_for('main_bp.index', action='login'))


@main_bp.route('/register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main_bp.admin_dashboard'))
    return redirect(url_for('main_bp.index', action='register'))


@main_bp.route('/admin_dashboard')
@login_required
def admin_dashboard():
    return render_template('admin_dashboard.html')


@main_bp.route('/comparison_dashboard')
@login_required
def comparison_dashboard():
    return render_template('comparison_dashboard.html')


@main_bp.route('/candidate_interview.html')
def candidate_interview():
    """Serves the candidate interview page with enhanced logging."""
    current_app.logger.info("Route /candidate_interview.html accessed.")
    try:
        # Attempt to render the template
        response = render_template('candidate_interview.html')
        current_app.logger.info("Successfully rendered candidate_interview.html template.")
        return response
    except Exception as e:
        # If rendering fails for any reason, log the full error and traceback
        current_app.logger.error(f"Error rendering candidate_interview.html: {e}\n{traceback.format_exc()}")
        # Return a 500 error to the browser so the failure is clear
        abort(500, description="Could not load the interview page due to a server error.")


@main_bp.route('/uploads/<path:folder>/<path:filename>')
def serve_uploaded_file(folder, filename):
    if '..' in folder or '..' in filename:
        abort(404)

    safe_folder_path = os.path.abspath(os.path.join(current_app.config['UPLOAD_FOLDER'], folder))

    if not safe_folder_path.startswith(os.path.abspath(current_app.config['UPLOAD_FOLDER'])):
        abort(403)

    try:
        return send_from_directory(safe_folder_path, filename)
    except FileNotFoundError:
        abort(404)
