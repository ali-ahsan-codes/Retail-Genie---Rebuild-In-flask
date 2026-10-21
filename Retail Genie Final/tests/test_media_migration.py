import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select

from retail_genie.extensions import db
from retail_genie.migrations.legacy_import import import_sqlite_database
from retail_genie.migrations.media import MediaMigrationError, migrate_legacy_media
from retail_genie.models import CatalogProduct, legacy_tables

SAMPLE_DATABASE = Path(__file__).resolve().parents[2] / "Node Js Version" / "netpos.db"


def _set_source_image(source: Path, product_id: str, image_path: str) -> None:
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            "UPDATE products SET imageUrl = ? WHERE id = ?",
            (image_path, product_id),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.commit()
    finally:
        connection.close()


def _source_with_product_image(tmp_path: Path, image_path: str) -> Path:
    source = tmp_path / "legacy-with-media.sqlite"
    shutil.copyfile(SAMPLE_DATABASE, source)
    _set_source_image(source, "prod_4", image_path)
    return source


def _import(app, source: Path) -> None:
    with app.app_context():
        import_sqlite_database(
            source,
            apply=True,
            password_policy="reset",
            company_id="test-company",
            store_id="test-store",
            allow_non_mysql_target=True,
        )


def _scoped_path(relative_path: str) -> str:
    container_hash = hashlib.sha256(b"test-container").hexdigest()
    company_hash = hashlib.sha256(b"test-company").hexdigest()
    return f"tenants/{container_hash}/companies/{company_hash}/{relative_path}"


def test_media_migration_dry_run_is_read_only_and_checks_source_files(app, tmp_path):
    source = _source_with_product_image(tmp_path, "/api/uploads/products/phone.png")
    source_uploads = tmp_path / "legacy-uploads"
    source_file = source_uploads / "products" / "phone.png"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"sample product image")

    with app.app_context():
        report = migrate_legacy_media(source, source_uploads)
        assert db.session.execute(
            select(legacy_tables["products"].c.image_url).where(legacy_tables["products"].c.id == "prod_4")
        ).scalar_one_or_none() is None

    assert report.source_references == 1
    assert report.local_references == 1
    assert report.unique_local_files == 1
    assert report.source_upload_files == 1
    assert report.unreferenced_files == 0
    assert report.missing_source_files == []
    assert report.copied_files == 0
    assert report.rewritten_target_references == 0


def test_media_migration_copies_verifies_and_namespaces_product_images(app, tmp_path):
    relative_path = "products/catalog/phone-4.png"
    source = _source_with_product_image(tmp_path, relative_path)
    source_uploads = tmp_path / "legacy-uploads"
    source_file = source_uploads / relative_path
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"verified media payload")
    destination = tmp_path / "flask-uploads"
    _import(app, source)

    with app.app_context():
        report = migrate_legacy_media(
            source,
            source_uploads,
            apply=True,
            company_id="test-company",
            destination_root=destination,
            allow_non_mysql_target=True,
        )
        legacy_path = db.session.execute(
            select(legacy_tables["products"].c.image_url).where(legacy_tables["products"].c.id == "prod_4")
        ).scalar_one()
        product = db.session.get(CatalogProduct, "prod_4")
        assert legacy_path == _scoped_path(relative_path)
        assert product.image_url == _scoped_path(relative_path)

        repeated = migrate_legacy_media(
            source,
            source_uploads,
            apply=True,
            company_id="test-company",
            destination_root=destination,
            allow_non_mysql_target=True,
        )

    expected_path = _scoped_path(relative_path)
    expected_file = destination / expected_path
    assert expected_file.read_bytes() == b"verified media payload"
    assert report.copied_files == 1
    assert report.already_present_files == 0
    assert report.rewritten_target_references == 2  # landing row + normalized catalog row
    assert report.already_rewritten_references == 0
    assert report.database_paths_verified == 2
    if os.name != "nt":
        assert (destination.stat().st_mode & 0o777) == 0o700
        assert (expected_file.stat().st_mode & 0o777) == 0o600

    assert repeated.copied_files == 0
    assert repeated.already_present_files == 1
    assert repeated.rewritten_target_references == 0
    assert repeated.already_rewritten_references == 2
    assert repeated.database_paths_verified == 2
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT imageUrl FROM products WHERE id = 'prod_4'").fetchone()[0] == relative_path


