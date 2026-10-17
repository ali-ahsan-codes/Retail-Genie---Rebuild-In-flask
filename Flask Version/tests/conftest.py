from __future__ import annotations

import pytest

from retail_genie import create_app
from retail_genie.extensions import db
from retail_genie.models import User


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
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clear_database(app):
    yield
    with app.app_context():
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


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
    ) -> str:
        with app.app_context():
            user = User(
                username=username,
                role=role,
                permissions=permissions or [],
                is_active=is_active,
                force_password_change=force_password_change,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return user.id

    return factory
