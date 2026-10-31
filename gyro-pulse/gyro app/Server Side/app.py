import os
import logging
from flask import Flask, jsonify, redirect, url_for, send_from_directory, json
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import datetime

# Import database and blueprints
from models import db, User
from api import api_bp
from dashboard import dashboard_bp
from auth import auth_bp
from backup import backup_db, get_backup_interval

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO if os.getenv('FLASK_DEBUG', '0') == '0' else logging.DEBUG,
    format='%(asctime)s [%(levelname)s] in %(module)s: %(message)s'
)

def create_app():
    """
    Application Factory for Gyro Pulse Flask API.
    """
    app = Flask(__name__)

    # --------------------------------------------------------------------------
    # Configuration
    # --------------------------------------------------------------------------
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret-key-change-in-prod')
    
    # Load folders from config.json or environment
    config_json_path = os.path.join(app.root_path, 'config.json')
    if os.path.exists(config_json_path):
        try:
            with open(config_json_path, 'r') as f:
                cfg = json.load(f)
                app.config['UPLOAD_FOLDER'] = cfg.get('app', {}).get('upload_folder', './uploads')
                app.config['BACKUP_FOLDER'] = cfg.get('app', {}).get('backup_folder', './backups')
        except Exception:
            app.config['UPLOAD_FOLDER'] = './uploads'
            app.config['BACKUP_FOLDER'] = './backups'
    else:
        app.config['UPLOAD_FOLDER'] = './uploads'
        app.config['BACKUP_FOLDER'] = './backups'
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB max upload payload

    production = os.getenv('APP_ENV') == 'production'
    if production and (not os.getenv('SECRET_KEY') or len(os.getenv('SECRET_KEY', '')) < 32 or not os.getenv('MASTER_SECRET')):
        raise RuntimeError('Production requires SECRET_KEY (32+ characters) and MASTER_SECRET')
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production)

    # Database Setup
    db_url = os.getenv('DATABASE_URL', 'sqlite:///gyro_pulse.db')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --------------------------------------------------------------------------
    # Middleware & Extensions
    # --------------------------------------------------------------------------
    db.init_app(app)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    allowed_origins = os.getenv('CORS_ALLOWED_ORIGINS', '*').split(',')
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    app.wsgi_app = ProxyFix(
        app.wsgi_app, 
        x_for=1, 
        x_proto=1, 
        x_host=1, 
        x_prefix=1
    )

    # --------------------------------------------------------------------------
    # Register Blueprints
    # --------------------------------------------------------------------------
    app.register_blueprint(api_bp)          # /api/...
    app.register_blueprint(dashboard_bp)    # /dashboard/...
    app.register_blueprint(auth_bp)         # /login, /logout

    # --------------------------------------------------------------------------
    # Static file route for media uploads
    # --------------------------------------------------------------------------
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        upload_folder = os.path.abspath(app.config.get('UPLOAD_FOLDER', './uploads'))
        return send_from_directory(upload_folder, filename)

    # --------------------------------------------------------------------------
    # Root route – redirect to dashboard or login
    # --------------------------------------------------------------------------
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'healthy',
            'service': 'Gyro Pulse Backend',
            'version': '4.0',
            'features': ['offline-first', 'token-based-security', 'device-binding', 'gpc-encryption', 'media-sync']
        }), 200

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'status': 'error', 'message': 'Resource not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request
        if request.is_json or request.path.startswith(('/api', '/session-check', '/user-info')):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('auth.login'))

    from fulfillment import register_fulfillment
    register_fulfillment(app)
    return app


# WSGI import has no database writes, default accounts or background threads.
app = create_app()

@app.cli.command('init-db')
def init_database():
    """Initialize a new database; use migrations for existing deployments."""
    db.create_all()

@app.cli.command('create-admin')
def create_admin():
    """Interactively provision the first administrator without default credentials."""
    import click
    from werkzeug.security import generate_password_hash
    username = click.prompt('Username')
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        raise click.ClickException('Password must contain at least 12 characters')
    if User.query.filter_by(username=username).first():
        raise click.ClickException('Username already exists')
    db.session.add(User(username=username, password_hash=generate_password_hash(password), role='admin', is_active=True))
    db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
