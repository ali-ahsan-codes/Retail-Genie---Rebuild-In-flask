from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from retail_genie import create_app
from retail_genie.extensions import db


BASE_REVISION = "93c522098bed"


def test_upgrade_preserves_company_isolation_and_backfills_tenant_keys(tmp_path):
    project_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "container-backfill.sqlite"
    app = create_app(
        {
            "SECRET_KEY": "test-only-secret-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    migration_config = Config(str(project_dir / "migrations" / "alembic.ini"))
    migration_config.set_main_option("script_location", str(project_dir / "migrations"))
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")

    with app.app_context():
        command.upgrade(migration_config, BASE_REVISION)
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies "
                    "(id, name, slug, timezone, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, 'Asia/Muscat', 1, :created_at, :updated_at)"
                ),
                {
                    "id": "separate-legacy-company",
                    "name": "Separate Legacy Company",
                    "slug": "separate-legacy-company",
                    "created_at": stamp,
                    "updated_at": stamp,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO stores "
                    "(id, company_id, code, name, is_active, created_at, updated_at) "
                    "VALUES ('separate-legacy-store', 'separate-legacy-company', 'MAIN', 'Separate Branch', 1, :created_at, :updated_at)"
                ),
                {"created_at": stamp, "updated_at": stamp},
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, password_hash, role, permissions, is_active, force_password_change, auth_version, created_at, updated_at, company_id) "
                    "VALUES ('separate-legacy-user', 'separate.legacy.user', 'argon2-test-hash', 'cashier', '[]', 1, 0, 1, :created_at, :updated_at, 'separate-legacy-company')"
                ),
                {"created_at": stamp, "updated_at": stamp},
            )
            connection.execute(
                text(
                    "INSERT INTO user_store_assignments "
                    "(id, company_id, user_id, store_id, assigned_by_id, can_view_shared_bills, is_active, created_at, updated_at) "
                    "VALUES ('separate-legacy-assignment', 'separate-legacy-company', 'separate-legacy-user', 'separate-legacy-store', NULL, 0, 1, :created_at, :updated_at)"
                ),
                {"created_at": stamp, "updated_at": stamp},
            )
            connection.execute(
                text(
                    "INSERT INTO products (id, company_id, store_id, name, sku) "
                    "VALUES ('separate-legacy-product', 'separate-legacy-company', 'separate-legacy-store', 'Product', 'SKU-1')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO billing_series "
                    "(id, company_id, category, prefix, next_number, is_active, created_at, updated_at) "
                    "VALUES ('separate-legacy-series', 'separate-legacy-company', 'cash', 'SEP', 1, 1, :created_at, :updated_at)"
                ),
                {"created_at": stamp, "updated_at": stamp},
            )
            connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(id, company_id, store_id, actor_user_id, action, entity_type, entity_id, created_at) "
                    "VALUES ('separate-legacy-audit', 'separate-legacy-company', 'separate-legacy-store', 'separate-legacy-user', 'seed', 'product', 'separate-legacy-product', :created_at)"
                ),
                {"created_at": stamp},
            )

        command.upgrade(migration_config, "head")
        engine = db.engine
        engine.dispose()

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(connection, _connection_record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        with db.engine.connect() as connection:
            companies = connection.execute(
                text(
                    "SELECT id, tenant_container_id FROM companies "
                    "WHERE id IN ('retail-genie-default-company', 'separate-legacy-company') ORDER BY id"
                )
            ).all()
            assert companies == [
                ("retail-genie-default-company", "retail-genie-default-company"),
                ("separate-legacy-company", "separate-legacy-company"),
            ]
            assert connection.execute(
                text("SELECT tenant_container_id FROM products WHERE id='separate-legacy-product'")
            ).scalar_one() == "separate-legacy-company"
            assert connection.execute(
                text(
                    "SELECT tenant_container_id, company_id, sku, name "
                    "FROM catalog_products WHERE id='separate-legacy-product'"
                )
            ).one() == ("separate-legacy-company", "separate-legacy-company", "SKU-1", "Product")
            assert connection.execute(
                text(
                    "SELECT tenant_container_id, company_id, store_id, quantity_on_hand "
                    "FROM inventory_balances WHERE product_id='separate-legacy-product'"
                )
            ).one() == ("separate-legacy-company", "separate-legacy-company", "separate-legacy-store", 0)
            assert connection.execute(
                text(
                    "SELECT movement_type, quantity_delta FROM inventory_movements "
                    "WHERE product_id='separate-legacy-product'"
                )
            ).one() == ("opening", 0)
            assert connection.execute(
                text("SELECT tenant_container_id FROM billing_series WHERE id='separate-legacy-series'")
            ).scalar_one() == "separate-legacy-company"
            assert connection.execute(
                text("SELECT tenant_container_id FROM container_memberships WHERE user_id='separate-legacy-user'")
            ).scalar_one() == "separate-legacy-company"
            assert connection.execute(
                text("SELECT tenant_container_id FROM user_store_assignments WHERE id='separate-legacy-assignment'")
            ).scalar_one() == "separate-legacy-company"
            assert connection.execute(
                text("SELECT tenant_container_id FROM audit_events WHERE id='separate-legacy-audit'")
            ).scalar_one() == "separate-legacy-company"
            assert connection.execute(
                text("SELECT count(*) FROM tenant_data_policies WHERE tenant_container_id='separate-legacy-company'")
            ).scalar_one() == 12
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []

        with pytest.raises(IntegrityError):
            with db.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO stores "
                        "(id, tenant_container_id, company_id, code, name, is_active, created_at, updated_at) "
                        "VALUES ('invalid-cross-tenant-store', 'retail-genie-default-company', 'separate-legacy-company', 'BAD', 'Invalid', 1, :created_at, :updated_at)"
                    ),
                    {"created_at": stamp, "updated_at": stamp},
                )

        db.session.remove()
        db.engine.dispose()
