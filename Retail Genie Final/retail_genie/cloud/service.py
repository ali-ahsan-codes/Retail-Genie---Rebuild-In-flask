"""Private tenant-scoped uploads, sharing, and authorized downloads."""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from flask import current_app
from sqlalchemy import or_, select
from werkzeug.utils import secure_filename

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import CloudFile, CloudFileShare, Company, Store, TenantContainer, User

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".csv", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".zip",
}


class CloudRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant(actor: User) -> str:
    tenant_id = current_tenant_container_id(actor)
    if not tenant_id:
        raise CloudRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, tenant_id)
    if container is None or not container.is_active:
        raise CloudRuleError("Tenant container not found.", 404, "not_found")
    return tenant_id


def _owner_company(actor: User, tenant_id: str) -> str | None:
    if actor.is_super_admin:
        return None
    membership = current_membership(actor, tenant_container_id=tenant_id)
    if membership is None:
        raise CloudRuleError("Tenant membership is required.", 403, "tenant_forbidden")
    return membership.company_id


def _can_files(actor: User, tenant_id: str, company_id: str | None, action: str = "view") -> bool:
    if actor.is_super_admin:
        return True
    if not actor.has_permission("upload_cloud") and action == "add":
        return False
    if not actor.has_permission("manage_cloud_files") and action in {"delete", "edit"}:
        # Owners can manage their own files; admins get the broad permission.
        return True
    if company_id is None:
        return False
    try:
        return can_access_data_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="files",
            action=action,
            company_id=company_id,
        )
    except Exception:
        return False


