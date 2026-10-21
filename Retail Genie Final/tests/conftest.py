from __future__ import annotations

import os

import pytest
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event, inspect, make_url

from retail_genie import create_app
from retail_genie.extensions import db, migrate
from retail_genie.models import (
    BillingSeries,
    Company,
    ContainerMembership,
    INVOICE_CATEGORIES,
    OrderNumberSeries,
    Store,
    TenantContainer,
    User,
    UserStoreAssignment,
)
from retail_genie.tenancy.service import seed_tenant_data_policies


def _clear_mysql_test_tables() -> None:
    """Remove test rows while retaining schema in the guarded disposable DB."""
    db.session.remove()
    with db.engine.connect() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        connection.commit()
        try:
            for table in reversed(db.metadata.sorted_tables):
                connection.execute(table.delete())
            connection.commit()
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            connection.commit()


@pytest.fixture(scope="session")
def app():
    mysql_test_url = os.getenv("RETAIL_GENIE_MYSQL_TEST_URL")
    database_uri = "sqlite://"
    if mysql_test_url:
        try:
            test_url = make_url(mysql_test_url)
        except (TypeError, ValueError):
            raise RuntimeError("RETAIL_GENIE_MYSQL_TEST_URL is not a valid SQLAlchemy URL.") from None
        if test_url.get_backend_name() != "mysql" or not (test_url.database or "").endswith("_phase6_test"):
            raise RuntimeError(
                "MySQL integration tests require a MySQL database name ending in '_phase6_test'; "
                "the suite clears its test tables between cases."
            )
        database_uri = mysql_test_url

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": database_uri,
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "SESSION_PERMANENT": False,
        }
    )
    with application.app_context():
        engine = db.engine
        if engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def _enable_sqlite_foreign_keys(connection, _connection_record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
            db.create_all()
        else:
            # Do not let the MySQL test fixture create or alter schema. Require
            # the operator to run reviewed Alembic migrations explicitly first.
            with engine.connect() as connection:
                current_heads = set(MigrationContext.configure(connection).get_current_heads())
                expected_heads = set(ScriptDirectory.from_config(migrate.get_config()).get_heads())
                missing_tables = set(db.metadata.tables) - set(inspect(connection).get_table_names())
            if not expected_heads or current_heads != expected_heads or missing_tables:
                raise RuntimeError(
                    "MySQL integration database is not at the current Alembic head or is missing mapped tables; "
                    "run reviewed `flask db upgrade` on the disposable *_phase6_test database first."
                )
    yield application
    with application.app_context():
        db.session.remove()
        if db.engine.dialect.name == "sqlite":
            db.drop_all()
        db.engine.dispose()


@pytest.fixture(autouse=True)
def clear_database(app):
    from retail_genie.realtime.service import initialize_realtime_registry

    initialize_realtime_registry(app)
    with app.app_context():
        if db.engine.dialect.name == "mysql":
            _clear_mysql_test_tables()
        container = TenantContainer(
            id="test-container",
            name="Test Tenant",
            slug="test-tenant",
            timezone="Asia/Muscat",
        )
        db.session.add(container)
        db.session.flush()
        seed_tenant_data_policies(container.id)
        company = Company(
            id="test-company",
            tenant_container_id=container.id,
            name="Test Company",
            slug="test-company",
        )
        db.session.add(company)
        db.session.flush()
        store = Store(
            id="test-store",
            tenant_container_id=container.id,
            company_id=company.id,
            code="MAIN",
            name="Main Store",
        )
        prefixes = {"cash": "CASH-", "bank": "BANK-", "bank_transfer": "BT-", "other": "OTH-"}
        db.session.add(store)
        db.session.add_all(
            [
                BillingSeries(
                    tenant_container_id=container.id,
                    company_id=company.id,
                    category=category,
                    prefix=prefixes[category],
                    next_number=1,
                )
                for category in INVOICE_CATEGORIES
            ]
        )
        db.session.add(
            OrderNumberSeries(
                tenant_container_id=container.id,
                company_id=company.id,
                prefix="ORD-",
                next_number=1,
            )
        )
        db.session.commit()
    yield
    with app.app_context():
        db.session.remove()
        if db.engine.dialect.name == "sqlite":
            raw_connection = db.engine.raw_connection()
            cursor = raw_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            raw_connection.commit()
            cursor.close()
            raw_connection.close()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()
            db.session.remove()
            raw_connection = db.engine.raw_connection()
            cursor = raw_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            raw_connection.commit()
            cursor.close()
            raw_connection.close()
        else:
            # The guarded *_phase6_test schema is retained for repeat runs.
            _clear_mysql_test_tables()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def create_user(app):
    def factory(
        username: str,
        password: str = "A-long-test-password-4!",
        role: str = "salesperson",
        permissions: list[str] | None = None,
        is_active: bool = True,
        force_password_change: bool = False,
        company_id: str | None = None,
        tenant_container_id: str | None = None,
        can_view_shared_bills: bool = False,
    ) -> str:
        with app.app_context():
            if role != "super_admin":
                company_id = company_id or "test-company"
                company = db.session.get(Company, company_id)
                if company is None:
                    raise ValueError(f"Unknown test company {company_id!r}")
                tenant_container_id = tenant_container_id or company.tenant_container_id
            user = User(
                username=username,
                company_id=company_id,
                role=role,
                permissions=permissions or [],
                is_active=is_active,
                force_password_change=force_password_change,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            if role != "super_admin":
                db.session.add(
                    ContainerMembership(
                        tenant_container_id=tenant_container_id,
                        user_id=user.id,
                        company_id=company_id,
                        role=role,
                        permissions=permissions or [],
                        is_default=True,
                        is_active=is_active,
                    )
                )
                if role not in {"company_admin", "admin"}:
                    db.session.add(
                        UserStoreAssignment(
                            tenant_container_id=tenant_container_id,
                            company_id=company_id,
                            user_id=user.id,
                            store_id="test-store",
                            can_view_shared_bills=can_view_shared_bills,
                        )
                    )
            db.session.commit()
            return user.id

    return factory
