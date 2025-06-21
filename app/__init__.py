from flask import Flask
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from config import Config
import os

# Initialize extensions
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main_bp.login'
login_manager.login_message_category = 'info'
mail = Mail()


def create_app(config_class=Config):
    """
    Creates and configures an instance of the Flask application.
    This is the application factory.
    """
    app = Flask(__name__, instance_relative_config=True, template_folder='templates', static_folder='static')
    app.config.from_object(config_class)

    # Initialize extensions with the app instance
    CORS(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # User loader function for Flask-Login
    from app.models import Admin
    @login_manager.user_loader
    def load_user(admin_id):
        return Admin.get(admin_id)

    # Ensure upload folders exist based on the configuration
    for folder_key in ['UPLOAD_FOLDER', 'RESUME_FOLDER', 'SCREENSHOT_FOLDER']:
        folder_path = app.config.get(folder_key)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path)
            app.logger.info(f"Created directory: {folder_path}")

    # Import and register Blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.interview_routes import interview_bp
    from app.routes.main_routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(interview_bp, url_prefix='/api/interview')
    app.register_blueprint(main_bp)

    app.logger.info("Application created and blueprints registered.")

    return app
