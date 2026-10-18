"""Company-scoped, verified migration of legacy uploads into Flask storage.

The SQLite source is opened read-only. Files are copied to a private
container/company namespace, then matching MySQL path metadata is updated in a
single database transaction. Existing files are never overwritten unless the
contents are identical; missing, unsafe, or conflicting paths abort the update.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit

from flask import current_app
from sqlalchemy import select, update

from ..extensions import db
from ..models import CatalogProduct, Company, User, legacy_tables
from .legacy_import import LegacyImportError, _open_sqlite_snapshot, _validate_source_schema


class MediaMigrationError(RuntimeError):
    """Legacy media cannot be migrated without risking data or path safety."""


@dataclass(frozen=True)
class MediaField:
    table_name: str
    source_column: str
    target_column: str
    allow_data_uri: bool = False


# Columns that contain a file path relative to the old Node application's
# uploads/ directory. Embedded or external product image URLs are preserved as
# metadata and are deliberately not mistaken for local files.
MEDIA_FIELDS: tuple[MediaField, ...] = (
    MediaField("attachments", "file_path", "file_path"),
    MediaField("attendance_logs", "selfieImagePath", "selfie_image_path"),
    MediaField("audit_images", "imagePath", "image_path"),
    MediaField("audits", "auditorSelfiePath", "auditor_selfie_path"),
    MediaField("po_attachments", "file_path", "file_path"),
    MediaField("products", "imageUrl", "image_url", allow_data_uri=True),
    MediaField("purchase_orders", "invoice_path", "invoice_path"),
    MediaField("supplier_attachments", "file_path", "file_path"),
    MediaField("supplier_products", "document_path", "document_path"),
)


@dataclass(frozen=True)
class _MediaReference:
    field: MediaField
    row_id: str
    original_value: str
    relative_path: str


@dataclass(frozen=True)
class _SourceFile:
    path: Path | None
    sha256: str
    size_bytes: int
    content: bytes | None = None


@dataclass
class MediaMigrationReport:
    source_references: int = 0
    local_references: int = 0
    unique_local_files: int = 0
    cloud_file_references: int = 0
    cloud_metadata_files: int = 0
    orphaned_cloud_users: list[str] = field(default_factory=list)
    source_upload_files: int = 0
    unreferenced_files: int = 0
    external_references: int = 0
    embedded_references: int = 0
    missing_source_files: list[str] = field(default_factory=list)
    copied_files: int = 0
    already_present_files: int = 0
    rewritten_target_references: int = 0
    already_rewritten_references: int = 0
    database_paths_verified: int = 0
    cloud_paths_verified: int = 0


@dataclass(frozen=True)
class _CloudMetadataFile:
    relative_path: str
    user_id: str
    entries: tuple[tuple[dict[str, Any], str], ...]
    raw_content: bytes


@dataclass
class _MediaPlan:
    references: list[_MediaReference]
    source_files: dict[str, _SourceFile]
    cloud_metadata: list[_CloudMetadataFile]
    cloud_paths: list[str]
    report: MediaMigrationReport


def _classify_value(field: MediaField, value: Any, *, row_id: str) -> tuple[str, str | None]:
    if value is None or value == "":
        return "empty", None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MediaMigrationError(
                f"Legacy media reference {field.table_name}:{row_id} is not valid UTF-8."
            ) from exc
    if not isinstance(value, str):
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} is not a text path."
        )

    raw = value.strip()
    if not raw:
        return "empty", None
    if "\x00" in raw:
        raise MediaMigrationError(f"Legacy media reference {field.table_name}:{row_id} contains a null byte.")

    if raw.lower().startswith("data:"):
        if field.allow_data_uri:
            return "embedded", None
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} embeds data where a file path is expected."
        )

    # Product records may contain a remote image URL. It is retained but is not
    # copied or treated as a filesystem path.
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return "external", None
    if parsed.scheme or parsed.netloc:
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} uses an unsupported URL scheme."
        )
    if parsed.query or parsed.fragment:
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} has an ambiguous query or fragment."
        )

    try:
        decoded = unquote(parsed.path, encoding="utf-8", errors="strict").replace("\\", "/")
    except UnicodeDecodeError as exc:
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} contains invalid URL-encoded UTF-8."
        ) from exc
    if PureWindowsPath(decoded).is_absolute() or re.match(r"^[A-Za-z]:", decoded) or decoded.startswith("//"):
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} is an absolute path; use a reviewed uploads-root-relative path."
        )

    # Accept historical public route spellings, but normalize stored metadata
    # to a path relative to the uploads root.
    for prefix in ("/api/uploads/", "api/uploads/", "/uploads/", "uploads/"):
        if decoded.startswith(prefix):
            decoded = decoded[len(prefix) :]
            break
    if decoded.startswith("/"):
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} is outside the uploads root."
        )

    parts = decoded.split("/")
    if not decoded or any(part in {"", ".", ".."} for part in parts):
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} has an unsafe relative path."
        )
    if any("\x00" in part or ":" in part for part in parts):
        raise MediaMigrationError(
            f"Legacy media reference {field.table_name}:{row_id} contains an unsupported path component."
        )
    return "local", PurePosixPath(*parts).as_posix()


def _resolve_existing_file(root: Path, relative_path: str, *, label: str) -> Path:
    root_path = root.resolve(strict=True)
    candidate = root_path.joinpath(*PurePosixPath(relative_path).parts)
    current = root_path
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise MediaMigrationError(f"{label} contains a symbolic link at '{relative_path}'.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise
    except OSError as exc:
        raise MediaMigrationError(f"{label} path '{relative_path}' cannot be inspected safely.") from exc
    if not resolved.is_relative_to(root_path):
        raise MediaMigrationError(f"{label} path '{relative_path}' escapes its configured root.")
    if not resolved.is_file():
        raise MediaMigrationError(f"{label} path '{relative_path}' is not a regular file.")
    return resolved


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _scan_cloud_metadata(
    source_root: Path,
    source_user_ids: set[str],
    report: MediaMigrationReport,
) -> tuple[list[_CloudMetadataFile], list[str]]:
    """Read legacy per-user cloud manifests and verify their referenced files."""
    cloud_root = source_root / "cloud"
    if not cloud_root.exists():
        return [], []
    if cloud_root.is_symlink() or not cloud_root.is_dir():
        raise MediaMigrationError("The legacy cloud uploads directory is not a safe directory.")

    cloud_files: list[_CloudMetadataFile] = []
    cloud_paths: list[str] = []
    metadata_field = MediaField("cloud_files_metadata.ndjson", "path", "path")
    for user_directory in sorted(cloud_root.iterdir(), key=lambda item: item.name):
        if user_directory.is_symlink():
            raise MediaMigrationError("The legacy cloud uploads tree contains a symbolic link.")
        if not user_directory.is_dir():
            continue
        user_id = user_directory.name
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id):
            raise MediaMigrationError("A legacy cloud user directory has an unsafe name.")
        if user_id not in source_user_ids:
            report.orphaned_cloud_users.append(user_id)

        metadata_path = user_directory / "cloud_files_metadata.ndjson"
        if not metadata_path.exists():
            continue
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise MediaMigrationError(f"Cloud metadata for user '{user_id}' is not a regular file.")
        relative_metadata_path = metadata_path.relative_to(source_root).as_posix()
        try:
            raw_content = metadata_path.read_bytes()
            text_content = raw_content.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise MediaMigrationError(f"Cloud metadata for user '{user_id}' is unreadable or invalid UTF-8.") from exc

        entries: list[tuple[dict[str, Any], str]] = []
        for line_number, line in enumerate(text_content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MediaMigrationError(
                    f"Cloud metadata for user '{user_id}' has invalid JSON on line {line_number}."
                ) from exc
            if not isinstance(entry, dict):
                raise MediaMigrationError(
                    f"Cloud metadata for user '{user_id}' has a non-object record on line {line_number}."
                )
            entry_user_id = entry.get("userId") or user_id
            if str(entry_user_id) != user_id:
                raise MediaMigrationError(
                    f"Cloud metadata for user '{user_id}' contains a different owner on line {line_number}."
                )
            kind, relative_to_user = _classify_value(
                metadata_field,
                entry.get("path"),
                row_id=f"{user_id}:{line_number}",
            )
            if kind != "local" or relative_to_user is None:
                raise MediaMigrationError(
                    f"Cloud metadata for user '{user_id}' has no safe local path on line {line_number}."
                )
            source_relative_path = PurePosixPath("cloud", user_id, relative_to_user).as_posix()
            entries.append((entry, source_relative_path))
            cloud_paths.append(source_relative_path)
            report.cloud_file_references += 1

        cloud_files.append(
            _CloudMetadataFile(
                relative_path=relative_metadata_path,
                user_id=user_id,
                entries=tuple(entries),
                raw_content=raw_content,
            )
        )
        report.cloud_metadata_files += 1
    return cloud_files, cloud_paths


def _scan_upload_files(source_root: Path) -> dict[str, _SourceFile]:
    """Hash every regular file so orphaned legacy uploads are preserved too."""
    result: dict[str, _SourceFile] = {}

    def fail_walk(error: OSError) -> None:
        raise MediaMigrationError("The legacy uploads tree could not be scanned safely.") from error

    for directory_name, directory_names, file_names in os.walk(source_root, followlinks=False, onerror=fail_walk):
        directory = Path(directory_name)
        for name in directory_names:
            candidate_directory = directory / name
            if candidate_directory.is_symlink() or not candidate_directory.is_dir():
                raise MediaMigrationError("The legacy uploads tree contains a symbolic link or non-directory entry.")
        for name in file_names:
            candidate = directory / name
            if candidate.is_symlink():
                raise MediaMigrationError("The legacy uploads tree contains a symbolic link.")
            relative_path = candidate.relative_to(source_root).as_posix()
            parts = PurePosixPath(relative_path).parts
            if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
                raise MediaMigrationError("The legacy uploads tree contains an unsafe file name.")
            try:
                resolved = _resolve_existing_file(source_root, relative_path, label="Legacy uploads")
            except FileNotFoundError as exc:
                raise MediaMigrationError(f"Legacy upload '{relative_path}' disappeared during preflight.") from exc
            digest, size = _sha256_file(resolved)
            result[relative_path] = _SourceFile(path=resolved, sha256=digest, size_bytes=size)
    return result


def _build_plan(source_path: str | Path, source_uploads: str | Path) -> _MediaPlan:
    source_root = Path(source_uploads).expanduser()
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise MediaMigrationError("The legacy uploads directory does not exist or cannot be resolved.") from exc
    if not source_root.is_dir():
        raise MediaMigrationError("The legacy uploads path must be a directory.")

    references: list[_MediaReference] = []
    source_user_ids: set[str] = set()
    report = MediaMigrationReport()
    try:
        connection = _open_sqlite_snapshot(source_path)
    except Exception as exc:
        if isinstance(exc, MediaMigrationError):
            raise
        raise MediaMigrationError("The legacy SQLite snapshot could not be opened safely.") from exc
    try:
        _validate_source_schema(connection)
        source_user_ids = {
            str(row[0]) for row in connection.execute('SELECT "id" FROM "users"')
        }
        for media_field in MEDIA_FIELDS:
            table_name = media_field.table_name
            query = (
                f'SELECT "id", "{media_field.source_column}" '
                f'FROM "{table_name}" WHERE "{media_field.source_column}" IS NOT NULL '
                f'AND "{media_field.source_column}" != \'\''
            )
            for row in connection.execute(query):
                row_id = str(row["id"])
                report.source_references += 1
                raw_value = row[media_field.source_column]
                kind, relative_path = _classify_value(media_field, raw_value, row_id=row_id)
                if kind == "external":
                    report.external_references += 1
                elif kind == "embedded":
                    report.embedded_references += 1
                elif kind == "local" and relative_path is not None:
                    report.local_references += 1
                    original_value = raw_value.decode("utf-8") if isinstance(raw_value, bytes) else str(raw_value)
                    references.append(
                        _MediaReference(
                            field=media_field,
                            row_id=row_id,
                            original_value=original_value,
                            relative_path=relative_path,
                        )
                    )
    except LegacyImportError as exc:
        raise MediaMigrationError(f"The legacy SQLite schema is not eligible for media migration: {exc}") from exc
    except sqlite3.Error as exc:
        raise MediaMigrationError("The legacy media references could not be read from the SQLite snapshot.") from exc
    finally:
        connection.close()

    cloud_metadata, cloud_paths = _scan_cloud_metadata(source_root, source_user_ids, report)
    source_files = _scan_upload_files(source_root)
    for metadata in cloud_metadata:
        for entry, relative_path in metadata.entries:
            source_file = source_files.get(relative_path)
            declared_size = entry.get("file_size")
            if source_file is not None and declared_size is not None:
                if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size != source_file.size_bytes:
                    raise MediaMigrationError(
                        f"Cloud file size does not reconcile for user '{metadata.user_id}' at '{relative_path}'."
                    )
    report.orphaned_cloud_users.sort()
    report.source_upload_files = len(source_files)
    report.unique_local_files = len({reference.relative_path for reference in references})

    required_paths = {reference.relative_path for reference in references}
    required_paths.update(cloud_paths)
    required_paths.update(metadata.relative_path for metadata in cloud_metadata)
    report.missing_source_files = sorted(path for path in required_paths if path not in source_files)
    report.unreferenced_files = len(set(source_files) - required_paths)

    return _MediaPlan(
        references=references,
        source_files=source_files,
        cloud_metadata=cloud_metadata,
        cloud_paths=cloud_paths,
        report=report,
    )


def _scope_prefix(tenant_container_id: str, company_id: str) -> PurePosixPath:
    container_key = hashlib.sha256(tenant_container_id.encode("utf-8")).hexdigest()
    company_key = hashlib.sha256(company_id.encode("utf-8")).hexdigest()
    return PurePosixPath("tenants", container_key, "companies", company_key)


def _destination_relative_path(
    relative_path: str,
    *,
    tenant_container_id: str,
    company_id: str,
) -> str:
    prefix = _scope_prefix(tenant_container_id, company_id)
    path = PurePosixPath(relative_path)
    parts = path.parts
    if parts and parts[0] == "tenants":
        if path.is_relative_to(prefix):
            return path.as_posix()
        raise MediaMigrationError("A legacy media path is already namespaced to a different tenant/company.")
    return (prefix / path).as_posix()


def _configured_uploads_root(configured: str | Path | None = None) -> Path:
    if configured is None:
        configured = current_app.config.get("UPLOADS_DIR")
    if not configured:
        raise MediaMigrationError("UPLOADS_DIR is not configured.")
    root = Path(configured).expanduser()
    if not root.is_absolute():
        root = Path(current_app.root_path).parent / root
    root = root.resolve(strict=False)
    static_folder = Path(current_app.static_folder).resolve()
    if root == static_folder or static_folder in root.parents:
        raise MediaMigrationError("UPLOADS_DIR must be outside Flask's public static directory.")
    return root


def _ensure_private_directory(path: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        root.chmod(0o700)
    current = root
    relative = path.relative_to(root)
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise MediaMigrationError("UPLOADS_DIR contains a symbolic link in the destination path.")
        current.mkdir(mode=0o700, exist_ok=True)
        if not current.is_dir():
            raise MediaMigrationError("UPLOADS_DIR contains a non-directory path component.")
        if os.name != "nt":
            current.chmod(0o700)
        if not current.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise MediaMigrationError("UPLOADS_DIR destination escapes its configured root.")


def _destination_file(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise MediaMigrationError(f"Destination media path '{relative_path}' contains a symbolic link.")
    if not candidate.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
        raise MediaMigrationError(f"Destination media path '{relative_path}' escapes UPLOADS_DIR.")
    return candidate


def _prepare_cloud_metadata(
    plan: _MediaPlan,
    new_paths: dict[str, str],
) -> None:
    """Rewrite legacy cloud manifest URLs to the new scoped upload locations."""
    for metadata in plan.cloud_metadata:
        if not metadata.entries:
            content = metadata.raw_content
        else:
            lines: list[str] = []
            for entry, source_relative_path in metadata.entries:
                migrated_entry = dict(entry)
                if not migrated_entry.get("userId"):
                    migrated_entry["userId"] = metadata.user_id
                migrated_entry["public_url"] = new_paths[source_relative_path]
                lines.append(json.dumps(migrated_entry, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
            content = ("\n".join(lines) + "\n").encode("utf-8")

        digest = hashlib.sha256(content).hexdigest()
        plan.source_files[metadata.relative_path] = _SourceFile(
            path=None,
            sha256=digest,
            size_bytes=len(content),
            content=content,
        )


def _copy_verified_file(source: _SourceFile, destination: Path) -> bool:
    """Copy to a same-directory temporary file, then install without overwrite."""
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise MediaMigrationError("A destination media path exists but is not a regular file.")
        existing_hash, existing_size = _sha256_file(destination)
        if existing_hash != source.sha256 or existing_size != source.size_bytes:
            raise MediaMigrationError(
                f"Destination media conflict at '{destination.name}'; refusing to overwrite different content."
            )
        return False

    if source.content is None and source.path is None:
        raise MediaMigrationError("A planned upload has no readable source content.")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".media-", suffix=".partial", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        digest = hashlib.sha256()
        size = 0
        source_stream = io.BytesIO(source.content) if source.content is not None else source.path.open("rb")
        with os.fdopen(descriptor, "wb") as target, source_stream:
            for chunk in iter(lambda: source_stream.read(1024 * 1024), b""):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        if digest.hexdigest() != source.sha256 or size != source.size_bytes:
            raise MediaMigrationError("A source upload changed while it was being copied; retry from a closed snapshot.")
        if os.name != "nt":
            temporary.chmod(0o600)

        try:
            # Hard-link creation is atomic and refuses to replace a destination
            # that appeared after preflight.
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or not destination.is_file():
                raise MediaMigrationError("A destination media path changed during migration.")
            existing_hash, existing_size = _sha256_file(destination)
            if existing_hash != source.sha256 or existing_size != source.size_bytes:
                raise MediaMigrationError("A destination media conflict appeared during migration.")
            return False
        except OSError as exc:
            raise MediaMigrationError("Could not atomically install a migrated upload in UPLOADS_DIR.") from exc
        return True
    except OSError as exc:
        raise MediaMigrationError("A legacy upload could not be copied to UPLOADS_DIR.") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            current_app.logger.exception("Could not remove a temporary media migration file")


def _read_target_media_value(connection, media_field: MediaField, reference: _MediaReference, tenant_id: str, company_id: str):
    table = legacy_tables[media_field.table_name]
    column = table.c[media_field.target_column]
    row = connection.execute(
        select(column).where(
            table.c.id == reference.row_id,
            table.c.tenant_container_id == tenant_id,
            table.c.company_id == company_id,
        )
    ).first()
    if row is None:
        raise MediaMigrationError(
            f"Imported target row {media_field.table_name}:{reference.row_id} is missing from the selected company."
        )
    return row[0]


def _target_product_image_value(connection, reference: _MediaReference, tenant_id: str, company_id: str):
    table = CatalogProduct.__table__
    row = connection.execute(
        select(table.c.image_url).where(
            table.c.id == reference.row_id,
            table.c.tenant_container_id == tenant_id,
            table.c.company_id == company_id,
        )
    ).first()
    if row is None:
        raise MediaMigrationError(
            f"Normalized catalog product {reference.row_id} is missing from the selected company."
        )
    return row[0]


def _validate_target_cloud_owners(connection, plan: _MediaPlan, company_id: str) -> None:
    user_table = User.__table__
    orphaned_users = set(plan.report.orphaned_cloud_users)
    for user_id in {metadata.user_id for metadata in plan.cloud_metadata} - orphaned_users:
        imported_user = connection.execute(
            select(user_table.c.id).where(
                user_table.c.id == user_id,
                user_table.c.company_id == company_id,
            )
        ).scalar_one_or_none()
        if imported_user is None:
            raise MediaMigrationError(
                f"Cloud files for user '{user_id}' have no matching imported account in the selected company."
            )


def _validate_target_values(
    connection,
    references: list[_MediaReference],
    new_paths: dict[str, str],
    tenant_id: str,
    company_id: str,
) -> tuple[int, int]:
    already = 0
    for reference in references:
        target_path = new_paths[reference.relative_path]
        current = _read_target_media_value(
            connection, reference.field, reference, tenant_id, company_id
        )
        if current == target_path:
            already += 1
        elif current != reference.original_value:
            raise MediaMigrationError(
                f"Imported target path conflicts at {reference.field.table_name}:{reference.row_id}; no metadata was updated."
            )

        if reference.field.table_name == "products":
            catalog_value = _target_product_image_value(connection, reference, tenant_id, company_id)
            if catalog_value == target_path:
                already += 1
            elif catalog_value != reference.original_value:
                raise MediaMigrationError(
                    f"Normalized catalog image path conflicts for product {reference.row_id}."
                )
    return already, len(references)


def _update_target_values(
    connection,
    references: list[_MediaReference],
    new_paths: dict[str, str],
    tenant_id: str,
    company_id: str,
) -> tuple[int, int]:
    rewritten = 0
    already = 0
    for reference in references:
        target_path = new_paths[reference.relative_path]
        table = legacy_tables[reference.field.table_name]
        column = table.c[reference.field.target_column]
        current = _read_target_media_value(
            connection, reference.field, reference, tenant_id, company_id
        )
        if current == reference.original_value:
            result = connection.execute(
                update(table)
                .where(
                    table.c.id == reference.row_id,
                    table.c.tenant_container_id == tenant_id,
                    table.c.company_id == company_id,
                    column == reference.original_value,
                )
                .values({reference.field.target_column: target_path})
            )
            if result.rowcount != 1:
                raise MediaMigrationError(
                    f"Imported target path changed during migration at {reference.field.table_name}:{reference.row_id}."
                )
            rewritten += 1
        elif current == target_path:
            already += 1
        else:
            raise MediaMigrationError(
                f"Imported target path changed during migration at {reference.field.table_name}:{reference.row_id}."
            )

        if reference.field.table_name == "products":
            catalog_table = CatalogProduct.__table__
            catalog_column = catalog_table.c.image_url
            catalog_value = _target_product_image_value(connection, reference, tenant_id, company_id)
            if catalog_value == reference.original_value:
                result = connection.execute(
                    update(catalog_table)
                    .where(
                        catalog_table.c.id == reference.row_id,
                        catalog_table.c.tenant_container_id == tenant_id,
                        catalog_table.c.company_id == company_id,
                        catalog_column == reference.original_value,
                    )
                    .values(image_url=target_path)
                )
                if result.rowcount != 1:
                    raise MediaMigrationError(
                        f"Normalized catalog image path changed during migration for product {reference.row_id}."
                    )
                rewritten += 1
            elif catalog_value == target_path:
                already += 1
            else:
                raise MediaMigrationError(
                    f"Normalized catalog image path changed during migration for product {reference.row_id}."
                )
    return rewritten, already


def _verify_target_paths(connection, root: Path, tenant_id: str, company_id: str) -> int:
    verified_references = 0
    for media_field in MEDIA_FIELDS:
        table = legacy_tables[media_field.table_name]
        column = table.c[media_field.target_column]
        rows = connection.execute(
            select(table.c.id, column).where(
                table.c.tenant_container_id == tenant_id,
                table.c.company_id == company_id,
                column.is_not(None),
                column != "",
            )
        ).all()
        for row in rows:
            row_id = str(row[0])
            kind, relative_path = _classify_value(media_field, row[1], row_id=row_id)
            if kind != "local" or relative_path is None:
                continue
            prefix = _scope_prefix(tenant_id, company_id)
            if not PurePosixPath(relative_path).is_relative_to(prefix):
                raise MediaMigrationError(
                    f"Target media reference {media_field.table_name}:{row_id} is not isolated to its tenant/company path."
                )
            try:
                _resolve_existing_file(root, relative_path, label="Migrated uploads")
            except FileNotFoundError as exc:
                raise MediaMigrationError(
                    f"Target database path {media_field.table_name}:{row_id} does not resolve to a file in UPLOADS_DIR."
                ) from exc
            verified_references += 1

    catalog_table = CatalogProduct.__table__
    rows = connection.execute(
        select(catalog_table.c.id, catalog_table.c.image_url).where(
            catalog_table.c.tenant_container_id == tenant_id,
            catalog_table.c.company_id == company_id,
            catalog_table.c.image_url.is_not(None),
            catalog_table.c.image_url != "",
        )
    ).all()
    product_field = next(field for field in MEDIA_FIELDS if field.table_name == "products")
    for row in rows:
        product_id = str(row[0])
        kind, relative_path = _classify_value(product_field, row[1], row_id=product_id)
        if kind != "local" or relative_path is None:
            continue
        prefix = _scope_prefix(tenant_id, company_id)
        if not PurePosixPath(relative_path).is_relative_to(prefix):
            raise MediaMigrationError(
                f"Catalog image path for product {product_id} is not isolated to its tenant/company path."
            )
        try:
            _resolve_existing_file(root, relative_path, label="Migrated uploads")
        except FileNotFoundError as exc:
            raise MediaMigrationError(
                f"Catalog image path for product {product_id} does not resolve to a file in UPLOADS_DIR."
            ) from exc
        verified_references += 1
    return verified_references


def _verify_cloud_uploads(
    root: Path,
    plan: _MediaPlan,
    new_paths: dict[str, str],
) -> int:
    """Verify copied cloud assets and the migrated per-user manifests."""
    verified = 0
    for source_relative in plan.cloud_paths:
        target_relative = new_paths[source_relative]
        try:
            _resolve_existing_file(root, target_relative, label="Migrated cloud uploads")
        except FileNotFoundError as exc:
            raise MediaMigrationError(
                f"Cloud metadata path '{source_relative}' does not resolve after migration."
            ) from exc
        verified += 1

    for metadata in plan.cloud_metadata:
        target_metadata_path = new_paths[metadata.relative_path]
        try:
            metadata_file = _resolve_existing_file(root, target_metadata_path, label="Migrated cloud metadata")
            lines = metadata_file.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError, UnicodeDecodeError) as exc:
            raise MediaMigrationError(
                f"Migrated cloud metadata for user '{metadata.user_id}' cannot be read."
            ) from exc
        actual_entries = [line for line in lines if line.strip()]
        if len(actual_entries) != len(metadata.entries):
            raise MediaMigrationError(
                f"Migrated cloud metadata for user '{metadata.user_id}' does not reconcile."
            )
        public_field = MediaField("cloud_files_metadata.ndjson", "public_url", "public_url")
        for line_number, (line, (_original_entry, source_relative_path)) in enumerate(
            zip(actual_entries, metadata.entries), start=1
        ):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MediaMigrationError(
                    f"Migrated cloud metadata for user '{metadata.user_id}' is invalid on line {line_number}."
                ) from exc
            if not isinstance(entry, dict) or entry.get("userId") != metadata.user_id:
                raise MediaMigrationError(
                    f"Migrated cloud metadata for user '{metadata.user_id}' has an invalid owner."
                )
            kind, public_path = _classify_value(
                public_field,
                entry.get("public_url"),
                row_id=f"{metadata.user_id}:{line_number}",
            )
            if kind != "local" or public_path != new_paths[source_relative_path]:
                raise MediaMigrationError(
                    f"Migrated cloud metadata for user '{metadata.user_id}' has an invalid scoped URL."
                )
            try:
                _resolve_existing_file(root, public_path, label="Migrated cloud uploads")
            except FileNotFoundError as exc:
                raise MediaMigrationError(
                    f"Migrated cloud URL for user '{metadata.user_id}' does not resolve to a file."
                ) from exc
    return verified


def migrate_legacy_media(
    source_path: str | Path,
    source_uploads: str | Path,
    *,
    apply: bool = False,
    company_id: str | None = None,
    destination_root: str | Path | None = None,
    allow_non_mysql_target: bool = False,
) -> MediaMigrationReport:
    """Preflight or apply a verified legacy media migration.

    Dry-run mode reads only the immutable SQLite snapshot and source uploads.
    Applying requires the legacy rows to have already been imported, identifies
    one target company, copies media to that company's private path namespace,
    and updates its database references transactionally.

    ``allow_non_mysql_target`` is reserved for isolated SQLite tests. The Flask
    CLI never enables it; operational media migrations must target MySQL.
    """
    plan = _build_plan(source_path, source_uploads)
    report = plan.report
    if not apply:
        return report
    if report.missing_source_files:
        sample = ", ".join(report.missing_source_files[:5])
        raise MediaMigrationError(
            f"The legacy uploads directory is missing {len(report.missing_source_files)} referenced file(s): {sample}."
        )
    if not company_id:
        raise MediaMigrationError("Applying media migration requires an explicit --company-id.")

    dialect = db.engine.dialect.name
    if dialect not in {"mysql", "mariadb"} and not allow_non_mysql_target:
        raise MediaMigrationError("Applying a media migration requires a MySQL or MariaDB target database.")

    company_table = Company.__table__
    with db.engine.connect() as connection:
        tenant_id = connection.execute(
            select(company_table.c.tenant_container_id).where(company_table.c.id == company_id)
        ).scalar_one_or_none()
        if tenant_id is None:
            raise MediaMigrationError("The selected target company does not exist.")
        tenant_id = str(tenant_id)
        _validate_target_cloud_owners(connection, plan, company_id)
        new_paths = {
            relative: _destination_relative_path(
                relative,
                tenant_container_id=tenant_id,
                company_id=company_id,
            )
            for relative in plan.source_files
        }
        already, _ = _validate_target_values(
            connection,
            plan.references,
            new_paths,
            tenant_id,
            company_id,
        )
    report.already_rewritten_references = already
    _prepare_cloud_metadata(plan, new_paths)

    destination = _configured_uploads_root(destination_root)
    file_destinations: dict[str, Path] = {}
    for relative, source_file in plan.source_files.items():
        destination_relative = new_paths[relative]
        target = _destination_file(destination, destination_relative)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise MediaMigrationError(f"Destination media path '{destination_relative}' is not a regular file.")
            target_hash, target_size = _sha256_file(target)
            if target_hash != source_file.sha256 or target_size != source_file.size_bytes:
                raise MediaMigrationError(
                    f"Destination media conflict at '{destination_relative}'; refusing to overwrite different content."
                )
        file_destinations[relative] = target

    for relative, source_file in plan.source_files.items():
        target = file_destinations[relative]
        if target.exists():
            report.already_present_files += 1
            continue
        _ensure_private_directory(target.parent, destination)
        if _copy_verified_file(source_file, target):
            report.copied_files += 1
        else:
            report.already_present_files += 1

    with db.engine.begin() as connection:
        # Recheck company scope and path values inside the write transaction so
        # concurrent target changes cannot be silently replaced.
        current_tenant_id = connection.execute(
            select(company_table.c.tenant_container_id).where(company_table.c.id == company_id)
        ).scalar_one_or_none()
        if str(current_tenant_id) != tenant_id:
            raise MediaMigrationError("The target company's tenant changed during media migration.")
        rewritten, already = _update_target_values(
            connection,
            plan.references,
            new_paths,
            tenant_id,
            company_id,
        )
        report.rewritten_target_references = rewritten
        report.already_rewritten_references = already
        report.database_paths_verified = _verify_target_paths(
            connection,
            destination,
            tenant_id,
            company_id,
        )
    report.cloud_paths_verified = _verify_cloud_uploads(destination, plan, new_paths)
    return report
