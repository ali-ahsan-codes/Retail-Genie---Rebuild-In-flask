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

    initialize_realtime_registry(app)
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

    @app.before_request
    def require_tenant_context_and_password_change():
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
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        if request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")
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
    """Register safe account, backup-worker, and one-time import commands."""
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
        if User.query.filter_by(role="super_admin", is_active=True).count():
            raise click.ClickException(
                "An active Main Admin already exists; use company administration or reset-imported-password for an approved account."
            )
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
        except Exception as error:  # Keep provisioning errors generic; never print credentials.
            db.session.rollback()
            app.logger.error("Could not create initial administrator: %s", type(error).__name__)
            raise click.ClickException("Administrator creation failed. Check database connectivity and migration status.") from None

        click.echo(f"Main Admin '{normalized_username}' created.")

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

    @app.cli.command("import-sqlite")
    @click.option("--source", "source_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--apply", "apply_import", is_flag=True, help="Apply the import; otherwise perform a read-only dry run.")
    @click.option("--confirm-apply", is_flag=True, help="Required with --apply after reviewing the dry-run report.")
    @click.option("--password-policy", type=click.Choice(["reset", "hash"]), default="reset", show_default=True)
    @click.option("--confirm-legacy-passwords", is_flag=True, help="Required with --password-policy=hash on apply.")
    @click.option("--company-id", help="Company to receive the legacy rows; required when multiple companies exist.")
    @click.option("--store-id", help="Store to receive legacy store-scoped rows; required when multiple stores exist.")
    def import_sqlite(
        source_path: Path,
        apply_import: bool,
        confirm_apply: bool,
        password_policy: str,
        confirm_legacy_passwords: bool,
        company_id: str | None,
        store_id: str | None,
    ) -> None:
        """Validate or import the reviewed legacy SQLite database."""
        from .migrations.legacy_import import LegacyImportError, import_sqlite_database

        if apply_import and not confirm_apply:
            raise click.ClickException("Review a dry run first, then pass --apply --confirm-apply.")
        if apply_import and password_policy == "hash" and not confirm_legacy_passwords:
            raise click.ClickException(
                "Preserving legacy passwords requires --confirm-legacy-passwords; the default policy resets them."
            )
        try:
            report = import_sqlite_database(
                source_path,
                apply=apply_import,
                password_policy=password_policy,
                company_id=company_id,
                store_id=store_id,
            )
        except LegacyImportError as error:
            raise click.ClickException(str(error)) from None
        except Exception as error:
            app.logger.error(
                "SQLite import failed and the target transaction was rolled back (%s)",
                type(error).__name__,
            )
            raise click.ClickException(
                f"SQLite import failed ({type(error).__name__}); check server logs."
            ) from None

        click.echo("Import mode: " + ("APPLIED" if apply_import else "DRY RUN — no target rows changed"))
        click.echo(f"Password policy: {password_policy}; accounts will require a password change.")
        click.echo("Table counts:")
        for table_name in sorted(report.source_counts):
            inserted = report.inserted_counts.get(table_name, 0)
            skipped = report.skipped_counts.get(table_name, 0)
            click.echo(
                f"  {table_name}: source={report.source_counts[table_name]}, "
                f"inserted={inserted}, skipped={skipped}"
            )
        click.echo(
            f"User credentials reset={report.user_passwords_reset}, "
            f"legacy credentials hashed={report.user_passwords_hashed}."
        )
        orders = report.reconciliation.get("orders", {})
        payments = report.reconciliation.get("payments", {})
        stock = report.reconciliation.get("stock", {})
        counters = report.reconciliation.get("invoice_counters", {})
        click.echo(
            "Reconciliation: "
            f"orders={orders.get('rows', 0)} total_OMR={orders.get('total_omr', '0')}; "
            f"payments_OMR={payments.get('combined_total_omr', '0')}; "
            f"stock_units={stock.get('quantity_total', 0)}; "
            f"invoice_counter_rows={counters.get('rows', 0)}."
        )

    @app.cli.command("migrate-media")
    @click.option("--source", "source_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--source-uploads", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path))
    @click.option("--company-id", help="Imported target company that owns these legacy uploads.")
    @click.option("--destination", type=click.Path(file_okay=False, path_type=Path), help="Override UPLOADS_DIR for this run.")
    @click.option("--apply", "apply_migration", is_flag=True, help="Copy files and update matching MySQL path metadata.")
    @click.option("--confirm-apply", is_flag=True, help="Required with --apply after reviewing the dry-run report.")
    def migrate_media(
        source_path: Path,
        source_uploads: Path,
        company_id: str | None,
        destination: Path | None,
        apply_migration: bool,
        confirm_apply: bool,
    ) -> None:
        """Preflight or migrate legacy uploads after the SQLite import."""
        from .migrations.media import MediaMigrationError, migrate_legacy_media

        if apply_migration and not confirm_apply:
            raise click.ClickException("Review the media dry run first, then pass --apply --confirm-apply.")
        if apply_migration and not company_id:
            raise click.ClickException("Applying media migration requires --company-id.")
        try:
            report = migrate_legacy_media(
                source_path,
                source_uploads,
                apply=apply_migration,
                company_id=company_id,
                destination_root=destination,
            )
        except MediaMigrationError as error:
            raise click.ClickException(str(error)) from None
        except Exception as error:
            app.logger.error("Legacy media migration failed (%s)", type(error).__name__)
            raise click.ClickException("Legacy media migration failed; check server logs.") from None

        mode = "APPLIED" if apply_migration else "DRY RUN — no files or database paths changed"
        click.echo(f"Media migration: {mode}")
        click.echo(
            f"References={report.source_references}; local={report.local_references}; "
            f"unique_files={report.unique_local_files}; cloud_refs={report.cloud_file_references}; "
            f"cloud_manifests={report.cloud_metadata_files}; orphan_cloud_users={len(report.orphaned_cloud_users)}; "
            f"uploads_tree_files={report.source_upload_files}; unreferenced={report.unreferenced_files}; "
            f"external={report.external_references}; "
            f"embedded={report.embedded_references}; missing_source_files={len(report.missing_source_files)}."
        )
        if apply_migration:
            click.echo(
                f"Copied={report.copied_files}; already_present={report.already_present_files}; "
                f"path_updates={report.rewritten_target_references}; "
                f"already_updated={report.already_rewritten_references}; "
                f"verified_database_paths={report.database_paths_verified}; "
                f"verified_cloud_paths={report.cloud_paths_verified}."
            )
        if report.missing_source_files:
            examples = ", ".join(report.missing_source_files[:5])
            raise click.ClickException(
                f"The source uploads directory is missing referenced files: {examples}"
            )

    @app.cli.command("reset-imported-password")
    @click.option("--username", required=True, help="Imported account to reset.")
    @click.option("--activate/--no-activate", default=True, show_default=True)
    def reset_imported_password(username: str, activate: bool) -> None:
        """Set an interactive temporary password for a migrated account."""
        from .models.user import normalize_username

        normalized_username = normalize_username(username)
        target = User.query.filter_by(username=normalized_username).first()
        if target is None:
            raise click.ClickException("No account with that username exists.")
        password = click.prompt("Temporary password (minimum 12 characters)", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Password must be at least 12 characters.")
        target.set_password(password)
        target.is_active = activate
        target.force_password_change = True
        target.auth_version += 1
        db.session.commit()
        click.echo(f"Password reset for '{normalized_username}'. The account must change it at next sign-in.")