def test_media_migration_preserves_cloud_manifests_and_unreferenced_uploads(app, tmp_path):
    source = _source_with_product_image(tmp_path, "")
    source_uploads = tmp_path / "legacy-uploads"
    user_id = "user_admin"
    cloud_user_dir = source_uploads / "cloud" / user_id
    cloud_image = cloud_user_dir / "images" / "avatar.png"
    cloud_image.parent.mkdir(parents=True)
    cloud_image.write_bytes(b"legacy cloud image")
    metadata = {
        "file_id": "cloud-file-1",
        "userId": user_id,
        "original_filename": "avatar.png",
        "saved_filename": "avatar.png",
        "path": "images/avatar.png",
        "public_url": f"cloud/{user_id}/images/avatar.png",
        "file_type": "image/png",
        "file_size": len(b"legacy cloud image"),
        "upload_timestamp": "2025-01-01T00:00:00Z",
    }
    (cloud_user_dir / "cloud_files_metadata.ndjson").write_text(
        json.dumps(metadata) + "\n", encoding="utf-8"
    )
    orphan = source_uploads / "csv" / "legacy-export.csv"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("preserved,for,review\n", encoding="utf-8")
    destination = tmp_path / "flask-uploads"
    _import(app, source)

    with app.app_context():
        report = migrate_legacy_media(
            source,
            source_uploads,
            apply=True,
            company_id="test-company",
            destination_root=destination,
            allow_non_mysql_target=True,
        )

    cloud_relative_path = f"cloud/{user_id}/images/avatar.png"
    metadata_relative_path = f"cloud/{user_id}/cloud_files_metadata.ndjson"
    migrated_metadata = destination / _scoped_path(metadata_relative_path)
    metadata_row = json.loads(migrated_metadata.read_text(encoding="utf-8").strip())
    assert metadata_row["public_url"] == _scoped_path(cloud_relative_path)
    assert (destination / metadata_row["public_url"]).read_bytes() == b"legacy cloud image"
    assert (destination / _scoped_path("csv/legacy-export.csv")).read_text(encoding="utf-8") == "preserved,for,review\n"
    assert report.cloud_file_references == 1
    assert report.cloud_metadata_files == 1
    assert report.source_upload_files == 3
    assert report.unreferenced_files == 1
    assert report.copied_files == 3
    assert report.cloud_paths_verified == 1
    assert report.database_paths_verified == 0


def test_media_migration_missing_source_file_does_not_change_database_or_copy(app, tmp_path):
    relative_path = "products/missing.png"
    source = _source_with_product_image(tmp_path, relative_path)
    source_uploads = tmp_path / "legacy-uploads"
    source_uploads.mkdir()
    destination = tmp_path / "flask-uploads"
    _import(app, source)

    with app.app_context(), pytest.raises(MediaMigrationError, match="missing 1 referenced file"):
        migrate_legacy_media(
            source,
            source_uploads,
            apply=True,
            company_id="test-company",
            destination_root=destination,
            allow_non_mysql_target=True,
        )

    with app.app_context():
        legacy_path = db.session.execute(
            select(legacy_tables["products"].c.image_url).where(legacy_tables["products"].c.id == "prod_4")
        ).scalar_one()
        product = db.session.get(CatalogProduct, "prod_4")
        assert legacy_path == relative_path
        assert product.image_url == relative_path
    assert not destination.exists()


def test_media_migration_rejects_path_traversal_and_symlinks(app, tmp_path):
    traversal_source = _source_with_product_image(tmp_path, "../../outside.png")
    uploads = tmp_path / "legacy-uploads"
    uploads.mkdir()

    with app.app_context(), pytest.raises(MediaMigrationError, match="unsafe relative path"):
        migrate_legacy_media(traversal_source, uploads)

    symlink_source = _source_with_product_image(tmp_path, "products/link.png")
    target = tmp_path / "outside.png"
    target.write_bytes(b"outside")
    product_dir = uploads / "products"
    product_dir.mkdir()
    try:
        (product_dir / "link.png").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("The current filesystem does not permit symlink creation.")

    with app.app_context(), pytest.raises(MediaMigrationError, match="symbolic link"):
        migrate_legacy_media(symlink_source, uploads)


def test_media_migration_preserves_remote_and_embedded_product_images(app, tmp_path):
    source = _source_with_product_image(tmp_path, "https://cdn.example.test/products/external.png")
    _set_source_image(source, "prod_5", "data:image/png;base64,AAAA")
    uploads = tmp_path / "legacy-uploads"
    uploads.mkdir()

    with app.app_context():
        report = migrate_legacy_media(source, uploads)

    assert report.source_references == 2
    assert report.local_references == 0
    assert report.unique_local_files == 0
    assert report.external_references == 1
    assert report.embedded_references == 1
    assert report.missing_source_files == []


def test_media_cli_reports_dry_run_and_requires_explicit_confirmation(app, tmp_path):
    relative_path = "products/cli.png"
    source = _source_with_product_image(tmp_path, relative_path)
    uploads = tmp_path / "legacy-uploads"
    source_file = uploads / relative_path
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"cli media")

    runner = app.test_cli_runner()
    dry_run = runner.invoke(
        args=["migrate-media", "--source", str(source), "--source-uploads", str(uploads)]
    )
    assert dry_run.exit_code == 0
    assert "DRY RUN" in dry_run.output
    assert "unique_files=1" in dry_run.output

    refused = runner.invoke(
        args=[
            "migrate-media",
            "--source",
            str(source),
            "--source-uploads",
            str(uploads),
            "--company-id",
            "test-company",
            "--apply",
        ]
    )
    assert refused.exit_code != 0
    assert "--confirm-apply" in refused.output
