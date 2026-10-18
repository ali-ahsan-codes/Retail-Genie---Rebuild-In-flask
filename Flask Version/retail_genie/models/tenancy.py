"""SaaS tenant containers, nested companies, memberships, policies and audits."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

DATA_DOMAINS: tuple[str, ...] = (
    "product_catalog",
    "inventory",
    "customers",
    "open_bills",
    "sales",
    "staff_accounts",
    "suppliers",
    "reports",
    "files",
    "audit",
    "cashups",
    "settings",
)
SHARING_MODES: tuple[str, ...] = ("container", "company", "assigned_store", "selected_units", "disabled")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantContainer(db.Model):
    """Logical SaaS isolation boundary; all customers share the same MySQL DB."""

    __tablename__ = "tenant_containers"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_containers_slug"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Muscat")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    policy_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    companies: Mapped[list["Company"]] = relationship(back_populates="tenant_container")


class Company(db.Model):
    """An operating/legal company node inside a tenant container."""

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("mixed_tender_category IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_companies_mixed_tender_category"),
        ForeignKeyConstraint(
            ["tenant_container_id", "parent_company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_companies_parent_same_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "id", name="uq_companies_container_id_id"),
        UniqueConstraint("tenant_container_id", "slug", name="uq_companies_container_slug"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Muscat")
    mixed_tender_category: Mapped[str] = mapped_column(String(24), nullable=False, default="other", server_default=text("'other'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    tenant_container: Mapped[TenantContainer] = relationship(back_populates="companies")
    parent: Mapped["Company | None"] = relationship(
        remote_side=lambda: [Company.tenant_container_id, Company.id],
        back_populates="children",
        foreign_keys=[tenant_container_id, parent_company_id],
        overlaps="companies,tenant_container",
    )
    children: Mapped[list["Company"]] = relationship(
        back_populates="parent",
        foreign_keys=[tenant_container_id, parent_company_id],
        overlaps="companies,tenant_container",
    )
    stores: Mapped[list["Store"]] = relationship(
        back_populates="company",
        foreign_keys=lambda: [Store.tenant_container_id, Store.company_id],
    )


class Store(db.Model):
    """A branch/store belonging to one company inside one tenant container."""

    __tablename__ = "stores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_stores_company_same_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_stores_company_id_id"),
        UniqueConstraint("tenant_container_id", "id", name="uq_stores_container_id_id"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stores_container_company_id"),
        UniqueConstraint("tenant_container_id", "company_id", "code", name="uq_stores_container_company_code"),
        Index("ix_stores_container_company_active", "tenant_container_id", "company_id", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    company: Mapped[Company] = relationship(back_populates="stores", foreign_keys=[company_id])


class ContainerMembership(db.Model):
    """A user identity's role and permission set in a particular tenant."""

    __tablename__ = "container_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')",
            name="ck_container_memberships_valid_role",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_container_memberships_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "user_id", name="uq_container_memberships_container_user"),
        Index("ix_container_memberships_user_active", "user_id", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class TenantDataPolicy(db.Model):
    """Container-level sharing mode for one data domain; roles stay independent."""

    __tablename__ = "tenant_data_policies"
    __table_args__ = (
        CheckConstraint("sharing_mode IN ('container', 'company', 'assigned_store', 'selected_units', 'disabled')", name="ck_tenant_data_policies_sharing_mode"),
        CheckConstraint("domain IN ('product_catalog', 'inventory', 'customers', 'open_bills', 'sales', 'staff_accounts', 'suppliers', 'reports', 'files', 'audit', 'cashups', 'settings')", name="ck_tenant_data_policies_domain"),
        UniqueConstraint("tenant_container_id", "domain", name="uq_tenant_data_policies_container_domain"),
        UniqueConstraint("tenant_container_id", "id", name="uq_tenant_data_policies_container_id_id"),
        Index("ix_tenant_data_policies_container_enabled", "tenant_container_id", "is_enabled"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    sharing_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="container")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    policy_version: Mapped[int] = mapped_column(nullable=False, default=1)
    changed_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class TenantDataPolicyScope(db.Model):
    """Explicit allow/deny scopes used when a domain is set to selected_units."""

    __tablename__ = "tenant_data_policy_scopes"
    __table_args__ = (
        CheckConstraint("(company_id IS NOT NULL AND store_id IS NULL) OR (company_id IS NULL AND store_id IS NOT NULL)", name="ck_tenant_data_policy_scopes_one_unit"),
        ForeignKeyConstraint(
            ["tenant_container_id", "policy_id"],
            ["tenant_data_policies.tenant_container_id", "tenant_data_policies.id"],
            name="fk_tenant_data_policy_scopes_policy",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_tenant_data_policy_scopes_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "store_id"],
            ["stores.tenant_container_id", "stores.id"],
            name="fk_tenant_data_policy_scopes_store",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "policy_id", "company_id", "store_id", name="uq_tenant_data_policy_scopes_unit"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UserStoreAssignment(db.Model):
    """Revocable store access tied to a tenant membership."""

    __tablename__ = "user_store_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "user_id"],
            ["container_memberships.tenant_container_id", "container_memberships.user_id"],
            name="fk_user_store_assignments_membership",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_user_store_assignments_store_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "store_id", name="uq_user_store_assignments_user_store"),
        Index("ix_user_store_assignments_container_user", "tenant_container_id", "user_id"),
        Index("ix_user_store_assignments_container_store_active", "tenant_container_id", "store_id", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    can_view_shared_bills: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AuditEvent(db.Model):
    """Append-only-by-application audit event, always scoped to one container."""

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_audit_events_company_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_audit_events_store_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_audit_events_container_created", "tenant_container_id", "created_at"),
        Index("ix_audit_events_container_store_created", "tenant_container_id", "store_id", "created_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
