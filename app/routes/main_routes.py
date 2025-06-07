from flask import Blueprint, send_from_directory, abort, current_app
import os

main_bp = Blueprint('main_bp', __name__)


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