def _file_row(file_id: str, tenant_id: str) -> CloudFile:
    row = db.session.execute(
        select(CloudFile).where(
            CloudFile.id == file_id,
            CloudFile.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise CloudRuleError("File not found.", 404, "not_found")
    return row


def _may_read(actor: User, row: CloudFile, *, allow_owner: bool = True) -> bool:
    if row.owner_user_id == actor.id and allow_owner:
        return True
    if actor.is_super_admin:
        return True
    if not _can_files(actor, row.tenant_container_id, row.owner_company_id, "view"):
        return False
    if row.is_shared and row.share_scope == "container":
        return True
    membership = current_membership(actor, tenant_container_id=row.tenant_container_id)
    if row.share_scope == "company" and membership and membership.company_id == row.share_unit_id:
        return True
    if row.share_scope == "store" and membership:
        return row.share_unit_id in accessible_store_ids(
            actor, company_id=membership.company_id, tenant_container_id=row.tenant_container_id
        )
    share = db.session.execute(
        select(CloudFileShare.id).where(
            CloudFileShare.tenant_container_id == row.tenant_container_id,
            CloudFileShare.file_id == row.id,
            CloudFileShare.shared_with_user_id == actor.id,
        )
    ).scalar_one_or_none()
    return share is not None


def file_dict(row: CloudFile) -> dict:
    return {
        "id": row.id,
        "original_name": row.original_name,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "notes": row.notes,
        "owner_user_id": row.owner_user_id,
        "owner_company_id": row.owner_company_id,
        "share_scope": row.share_scope,
        "is_shared": row.is_shared,
        "uploaded_at": row.uploaded_at.isoformat().replace("+00:00", "Z") if row.uploaded_at else None,
    }


def list_files(actor: User, *, search: str | None = None) -> list[dict]:
    tenant_id = _tenant(actor)
    company_id = _owner_company(actor, tenant_id)
    statement = select(CloudFile).where(CloudFile.tenant_container_id == tenant_id)
    share_ids = select(CloudFileShare.file_id).where(
        CloudFileShare.tenant_container_id == tenant_id,
        CloudFileShare.shared_with_user_id == actor.id,
    )
    statement = statement.where(
        or_(
            CloudFile.owner_user_id == actor.id,
            CloudFile.is_shared.is_(True),
            CloudFile.id.in_(share_ids),
        )
    )
    if company_id is not None:
        statement = statement.where(
            or_(CloudFile.owner_company_id == company_id, CloudFile.share_scope == "container")
        )
    cleaned = (search or "").strip()
    if cleaned:
        statement = statement.where(CloudFile.original_name.ilike(f"%{cleaned}%"))
    statement = statement.order_by(CloudFile.uploaded_at.desc()).limit(500)
    return [file_dict(row) for row in db.session.execute(statement).scalars() if _may_read(actor, row)]


def upload_file(actor: User, *, file_storage, notes: str | None = None) -> CloudFile:
    tenant_id = _tenant(actor)
    company_id = _owner_company(actor, tenant_id)
    if not actor.has_permission("upload_cloud") and not actor.is_super_admin:
        raise CloudRuleError("File upload permission is required.", 403, "permission_denied")
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise CloudRuleError("Choose a file to upload.")
    original_name = secure_filename(file_storage.filename)
    if not original_name or len(original_name) > 255:
        raise CloudRuleError("The file name is invalid.")
    extension = Path(original_name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise CloudRuleError("This file type is not allowed.")
    content = file_storage.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise CloudRuleError("Files must be between 1 byte and 20 MB.")
    # Prevent active content upload under misleading text or document extensions.
    if extension in {".txt", ".csv"} and b"\x00" in content[:8192]:
        raise CloudRuleError("This file does not match its file extension.")
    file_id = str(uuid4())
    relative_path = f"tenants/{tenant_id}/cloud/{actor.id}/{file_id}{extension}"
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    destination = (root / relative_path).resolve()
    if root not in destination.parents:
        raise CloudRuleError("Invalid upload path.", 400, "invalid_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(content)
    row = CloudFile(
        id=file_id,
        tenant_container_id=tenant_id,
        owner_user_id=actor.id,
        owner_company_id=company_id,
        file_path=relative_path,
        original_name=original_name,
        mime_type=file_storage.mimetype or "application/octet-stream",
        size_bytes=len(content),
        notes=(notes or "").strip()[:500] or None,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        if destination.is_file():
            destination.unlink()
        raise
    return row


def authorized_file_path(actor: User, file_id: str) -> tuple[CloudFile, Path]:
    tenant_id = _tenant(actor)
    row = _file_row(file_id, tenant_id)
    if not _may_read(actor, row):
        raise CloudRuleError("You do not have access to this file.", 403, "permission_denied")
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / row.file_path).resolve()
    if root not in path.parents or not path.is_file():
        raise CloudRuleError("File is missing from private storage.", 404, "file_missing")
    return row, path


def update_file_notes(actor: User, *, file_id: str, notes: str | None) -> CloudFile:
    tenant_id = _tenant(actor)
    row = _file_row(file_id, tenant_id)
    if row.owner_user_id != actor.id and not actor.has_permission("manage_cloud_files"):
        raise CloudRuleError("Only the owner or a file administrator can edit notes.", 403, "permission_denied")
    cleaned = (notes or "").strip()
    if len(cleaned) > 500:
        raise CloudRuleError("Notes must be 500 characters or fewer.")
    row.notes = cleaned or None
    db.session.flush()
    return row


def delete_file(actor: User, *, file_id: str) -> Path:
    tenant_id = _tenant(actor)
    row = _file_row(file_id, tenant_id)
    if row.owner_user_id != actor.id and not actor.has_permission("manage_cloud_files"):
        raise CloudRuleError("Only the owner or a file administrator can delete this file.", 403, "permission_denied")
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / row.file_path).resolve()
    if root not in path.parents:
        raise CloudRuleError("Invalid stored file path.", 409, "invalid_path")
    db.session.delete(row)
    db.session.flush()
    return path


def share_file(actor: User, *, file_id: str, scope: str, unit_id: str | None = None, user_ids: list[str] | None = None) -> CloudFile:
    tenant_id = _tenant(actor)
    row = _file_row(file_id, tenant_id)
    if row.owner_user_id != actor.id and not actor.has_permission("manage_cloud_files"):
        raise CloudRuleError("Only the owner or file administrator can share this file.", 403, "permission_denied")
    if scope not in {"container", "company", "store", "user"}:
        raise CloudRuleError("Unknown sharing scope.")
    membership = current_membership(actor, tenant_container_id=tenant_id)
    if scope == "container" and not actor.is_admin and not actor.is_super_admin:
        raise CloudRuleError("Only administrators can share files across the full tenant.", 403, "permission_denied")
    if scope == "company":
        if not unit_id or unit_id != row.owner_company_id:
            raise CloudRuleError("Company-shared files must stay within the owner's company.", 403, "scope_forbidden")
    if scope == "store":
        allowed = accessible_store_ids(actor, company_id=membership.company_id if membership else None, tenant_container_id=tenant_id)
        target_store = db.session.get(Store, unit_id) if unit_id else None
        if not unit_id or unit_id not in allowed or target_store is None or target_store.company_id != row.owner_company_id or target_store.tenant_container_id != tenant_id:
            raise CloudRuleError("Choose an authorized store within the file owner's company.", 403, "scope_forbidden")
    if scope == "user":
        ids = list(dict.fromkeys(str(value) for value in (user_ids or [])))
        if not ids or len(ids) > 50:
            raise CloudRuleError("Choose 1-50 tenant members to share with.")
        for user_id in ids:
            from ..models import ContainerMembership
            valid = db.session.execute(
                select(ContainerMembership.id).where(
                    ContainerMembership.tenant_container_id == tenant_id,
                    ContainerMembership.user_id == user_id,
                    ContainerMembership.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if valid is None:
                raise CloudRuleError("Recipients must be active members of this tenant.", 403, "recipient_forbidden")
            existing = db.session.execute(
                select(CloudFileShare.id).where(
                    CloudFileShare.tenant_container_id == tenant_id,
                    CloudFileShare.file_id == row.id,
                    CloudFileShare.shared_with_user_id == user_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.session.add(
                    CloudFileShare(
                        tenant_container_id=tenant_id,
                        company_id=row.owner_company_id,
                        file_id=row.id,
                        shared_with_user_id=user_id,
                        created_by_id=actor.id,
                    )
                )
        row.share_scope = "user"
        row.share_unit_id = None
    else:
        row.share_scope = scope
        row.share_unit_id = unit_id if scope in {"company", "store"} else None
    row.is_shared = True
    db.session.flush()
    return row


def unshare_file(actor: User, *, file_id: str, user_id: str | None = None) -> CloudFile:
    tenant_id = _tenant(actor)
    row = _file_row(file_id, tenant_id)
    if row.owner_user_id != actor.id and not actor.has_permission("manage_cloud_files"):
        raise CloudRuleError("Only the owner or file administrator can unshare this file.", 403, "permission_denied")
    statement = select(CloudFileShare).where(
        CloudFileShare.tenant_container_id == tenant_id,
        CloudFileShare.file_id == row.id,
    )
    if user_id:
        statement = statement.where(CloudFileShare.shared_with_user_id == user_id)
    for share in db.session.execute(statement).scalars():
        db.session.delete(share)
    if user_id is None:
        row.is_shared = False
        row.share_scope = "user"
        row.share_unit_id = None
    db.session.flush()
    return row
