import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import func, select

from retail_genie.extensions import db
from retail_genie.migrations.legacy_import import (
    LegacyImportError,
    _financial_reconciliation,
    import_sqlite_database,
)
from retail_genie.models import User, legacy_tables

SAMPLE_DATABASE = Path(__file__).resolve().parents[2] / "Node Js Version" / "netpos.db"


def test_read_only_dry_run_maps_all_legacy_tables_without_writing(app):
    with app.app_context():
        report = import_sqlite_database(SAMPLE_DATABASE)

        assert report.dry_run is True
        assert len(report.source_counts) == 27
        assert report.source_counts["users"] == 12
        assert report.source_counts["products"] == 8
        assert report.source_counts["orders"] == 1
        assert report.source_counts["demand_notices"] == 2
        assert report.user_passwords_reset == 12
        assert report.user_passwords_hashed == 0
        assert report.reconciliation["orders"]["rows"] == 1
        assert report.reconciliation["stock"]["product_rows"] == 8
        assert report.reconciliation["invoice_counters"]["rows"] == 5
        assert User.query.count() == 0
        assert db.session.execute(select(func.count()).select_from(legacy_tables["products"])).scalar_one() == 0


def test_import_hashes_reset_accounts_preserves_ids_and_is_repeatable(app):
    with app.app_context():
        first = import_sqlite_database(
            SAMPLE_DATABASE,
            apply=True,
            password_policy="reset",
            allow_non_mysql_target=True,
        )
        assert sum(first.inserted_counts.values()) == 32
        assert first.reconciliation["orders"]["rows"] == 1
        assert first.reconciliation["payments"]["combined_total_omr"] == "0.000"
        assert first.user_passwords_reset == 12
        assert first.user_passwords_hashed == 0

        imported_users = User.query.order_by(User.username.asc()).all()
        assert len(imported_users) == 12
        assert all(user.password_hash.startswith("$argon2id$") for user in imported_users)
        assert all(user.force_password_change is True for user in imported_users)
        assert all(user.is_active is True for user in imported_users)
        assert db.session.execute(select(func.count()).select_from(legacy_tables["orders"])).scalar_one() == 1
        assert db.session.execute(select(func.count()).select_from(legacy_tables["demand_notices"])).scalar_one() == 2

        second = import_sqlite_database(
            SAMPLE_DATABASE,
            apply=True,
            password_policy="reset",
            allow_non_mysql_target=True,
        )
        assert sum(second.inserted_counts.values()) == 0
        assert sum(second.skipped_counts.values()) == 32
        assert second.reconciliation == first.reconciliation
        assert User.query.count() == 12


def test_target_conflict_rolls_back_whole_import_without_overwriting(app):
    source = sqlite3.connect(SAMPLE_DATABASE.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        product_id = source.execute('SELECT id FROM products LIMIT 1').fetchone()[0]
    finally:
        source.close()

    with app.app_context():
        db.session.execute(
            legacy_tables["products"].insert().values(id=product_id, name="Existing target record")
        )
        db.session.commit()

        with pytest.raises(LegacyImportError, match="Target row conflict"):
            import_sqlite_database(
                SAMPLE_DATABASE,
                apply=True,
                password_policy="reset",
                allow_non_mysql_target=True,
            )

        assert User.query.count() == 0
        existing = db.session.execute(
            select(legacy_tables["products"].c.name).where(legacy_tables["products"].c.id == product_id)
        ).scalar_one()
        assert existing == "Existing target record"


def test_cli_import_is_dry_run_by_default_and_requires_apply_confirmation(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["import-sqlite", "--source", str(SAMPLE_DATABASE)])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert "source=12" in result.output
    assert "reset=12" in result.output
    assert "password_hash" not in result.output

    refused = runner.invoke(args=["import-sqlite", "--source", str(SAMPLE_DATABASE), "--apply"])
    assert refused.exit_code != 0
    assert "--confirm-apply" in refused.output
    with app.app_context():
        assert User.query.count() == 0


def test_hash_policy_dry_run_counts_vetted_passwords_without_logging_them(app):
    with app.app_context():
        report = import_sqlite_database(SAMPLE_DATABASE, password_policy="hash")

    assert report.dry_run is True
    assert report.user_passwords_hashed == 11
    assert report.user_passwords_reset == 1


def test_payment_and_financial_reconciliation_sums_structured_legacy_json():
    report = _financial_reconciliation(
        {
            "orders": [
                {
                    "subtotal": 10.125,
                    "discount_amount": 0.125,
                    "total_amount": 10.0,
                    "payments": [{"amount": 3.25}, {"amount": 1.5}],
                }
            ],
            "demand_notices": [{"payments": [{"amount": "0.750"}]}],
            "products": [{"quantity_in_stock": 4}, {"quantity_in_stock": 7}],
            "invoice_number_settings": [{"next_number": 120}, {"next_number": 5}],
        }
    )

    assert report["orders"]["total_omr"] == "10.000"
    assert report["payments"]["combined_total_omr"] == "5.500"
    assert report["stock"]["quantity_total"] == 11
    assert report["invoice_counters"]["next_number_total"] == 125


def test_unmapped_sqlite_file_is_rejected_before_target_mutation(app, tmp_path):
    source = tmp_path / "wrong-schema.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unrelated (id TEXT PRIMARY KEY)")

    with app.app_context(), pytest.raises(LegacyImportError, match="does not match the reviewed"):
        import_sqlite_database(source, apply=True, allow_non_mysql_target=True)

    with app.app_context():
        assert User.query.count() == 0
