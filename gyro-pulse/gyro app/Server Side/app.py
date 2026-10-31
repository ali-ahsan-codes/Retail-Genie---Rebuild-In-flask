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

    return app


# Create application instance
app = create_app()

# Create tables if they don't exist
with app.app_context():
    db.create_all()
    # Seed default admin user if no users exist
    from werkzeug.security import generate_password_hash
    if not User.query.first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            is_active=True,
            show_stock_quantity=True  # Default: show stock quantities
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: admin / admin123")
        print("System ready with device-bound API keys, token pools, and GPC encryption.")

# --------------------------------------------------------------------------
# Auto-backup scheduler
# --------------------------------------------------------------------------
def scheduled_backup():
    with app.app_context():
        try:
            backup_db()
            print(f"[{datetime.now()}] Auto backup completed successfully.")
        except Exception as e:
            print(f"[{datetime.now()}] Auto backup failed: {e}")

# Start scheduler only if not in debug mode? (optional)
# For development, you may want to keep it running anyway.
scheduler = BackgroundScheduler()
interval = get_backup_interval()
scheduler.add_job(scheduled_backup, 'interval', minutes=interval)
scheduler.start()
print(f"[OK] Auto backup scheduler started - running every {interval} minute(s).")

# Shutdown scheduler gracefully when the app exits
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )