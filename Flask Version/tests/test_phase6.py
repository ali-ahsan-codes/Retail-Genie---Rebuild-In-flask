"""Phase 6 deployment checks fail closed on non-MySQL targets."""


def test_phase6_preflight_refuses_sqlite_without_running_mysql_queries(app):
    result = app.test_cli_runner().invoke(args=["phase6-preflight"])

    assert result.exit_code != 0
    assert "only accepts a MySQL connection; no SQL was run" in result.output
    assert "mysql+pymysql" not in result.output
