"""Local guardrails and opt-in MySQL deployment acceptance checks."""

import pytest
from sqlalchemy import create_engine

from retail_genie.extensions import db, migrate
from retail_genie.phase6 import PreflightError, mysql_deployment_preflight


def test_phase6_preflight_refuses_sqlite_without_running_mysql_queries():
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(PreflightError, match="only accepts a MySQL connection; no SQL was run"):
            mysql_deployment_preflight(engine, migration_config=None, expected_tables=())
    finally:
        engine.dispose()


def test_phase6_mysql_preflight_passes_when_opt_in_database_is_configured(app):
    with app.app_context():
        if db.engine.dialect.name != "mysql":
            pytest.skip("Set RETAIL_GENIE_MYSQL_TEST_URL to a migrated disposable *_phase6_test MySQL database.")
        checks = mysql_deployment_preflight(
            db.engine,
            migrate.get_config(),
            db.metadata.tables.keys(),
        )
    assert checks
    assert all(check.passed for check in checks), [check for check in checks if not check.passed]
