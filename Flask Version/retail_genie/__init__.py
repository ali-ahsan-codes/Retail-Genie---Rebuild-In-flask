"""Flask application factory for Retail Genie."""

from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import text

from .config import Config
from .extensions import csrf, db, limiter, login_manager, migrate, socketio


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set in the environment before starting Retail Genie.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL must point to the central MySQL database before starting Retail Genie.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        cors_allowed_origins=None,
        manage_session=False,
    )

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"

    from .models import User  # Register model metadata before migrations run.

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        user = db.session.get(User, user_id)
        if user is None:
            return None
        authenticated_version = session.get("auth_version")
        if authenticated_version is None or str(authenticated_version) != str(user.auth_version):
            return None
        return user

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(error="authentication_required"), 401
        from flask import redirect, url_for

        return redirect(url_for("auth.login"))

    from .admin.routes import admin_bp
    from .auth.routes import auth_bp
    from .health.routes import health_bp
    from .main.routes import main_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def require_temporary_password_change():
        if current_user.is_authenticated and current_user.force_password_change:
            allowed_endpoints = {"auth.change_password", "auth.logout", "static", "health.liveness", "health.readiness"}
            if request.endpoint not in allowed_endpoints:
                return redirect(url_for("auth.change_password"))
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' ws: wss:",
        )
        return response

    @app.errorhandler(403)
    def forbidden(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="forbidden"), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="not_found"), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        app.logger.error("Unhandled application error for %s %s", request.method, request.path)
        if request.path.startswith("/api/"):
            return jsonify(error="internal_server_error"), 500
        return render_template("errors/500.html"), 500

    register_cli_commands(app)
    return app


def register_cli_commands(app: Flask) -> None:
    """Register safe first-admin provisioning without shipping default credentials."""
    import click

    from .models import User

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="Username for the first administrator.")
    def create_admin(username: str) -> None:
        """Create the initial admin account after running `flask db upgrade`."""
        from .models.user import is_valid_username, normalize_username

        normalized_username = normalize_username(username)
        if not is_valid_username(normalized_username):
            raise click.ClickException("Username must be 3–48 characters using letters, numbers, dots, underscores, or hyphens.")
        if User.query.filter_by(role="admin", is_active=True).count():
            raise click.ClickException("An active administrator already exists; use Accounts to manage users.")
        if User.query.filter_by(username=normalized_username).first():
            raise click.ClickException("That username already exists.")

        password = click.prompt("Password (minimum 12 characters)", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Password must be at least 12 characters.")

        user = User(username=normalized_username, role="admin", permissions=[])
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception as error:  # Keep provisioning errors generic; never print credentials.
            db.session.rollback()
            app.logger.error("Could not create initial administrator: %s", type(error).__name__)
            raise click.ClickException("Administrator creation failed. Check database connectivity and migration status.") from None

        click.echo(f"Administrator '{normalized_username}' created.")
