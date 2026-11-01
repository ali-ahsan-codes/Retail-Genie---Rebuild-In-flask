"""Flask application factory for Retail Genie."""

from pathlib import Path
import secrets

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import text

from .config import Config
from .extensions import csrf, db, limiter, login_manager, socketio


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

    @app.context_processor
    def inject_template_context():
        from .device import is_mobile_phone
        from .share import app_login_url

        mobile_device = is_mobile_phone(
            request.user_agent.string,
            request.headers.get("Sec-CH-UA-Mobile"),
        )
        return {
            "csp_nonce": getattr(g, "csp_nonce", ""),
            "is_mobile_device": mobile_device,
            "app_login_url": None if mobile_device else app_login_url(),
        }

    db.init_app(app)
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

    from .models import User  # Register all application models before database operations.

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        from .auth.tenant_context import available_memberships, current_membership

        user = db.session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        if user.is_super_admin:
            if user.company_id is not None:
                return None
        else:
            selected_container_id = session.get("active_container_id")
            if selected_container_id:
                if current_membership(user, tenant_container_id=selected_container_id) is None:
                    return None
            elif session.get("pending_tenant_selection"):
                if not available_memberships(user.id):
                    return None
            else:
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

    from .admin.backup_routes import backup_admin_bp
    from .catalog import catalog_bp
    from .admin.routes import admin_bp
    from .admin.tenancy_routes import tenancy_admin_bp
    from .auth.routes import auth_bp
    from .commercial import commercial_bp
    from .health.routes import health_bp
    from .main.routes import main_bp
    from .realtime import realtime_bp
    from .realtime.service import initialize_realtime_registry
    from .sales import sales_bp
    from .settings import settings_bp
    from .scm import scm_bp
    from .attendance import attendance_bp
    from .stock_audits import stock_audits_bp
    from .messaging import messaging_bp
    from .cloud import cloud_bp
    from .reports import reports_bp
    from .display import display_bp
    from .express import express_bp
    from .saas import saas_bp

    initialize_realtime_registry(app)
    from .realtime.service import start_realtime_dispatcher

    @app.before_request
    def _ensure_realtime_dispatcher_started():
        start_realtime_dispatcher(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(commercial_bp)
    app.register_blueprint(realtime_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(tenancy_admin_bp)
    app.register_blueprint(backup_admin_bp)
    from .field_integration import register as register_field_integration
    register_field_integration(app)
    from .sync_core import register as register_transport
    register_transport(app)
    from .field_transport import register as register_transport_worker
    register_transport_worker(app)
    from .field_catalog import register as register_field_catalog
    register_field_catalog(app)
    from .field_orders import register as register_field_orders
    register_field_orders(app)
    app.register_blueprint(settings_bp)
    app.register_blueprint(scm_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(stock_audits_bp)
    app.register_blueprint(messaging_bp)
    app.register_blueprint(cloud_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(display_bp)
    app.register_blueprint(express_bp)
    app.register_blueprint(saas_bp)

    @app.before_request
    def require_tenant_context_and_password_change():
        g.csp_nonce = secrets.token_urlsafe(18)
        if current_user.is_authenticated and current_user.force_password_change:
            allowed_endpoints = {"auth.change_password", "auth.logout", "auth.select_tenant", "static", "health.liveness", "health.readiness"}
            if request.endpoint not in allowed_endpoints:
                return redirect(url_for("auth.change_password"))
        if current_user.is_authenticated and not current_user.is_super_admin:
            from .auth.tenant_context import current_membership

            if current_membership(current_user) is None:
                if request.endpoint in {"auth.select_tenant", "auth.logout", "auth.change_password", "static", "health.liveness", "health.readiness"}:
                    return None
                if session.get("pending_tenant_selection"):
                    return redirect(url_for("auth.select_tenant"))
                session.clear()
                return redirect(url_for("auth.login"))
        return None

    @app.after_request
    def add_security_headers(response):
        nonce = getattr(g, "csp_nonce", None) or secrets.token_urlsafe(18)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        if request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "object-src 'none'; "
            f"script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; "
            "img-src 'self' data:; connect-src 'self' ws: wss:",
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
    """Register first-admin provisioning and the MySQL backup worker."""
    import click

    from .models import User

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="Username for the first administrator.")
    def create_admin(username: str) -> None:
        """Create the initial Main Admin after loading the provided MySQL schema."""
        from .models.user import is_valid_username, normalize_username

        normalized_username = normalize_username(username)
        if not is_valid_username(normalized_username):
            raise click.ClickException("Username must be 3–48 characters using letters, numbers, dots, underscores, or hyphens.")
        if User.query.filter_by(role="super_admin", is_active=True).count():
            raise click.ClickException("An active Main Admin already exists.")
        if User.query.filter_by(username=normalized_username).first():
            raise click.ClickException("That username already exists.")

        password = click.prompt("Password (minimum 12 characters)", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Password must be at least 12 characters.")

        user = User(username=normalized_username, role="super_admin", company_id=None, permissions=[])
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            app.logger.error("Could not create initial administrator: %s", type(error).__name__)
            raise click.ClickException("Administrator creation failed. Check database connectivity and confirm the schema is installed.") from None

        click.echo(f"Main Admin '{normalized_username}' created.")

    @app.cli.command("seed-demo")
    @click.option(
        "--confirm-demo-data",
        is_flag=True,
        help="Confirm writing sample company, store, products, and opening stock to a fresh local database.",
    )
    def seed_demo(confirm_demo_data: bool) -> None:
        """Add opt-in demo records to a fresh local Retail Genie database."""
        if not confirm_demo_data:
            raise click.ClickException(
                "No data was written. Re-run with --confirm-demo-data only for a fresh local retail_genie database."
            )

        database_url = db.engine.url
        if (
            database_url.get_backend_name() != "mysql"
            or database_url.database != "retail_genie"
            or database_url.host not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise click.ClickException(
                "Demo seeding is restricted to a local MySQL database named retail_genie. No data was written."
            )

        from .models import CatalogProduct, Company, Store, TenantContainer
        from .demo_data import DEMO_CONTAINER_SLUG, seed_demo_records

        existing_demo = TenantContainer.query.filter_by(slug=DEMO_CONTAINER_SLUG).first()
        if existing_demo is not None:
            click.echo("Demo data already exists; no changes were made.")
            return
        if TenantContainer.query.first() or Company.query.first() or Store.query.first() or CatalogProduct.query.first():
            raise click.ClickException("Business data already exists; refusing to add demo records.")

        try:
            created = seed_demo_records()
        except Exception as error:
            app.logger.error("Demo data seeding failed (%s)", type(error).__name__)
            raise click.ClickException("Demo data was not seeded. Check local MySQL connectivity and schema setup.") from None

        if created:
            click.echo("Demo tenant, company, store, five products, and opening stock created.")
        else:
            click.echo("Demo data already exists; no changes were made.")

    @app.cli.command("backup-scheduler")
    @click.option("--once", "run_once", is_flag=True, help="Check for one due backup and exit.")
    def backup_scheduler(run_once: bool) -> None:
        """Run the separate MySQL backup scheduler/worker process."""
        from .backups.scheduler import run_backup_scheduler

        try:
            run_backup_scheduler(app, once=run_once)
        except RuntimeError as error:
            raise click.ClickException(str(error)) from None
        except Exception as error:
            app.logger.error("Backup scheduler could not start (%s)", type(error).__name__)
            raise click.ClickException("Backup scheduler could not start; verify MySQL connectivity and configuration.") from None
        if run_once:
            click.echo("Backup scheduler check completed.")
