"""User, role, and permission primitives for the first Flask milestone."""

import re
from datetime import datetime, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask_login import UserMixin
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .tenancy import DATA_DOMAINS

ROLES: tuple[str, ...] = (
    "super_admin",
    "company_admin",
    "admin",  # Company administrator account role.
    "manager",
    "salesperson",
    "storekeeper",
    "cashier",
    "logistics",
    "auditor",
    "display",
    "express",
)

DOMAIN_ACTIONS: tuple[str, ...] = ("view", "add", "edit", "delete")
DOMAIN_LABELS: dict[str, str] = {
    "product_catalog": "Product catalog",
    "inventory": "Inventory",
    "customers": "Customers",
    "open_bills": "Open bills",
    "sales": "Sales and invoices",
    "staff_accounts": "Staff and accounts",
    "suppliers": "Suppliers",
    "reports": "Reports",
    "files": "Files",
    "audit": "Audit",
    "cashups": "Cashups",
    "settings": "Settings",
}
DOMAIN_ACTION_PERMISSIONS: tuple[str, ...] = tuple(
    f"{domain}.{action}" for domain in DATA_DOMAINS for action in DOMAIN_ACTIONS
)

# Includes current application permissions, legacy cloud permissions, and
# explicit data-domain CRUD grants for future modules and scoped services.
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
    "use_sales_pos",
    "approve_pos",
    "receive_stock",
    "express_checkout",
    "upload_cloud",
    "delete_cloud_file",
    "edit_cloud_notes",
) + DOMAIN_ACTION_PERMISSIONS

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
    "use_sales_pos": "Open the point-of-sale screen",
    "approve_pos": "Approve purchase orders",
    "receive_stock": "Receive stock",
    "express_checkout": "Use express checkout",
    "upload_cloud": "Upload personal files",
    "delete_cloud_file": "Delete permitted files",
    "edit_cloud_notes": "Edit file notes",
}
PERMISSION_LABELS.update(
    {
        permission: f"{DOMAIN_LABELS[permission.rsplit('.', 1)[0]]} — {permission.rsplit('.', 1)[1]}"
        for permission in DOMAIN_ACTION_PERMISSIONS
    }
)

SALES_DOMAIN_PERMISSIONS = frozenset(
    {
        "open_bills.view",
        "open_bills.add",
        "open_bills.edit",
        "sales.view",
        "sales.add",
        "sales.edit",
        "product_catalog.view",
        "inventory.view",
    }
)
INVENTORY_DOMAIN_PERMISSIONS = frozenset(
    {"product_catalog.view", "inventory.view", "inventory.add", "inventory.edit"}
)
AUDIT_DOMAIN_PERMISSIONS = frozenset({"audit.view", "reports.view"})
CLOUD_PERMISSIONS = frozenset({"upload_cloud", "delete_cloud_file", "edit_cloud_notes"})
ROLE_PERMISSION_LIMITS: dict[str, frozenset[str]] = {
    "super_admin": frozenset(PERMISSIONS),
    "company_admin": frozenset(PERMISSIONS),
    "admin": frozenset(PERMISSIONS),
    "manager": frozenset(PERMISSIONS),
    "salesperson": CLOUD_PERMISSIONS | {"use_sales_pos", "view_salesperson_reports"} | SALES_DOMAIN_PERMISSIONS,
    "storekeeper": CLOUD_PERMISSIONS | INVENTORY_DOMAIN_PERMISSIONS,
    "cashier": CLOUD_PERMISSIONS | {"use_sales_pos"} | SALES_DOMAIN_PERMISSIONS,
    "logistics": CLOUD_PERMISSIONS | {"product_catalog.view", "inventory.view", "inventory.add", "inventory.edit"},
    "auditor": CLOUD_PERMISSIONS | {"conduct_audits"} | AUDIT_DOMAIN_PERMISSIONS,
    "display": frozenset(),
    "express": CLOUD_PERMISSIONS | {"express_checkout", "use_sales_pos"} | SALES_DOMAIN_PERMISSIONS,
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
            "role IN ('super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')",
            name="ck_users_valid_role",
        ),
        UniqueConstraint("company_id", "id", name="uq_users_company_id_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
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
    def effective_membership(self):
        """Return the active tenant membership rather than treating company_id as tenancy."""
        if self.role == "super_admin":
            return None
        try:
            from ..auth.tenant_context import current_membership

            return current_membership(self)
        except RuntimeError:
            return None

    @property
    def effective_role(self) -> str:
        membership = self.effective_membership
        return membership.role if membership is not None else self.role

    @property
    def is_admin(self) -> bool:
        """Compatibility predicate for tenant and platform administrators."""
        return self.effective_role in {"super_admin", "company_admin", "admin"}

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_company_admin(self) -> bool:
        return self.effective_role in {"company_admin", "admin"}

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
        membership = self.effective_membership
        role = membership.role if membership is not None else self.role
        if role in {"super_admin", "company_admin", "admin"}:
            return True
        permissions = membership.permissions if membership is not None else self.permissions
        return permission in (permissions or []) and permission in ROLE_PERMISSION_LIMITS.get(role, frozenset())

    def to_public_dict(self) -> dict[str, object]:
        """Serialize only safe account fields; password hashes are never exposed."""
        created_at = self.created_at
        if created_at is not None:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = created_at.astimezone(timezone.utc)
        membership = self.effective_membership
        permissions = membership.permissions if membership is not None else self.permissions
        return {
            "id": self.id,
            "tenant_container_id": membership.tenant_container_id if membership is not None else None,
            "company_id": self.company_id,
            "username": self.username,
            "role": self.effective_role,
            "permissions": sorted(permissions or []),
            "is_active": self.is_active,
            "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
        }

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r} role={self.role!r}>"
