"""User, role, and permission primitives for the first Flask milestone."""

import re
from datetime import datetime, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask_login import UserMixin
from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

ROLES: tuple[str, ...] = (
    "admin",
    "manager",
    "salesperson",
    "storekeeper",
    "cashier",
    "logistics",
    "auditor",
    "display",
    "express",
)

# Includes current application permissions and the three cloud permissions already
# present on the legacy seed accounts, but absent from its declared permission union.
PERMISSIONS: tuple[str, ...] = (
    "view_admin_dashboard",
    "manage_products",
    "manage_orders",
    "manage_users",
    "manage_demand_notices",
    "manage_settings",
    "view_reports",
    "view_salesperson_reports",
    "manage_logistics",
    "manage_returns",
    "view_activity_logs",
    "manage_labels",
    "manage_cloud_files",
    "manage_audits",
    "conduct_audits",
    "manage_suppliers",
    "create_pos",
    "approve_pos",
    "receive_stock",
    "express_checkout",
    "upload_cloud",
    "delete_cloud_file",
    "edit_cloud_notes",
)

PERMISSION_LABELS: dict[str, str] = {
    "view_admin_dashboard": "View admin dashboard",
    "manage_products": "Manage products",
    "manage_orders": "Manage orders",
    "manage_users": "Manage user accounts",
    "manage_demand_notices": "Manage demand notices",
    "manage_settings": "Manage settings",
    "view_reports": "View reports",
    "view_salesperson_reports": "View salesperson reports",
    "manage_logistics": "Manage logistics",
    "manage_returns": "Manage returns",
    "view_activity_logs": "View activity logs",
    "manage_labels": "Manage barcode and labels",
    "manage_cloud_files": "Manage all cloud files",
    "manage_audits": "Manage audits",
    "conduct_audits": "Conduct assigned audits",
    "manage_suppliers": "Manage suppliers",
    "create_pos": "Create purchase orders",
    "approve_pos": "Approve purchase orders",
    "receive_stock": "Receive stock",
    "express_checkout": "Use express checkout",
    "upload_cloud": "Upload personal files",
    "delete_cloud_file": "Delete permitted files",
    "edit_cloud_notes": "Edit file notes",
}

CLOUD_PERMISSIONS = frozenset({"upload_cloud", "delete_cloud_file", "edit_cloud_notes"})
ROLE_PERMISSION_LIMITS: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSIONS),
    "manager": frozenset(PERMISSIONS),
    "salesperson": CLOUD_PERMISSIONS,
    "storekeeper": CLOUD_PERMISSIONS,
    "cashier": CLOUD_PERMISSIONS,
    "logistics": CLOUD_PERMISSIONS,
    "auditor": CLOUD_PERMISSIONS | {"conduct_audits"},
    "display": frozenset(),
    "express": CLOUD_PERMISSIONS | {"express_checkout"},
}

_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,47}$")
_PASSWORD_HASHER = PasswordHasher()


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def is_valid_username(username: str) -> bool:
    return bool(_USERNAME_PATTERN.fullmatch(normalize_username(username)))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')",
            name="ck_users_valid_role",
        ),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_break_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auto_enter_after_scan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def __init__(self, **kwargs):
        if "username" in kwargs:
            kwargs["username"] = normalize_username(kwargs["username"])
        super().__init__(**kwargs)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def set_password(self, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters.")
        self.password_hash = _PASSWORD_HASHER.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            valid = _PASSWORD_HASHER.verify(self.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
            return False
        if valid and _PASSWORD_HASHER.check_needs_rehash(self.password_hash):
            self.password_hash = _PASSWORD_HASHER.hash(password)
        return bool(valid)

    def has_permission(self, permission: str) -> bool:
        if self.is_admin:
            return True
        return permission in (self.permissions or [])

    def to_public_dict(self) -> dict[str, object]:
        """Serialize only safe account fields; password hashes are never exposed."""
        created_at = self.created_at
        if created_at is not None:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = created_at.astimezone(timezone.utc)
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "permissions": sorted(self.permissions or []),
            "is_active": self.is_active,
            "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
        }

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r} role={self.role!r}>"
