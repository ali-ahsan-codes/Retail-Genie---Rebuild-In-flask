from __future__ import annotations

import pytest
from sqlalchemy import event

from retail_genie import create_app
from retail_genie.extensions import db
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


@pytest.fixture(scope="session")
def app():
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "SESSION_PERMANENT": False,
        }
    )
    with application.app_context():
        engine = db.engine

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(connection, _connection_record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clear_database(app):
    from retail_genie.realtime.service import initialize_realtime_registry

    initialize_realtime_registry(app)
    with app.app_context():
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
