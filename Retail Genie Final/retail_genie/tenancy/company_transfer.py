"""Guarded, same-database migration of one company between tenant containers.

This operation preserves company and business-row IDs. It is intentionally
limited to a leaf company; ambiguous cross-company data references are rejected
rather than silently copied or re-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import current_app
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.schema import Table

from ..extensions import db
from ..models import (
    AuditEvent,
    CloudFileShare,
    Company,
    ContainerMembership,
    Conversation,
    PlatformAuditEvent,
    Store,
    TenantContainer,
    TenantDataPolicy,
    TenantSubscription,
    User,
)


class CompanyTransferError(ValueError):
    """A company move could not be planned or safely committed."""


@dataclass(frozen=True)
class CompanyTransferPlan:
    company_id: str
    company_name: str
    company_slug: str
    source_container_id: str
    source_container_name: str
    destination_container_id: str
    destination_container_name: str
    destination_parent_company_id: str | None
    destination_parent_company_name: str | None
    store_count: int
    member_count: int
    row_counts: dict[str, int]
    destination_policy_modes: dict[str, str]
    source_will_archive: bool
    blockers: tuple[str, ...]

    @property
    def can_move(self) -> bool:
        return not self.blockers

    @property
    def total_rows(self) -> int:
        return sum(self.row_counts.values()) + 1  # Include the Company row.

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "company_slug": self.company_slug,
            "source_container_id": self.source_container_id,
            "source_container_name": self.source_container_name,
            "destination_container_id": self.destination_container_id,
            "destination_container_name": self.destination_container_name,
            "destination_parent_company_id": self.destination_parent_company_id,
            "destination_parent_company_name": self.destination_parent_company_name,
            "store_count": self.store_count,
            "member_count": self.member_count,
            "row_counts": self.row_counts,
            "destination_policy_modes": self.destination_policy_modes,
            "total_rows": self.total_rows,
            "source_will_archive": self.source_will_archive,
            "blockers": list(self.blockers),
            "can_move": self.can_move,
        }


_POLICY_SCOPE = "tenant_data_policy_scopes"
_CLOUD_FILES = "cloud_files"
_CLOUD_SHARES = "cloud_file_shares"
_CONVERSATIONS = "messaging_conversations"
_MESSAGES = "messaging_messages"
_MESSAGE_RECIPIENTS = "messaging_message_recipients"
_MESSAGE_ATTACHMENTS = "messaging_attachments"


def _table(name: str) -> Table:
    try:
        return db.metadata.tables[name]
    except KeyError as error:
        raise CompanyTransferError(f"The application schema is missing required table {name}.") from error


def _scope_conditions(
    table: Table,
    *,
    company_id: str,
    store_ids: list[str],
    user_ids: list[str],
    file_ids: list[str],
    conversation_ids: list[str],
    message_ids: list[str],
    physical_table_name: str | None = None,
) -> list[Any]:
    """Return ownership/link predicates for rows that follow the company."""
    columns = table.c
    table_name = physical_table_name or table.name
    conditions: list[Any] = []
    if "company_id" in columns:
        conditions.append(columns.company_id == company_id)
    if "owner_company_id" in columns:
        conditions.append(columns.owner_company_id == company_id)
    if "store_id" in columns and store_ids:
        conditions.append(columns.store_id.in_(store_ids))

    if table_name == _CLOUD_FILES and user_ids:
        conditions.append(and_(columns.owner_company_id.is_(None), columns.owner_user_id.in_(user_ids)))
    elif table_name == _CLOUD_SHARES and file_ids:
        conditions.append(columns.file_id.in_(file_ids))
    elif table_name == _MESSAGES and conversation_ids:
        conditions.append(columns.conversation_id.in_(conversation_ids))
    elif table_name in {_MESSAGE_RECIPIENTS, _MESSAGE_ATTACHMENTS} and message_ids:
        conditions.append(columns.message_id.in_(message_ids))
    return conditions


def _row_scope(
    table: Table,
    *,
    tenant_container_id: str,
    company_id: str,
    store_ids: list[str],
    user_ids: list[str],
    file_ids: list[str],
    conversation_ids: list[str],
    message_ids: list[str],
):
    if "tenant_container_id" not in table.c:
        return None
    conditions = _scope_conditions(
        table,
        company_id=company_id,
        store_ids=store_ids,
        user_ids=user_ids,
        file_ids=file_ids,
        conversation_ids=conversation_ids,
        message_ids=message_ids,
    )
    if not conditions:
        return None
    return and_(
        table.c.tenant_container_id == tenant_container_id,
        or_(*conditions),
    )


def _ids_for_scope(table: Table, scope):
    return list(db.session.execute(select(table.c.id).where(scope)).scalars())


def _count_rows(table: Table, scope) -> int:
    return int(db.session.execute(select(func.count()).select_from(table).where(scope)).scalar_one())


def _metadata_tables() -> list[Table]:
    return [
        table
        for table in db.metadata.sorted_tables
        if "tenant_container_id" in table.c and table.name != "tenant_containers"
    ]


def _build_plan(
    company_id: str,
    destination_container_id: str,
    destination_parent_company_id: str | None = None,
) -> tuple[CompanyTransferPlan, dict[str, Any]]:
    company = db.session.get(Company, company_id)
    if company is None:
        raise CompanyTransferError("The selected company does not exist.")
    source = db.session.get(TenantContainer, company.tenant_container_id)
    destination = db.session.get(TenantContainer, destination_container_id)
    if source is None or destination is None:
        raise CompanyTransferError("The source or destination tenant container does not exist.")
    if source.id == destination.id:
        raise CompanyTransferError("Choose a different destination container.")

    stores = db.session.execute(
        select(Store).where(
            Store.tenant_container_id == source.id,
            Store.company_id == company.id,
        ).order_by(Store.id.asc())
    ).scalars().all()
    store_ids = [store.id for store in stores]
    memberships = db.session.execute(
        select(ContainerMembership).where(
            ContainerMembership.tenant_container_id == source.id,
            ContainerMembership.company_id == company.id,
        ).order_by(ContainerMembership.user_id.asc())
    ).scalars().all()
    user_ids = [membership.user_id for membership in memberships]

    cloud_table = _table(_CLOUD_FILES)
    cloud_scope = _row_scope(
        cloud_table,
        tenant_container_id=source.id,
        company_id=company.id,
        store_ids=store_ids,
        user_ids=user_ids,
        file_ids=[],
        conversation_ids=[],
        message_ids=[],
    )
    file_ids = _ids_for_scope(cloud_table, cloud_scope) if cloud_scope is not None else []

    conversation_table = _table(_CONVERSATIONS)
    conversation_scope = _row_scope(
        conversation_table,
        tenant_container_id=source.id,
        company_id=company.id,
        store_ids=store_ids,
        user_ids=user_ids,
        file_ids=file_ids,
        conversation_ids=[],
        message_ids=[],
    )
    conversation_ids = _ids_for_scope(conversation_table, conversation_scope) if conversation_scope is not None else []

    message_table = _table(_MESSAGES)
    message_scope = _row_scope(
        message_table,
        tenant_container_id=source.id,
        company_id=company.id,
        store_ids=store_ids,
        user_ids=user_ids,
        file_ids=file_ids,
        conversation_ids=conversation_ids,
        message_ids=[],
    )
    message_ids = _ids_for_scope(message_table, message_scope) if message_scope is not None else []

    # Every selected tenant row is accounted for by company, owner-company,
    # store, file, conversation, or message ownership. Container billing,
    # backup, and policy header rows intentionally remain with the container.
    row_counts: dict[str, int] = {}
    scopes: dict[str, Any] = {}
    for table in _metadata_tables():
        scope = _row_scope(
            table,
            tenant_container_id=source.id,
            company_id=company.id,
            store_ids=store_ids,
            user_ids=user_ids,
            file_ids=file_ids,
            conversation_ids=conversation_ids,
            message_ids=message_ids,
        )
        if scope is None:
            continue
        count = _count_rows(table, scope)
        if count:
            row_counts[table.name] = count
            scopes[table.name] = scope

    blockers: list[str] = []
    if not company.is_active:
        blockers.append("Enable the company before transferring it.")
    if not source.is_active:
        blockers.append("The source container is archived; restore it before transferring a company.")
    if not destination.is_active:
        blockers.append("The destination container is archived; restore it before transferring a company.")
    if db.session.execute(
        select(Company.id).where(
            Company.tenant_container_id == destination.id,
            Company.slug == company.slug,
            Company.id != company.id,
        )
    ).scalar_one_or_none():
        blockers.append("The destination already has a company with the same company code.")

    children = db.session.execute(
        select(Company.id).where(
            Company.tenant_container_id == source.id,
            Company.parent_company_id == company.id,
        )
    ).scalars().all()
    if children:
        blockers.append("Move this company's child companies first; subtree transfers are not supported in one operation.")

    parent = None
    if destination_parent_company_id:
        parent = db.session.get(Company, destination_parent_company_id)
        if parent is None or not parent.is_active or parent.tenant_container_id != destination.id:
            blockers.append("The selected parent company is not active in the destination container.")
        elif parent.id == company.id:
            blockers.append("A company cannot be its own parent.")

    if user_ids:
        conflicts = db.session.execute(
            select(ContainerMembership.user_id).where(
                ContainerMembership.tenant_container_id == destination.id,
                ContainerMembership.user_id.in_(user_ids),
            )
        ).scalars().all()
        if conflicts:
            blockers.append(
                f"{len(set(conflicts))} company member(s) already have a destination-container membership; resolve duplicate access before moving."
            )

    # A moved business row may reference a product owned by another company.
    # Moving it would cross a tenant boundary, so reject rather than silently
    # copying the other company's product or breaking its foreign key.
    for table in _metadata_tables():
        if table.name not in scopes or "product_owner_company_id" not in table.c:
            continue
        moved_external_products = db.session.execute(
            select(func.count()).select_from(table).where(
                scopes[table.name],
                table.c.product_owner_company_id.is_not(None),
                table.c.product_owner_company_id != company.id,
            )
        ).scalar_one()
        if moved_external_products:
            blockers.append(
                f"{table.name} has {moved_external_products} moved row(s) using products owned by another company; resolve those links first."
            )

    for table in _metadata_tables():
        if table.name not in scopes or "product_owner_company_id" not in table.c:
            continue
        external_refs = db.session.execute(
            select(func.count()).select_from(table).where(
                table.c.tenant_container_id == source.id,
                table.c.product_owner_company_id == company.id,
                ~scopes[table.name],
            )
        ).scalar_one()
        if external_refs:
            blockers.append(
                f"{table.name} has {external_refs} source-company row(s) referencing this company's products; move or reassign those references first."
            )

    for table in _metadata_tables():
        if table.name not in scopes or not {"company_id", "store_id"}.issubset(table.c.keys()) or not store_ids:
            continue
        external_store_refs = db.session.execute(
            select(func.count()).select_from(table).where(
                table.c.tenant_container_id == source.id,
                table.c.store_id.in_(store_ids),
                table.c.company_id.is_not(None),
                table.c.company_id != company.id,
            )
        ).scalar_one()
        if external_store_refs:
            blockers.append(
                f"{table.name} contains {external_store_refs} row(s) owned by another company but linked to a moved store."
            )

    # Check composite foreign keys where the row's company is B but the
    # referenced product/company/store is owned by another company.
    for table in _metadata_tables():
        if table.name not in scopes:
            continue
        for constraint in table.foreign_key_constraints:
            remote_company_elements = [
                element for element in constraint.elements if element.column.name == "company_id"
            ]
            for element in remote_company_elements:
                local_column = table.c[element.parent.name]
                external = db.session.execute(
                    select(func.count()).select_from(table).where(
                        scopes[table.name],
                        local_column.is_not(None),
                        local_column != company.id,
                    )
                ).scalar_one()
                if external:
                    blockers.append(
                        f"{table.name}.{local_column.name} points to a different company for {external} moved row(s)."
                    )

    # A row can be swept into the move through an indirect parent link (for
    # example, a file share by file_id) even when its company_id belongs to a
    # different company. Reject those cross-company FK pairs up front.
    for table in _metadata_tables():
        if table.name not in scopes:
            continue
        for constraint in table.foreign_key_constraints:
            for element in constraint.elements:
                if element.column.table.name != "companies" or element.column.name != "id":
                    continue
                local_column = table.c[element.parent.name]
                mismatches = db.session.execute(
                    select(func.count()).select_from(table).where(
                        scopes[table.name],
                        local_column.is_not(None),
                        local_column != company.id,
                    )
                ).scalar_one()
                if mismatches:
                    blockers.append(
                        f"{table.name}.{local_column.name} references another company in {mismatches} moved row(s)."
                    )

    # Find dependent rows left behind in the source that reference any selected
    # parent row. This metadata-driven pass supplements domain-specific checks,
    # so newly mapped foreign-key relationships fail closed by default.
    scope_args = {
        "company_id": company.id,
        "store_ids": store_ids,
        "user_ids": user_ids,
        "file_ids": file_ids,
        "conversation_ids": conversation_ids,
        "message_ids": message_ids,
    }
    moving_parent_tables = {table.name: table for table in _metadata_tables() if table.name in scopes}
    moving_parent_tables["companies"] = Company.__table__
    for child_table in _metadata_tables():
        child_scope = _row_scope(
            child_table,
            tenant_container_id=source.id,
            **scope_args,
        )
        child_outside_scope = ~child_scope if child_scope is not None else True
        for constraint in child_table.foreign_key_constraints:
            parent_name = constraint.elements[0].column.table.name
            parent_table = moving_parent_tables.get(parent_name)
            if parent_table is None:
                continue
            parent_alias = parent_table.alias(f"move_ref_{child_table.name}_{parent_name}")
            parent_conditions = _scope_conditions(
                parent_alias,
                **scope_args,
                physical_table_name=parent_name,
            )
            if parent_name == "companies":
                parent_scope = and_(
                    parent_alias.c.tenant_container_id == source.id,
                    parent_alias.c.id == company.id,
                )
            elif parent_conditions:
                parent_scope = and_(
                    parent_alias.c.tenant_container_id == source.id,
                    or_(*parent_conditions),
                )
            else:
                continue
            join_conditions = and_(
                *(
                    child_table.c[element.parent.name] == parent_alias.c[element.column.name]
                    for element in constraint.elements
                )
            )
            local_values_present = and_(
                *(child_table.c[element.parent.name].is_not(None) for element in constraint.elements)
            )
            parent_exists = select(1).select_from(parent_alias).where(parent_scope, join_conditions).exists()
            external_dependents = db.session.execute(
                select(func.count()).select_from(child_table).where(
                    child_table.c.tenant_container_id == source.id,
                    child_outside_scope,
                    local_values_present,
                    parent_exists,
                )
            ).scalar_one()
            if external_dependents:
                blockers.append(
                    f"{child_table.name} has {external_dependents} source row(s) outside the move that reference moving data in {parent_name}."
                )

    moved_user_set = set(user_ids)
    for conversation in db.session.execute(
        select(Conversation).where(
            Conversation.tenant_container_id == source.id,
            Conversation.company_id == company.id,
        )
    ).scalars():
        participants = set(conversation.participant_ids or [])
        if participants - moved_user_set:
            blockers.append("Company-scoped conversations include participants who are not members of the company being moved.")
            break

    if file_ids:
        outside_file_shares = db.session.execute(
            select(func.count()).select_from(CloudFileShare).where(
                CloudFileShare.tenant_container_id == source.id,
                CloudFileShare.file_id.in_(file_ids),
                CloudFileShare.shared_with_user_id.not_in(user_ids or ["__no_company_members__"]),
            )
        ).scalar_one()
        if outside_file_shares:
            blockers.append("Company files are shared with users outside the moved company; review or revoke those shares first.")

    source_policies = db.session.execute(
        select(TenantDataPolicy).where(TenantDataPolicy.tenant_container_id == source.id)
    ).scalars().all()
    destination_policies = db.session.execute(
        select(TenantDataPolicy).where(TenantDataPolicy.tenant_container_id == destination.id)
    ).scalars().all()
    target_policy_domains = {policy.domain for policy in destination_policies}
    missing_domains = {policy.domain for policy in source_policies} - target_policy_domains
    if missing_domains:
        blockers.append("Destination container is missing data policies for: " + ", ".join(sorted(missing_domains)) + ".")

    remaining_company_count = db.session.execute(
        select(func.count()).select_from(Company).where(
            Company.tenant_container_id == source.id,
            Company.id != company.id,
        )
    ).scalar_one()
    source_subscription_status = db.session.execute(
        select(TenantSubscription.status).where(TenantSubscription.tenant_container_id == source.id)
    ).scalar_one_or_none()
    if remaining_company_count == 0 and source_subscription_status not in {None, "canceled", "suspended"}:
        blockers.append(
            f"The source container subscription is {source_subscription_status}; cancel or suspend it before moving the last company so the archived container is not left on an active plan."
        )

    plan = CompanyTransferPlan(
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        source_container_id=source.id,
        source_container_name=source.name,
        destination_container_id=destination.id,
        destination_container_name=destination.name,
        destination_parent_company_id=parent.id if parent else None,
        destination_parent_company_name=parent.name if parent else None,
        store_count=len(store_ids),
        member_count=len(user_ids),
        row_counts=row_counts,
        destination_policy_modes={policy.domain: policy.sharing_mode for policy in destination_policies},
        source_will_archive=remaining_company_count == 0,
        blockers=tuple(dict.fromkeys(blockers)),
    )
    context = {
        "company": company,
        "source": source,
        "destination": destination,
        "parent": parent,
        "store_ids": store_ids,
        "user_ids": user_ids,
        "file_ids": file_ids,
        "conversation_ids": conversation_ids,
        "message_ids": message_ids,
        "source_policies": source_policies,
        "destination_policies": destination_policies,
    }
    return plan, context


def preview_company_transfer(
    company_id: str,
    destination_container_id: str,
    destination_parent_company_id: str | None = None,
) -> CompanyTransferPlan:
    """Return a read-only impact and blocker report for a proposed transfer."""
    plan, _ = _build_plan(company_id, destination_container_id, destination_parent_company_id)
    return plan


def _validate_moved_foreign_keys(context: dict[str, Any]) -> None:
    """Check model-declared foreign keys for rows that are being transferred."""
    connection = db.session.connection()
    dialect = connection.dialect.name
    if dialect == "sqlite":
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise CompanyTransferError(
                f"Transfer validation found {len(violations)} foreign-key violation(s); no changes were committed."
            )
        return

    target_id = context["destination"].id
    company_id = context["company"].id
    scope_args = {
        "company_id": company_id,
        "store_ids": context["store_ids"],
        "user_ids": context["user_ids"],
        "file_ids": context["file_ids"],
        "conversation_ids": context["conversation_ids"],
        "message_ids": context["message_ids"],
    }
    for table in _metadata_tables():
        ownership = _scope_conditions(table, **scope_args)
        if not ownership:
            continue
        for constraint in table.foreign_key_constraints:
            present = and_(*(table.c[element.parent.name].is_not(None) for element in constraint.elements))
            remote_table = constraint.elements[0].column.table.alias(f"fkcheck_{table.name}")
            matches = and_(
                *(
                    remote_table.c[element.column.name] == table.c[element.parent.name]
                    for element in constraint.elements
                )
            )
            exists_target = select(1).select_from(remote_table).where(matches).exists()
            violations = db.session.execute(
                select(func.count())
                .select_from(table)
                .where(
                    table.c.tenant_container_id == target_id,
                    or_(*ownership),
                    present,
                    ~exists_target,
                )
            ).scalar_one()
            if violations:
                raise CompanyTransferError(
                    f"Transfer validation found {violations} broken reference(s) in {table.name}; no changes were committed."
                )

    moved_company = db.session.execute(
        select(Company).where(
            Company.id == company_id,
            Company.tenant_container_id == target_id,
            Company.parent_company_id == context["parent"].id if context["parent"] else Company.parent_company_id.is_(None),
        )
    ).scalar_one_or_none()
    if moved_company is None:
        raise CompanyTransferError("The company did not resolve in the destination container after transfer.")


def move_company_to_container(
    *,
    company_id: str,
    destination_container_id: str,
    destination_parent_company_id: str | None,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    """Move a leaf company and its scoped history in one guarded DB transaction.

    Callers must require an explicit typed confirmation and a reason. The
    source container is archived (never deleted) if this was its last company.
    """
    reason = (reason or "").strip()
    if len(reason) < 10 or len(reason) > 500:
        raise CompanyTransferError("Enter a transfer reason between 10 and 500 characters.")
    connection = None
    mysql_checks_disabled = False
    published_event_ids: list[int] = []
    moved_user_ids: list[str] = []
    try:
        # Serialize moves of the same containers/company and refresh the
        # preview under lock before any writes occur.
        company_lock = db.session.execute(
            select(Company).where(Company.id == company_id).with_for_update()
        ).scalar_one_or_none()
        if company_lock is None:
            raise CompanyTransferError("The selected company no longer exists.")
        container_ids = sorted({company_lock.tenant_container_id, destination_container_id})
        db.session.execute(
            select(TenantContainer.id)
            .where(TenantContainer.id.in_(container_ids))
            .order_by(TenantContainer.id.asc())
            .with_for_update()
        ).all()
        db.session.execute(
            select(Store.id)
            .where(Store.tenant_container_id == company_lock.tenant_container_id, Store.company_id == company_id)
            .order_by(Store.id.asc())
            .with_for_update()
        ).all()
        db.session.execute(
            select(TenantDataPolicy.id)
            .where(TenantDataPolicy.tenant_container_id.in_(container_ids))
            .order_by(TenantDataPolicy.id.asc())
            .with_for_update()
        ).all()
        plan, context = _build_plan(company_id, destination_container_id, destination_parent_company_id)
        if plan.blockers:
            raise CompanyTransferError("Transfer blocked: " + " ".join(plan.blockers))

        connection = db.session.connection()
        if connection.dialect.name == "mysql":
            connection.exec_driver_sql("SET SESSION FOREIGN_KEY_CHECKS=0")
            mysql_checks_disabled = True
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")

        policy_map = {
            policy.id: next(
                target_policy.id for target_policy in context["destination_policies"] if target_policy.domain == policy.domain
            )
            for policy in context["source_policies"]
        }

        for table in _metadata_tables():
            scope = _row_scope(
                table,
                tenant_container_id=context["source"].id,
                company_id=company_id,
                store_ids=context["store_ids"],
                user_ids=context["user_ids"],
                file_ids=context["file_ids"],
                conversation_ids=context["conversation_ids"],
                message_ids=context["message_ids"],
            )
            if scope is None:
                continue
            values: dict[str, Any] = {"tenant_container_id": context["destination"].id}
            if table.name == _POLICY_SCOPE and "policy_id" in table.c and policy_map:
                values["policy_id"] = case(policy_map, value=table.c.policy_id, else_=table.c.policy_id)
            db.session.execute(update(table).where(scope).values(**values))

        # The self-reference is re-parented into the destination boundary only
        # after its selected parent has been validated there.
        moved_company_query = update(Company).where(
            Company.id == company_id,
            Company.tenant_container_id == context["source"].id,
        ).values(
            tenant_container_id=context["destination"].id,
            parent_company_id=destination_parent_company_id,
            updated_at=datetime.now(timezone.utc),
        )
        db.session.execute(moved_company_query)

        # Revoke old sessions and realtime subscriptions for every moved
        # company member. The new access events are recorded in the destination.
        from ..realtime.service import clear_user_subscriptions, publish_realtime_event, stage_access_revocation

        moved_user_ids = list(context["user_ids"])
        for user_id in moved_user_ids:
            db.session.execute(
                update(User).where(User.id == user_id).values(auth_version=User.auth_version + 1)
            )
            published_event_ids.append(
                stage_access_revocation(
                    user_id=user_id,
                    # Keep the revocation notice in the old container so its
                    # existing sockets receive it; company_id=None prevents the
                    # notice itself from following the company row.
                    tenant_container_id=context["source"].id,
                    company_id=None,
                    actor_user_id=actor_user_id,
                )
            )

        if plan.source_will_archive:
            context["source"].is_active = False
            context["source"].updated_at = datetime.now(timezone.utc)

        counts = dict(plan.row_counts)
        db.session.add(
            AuditEvent(
                tenant_container_id=context["destination"].id,
                company_id=company_id,
                actor_user_id=actor_user_id,
                action="company.container_transferred",
                entity_type="company",
                entity_id=company_id,
                reason=reason,
                before_data={"tenant_container_id": context["source"].id},
                after_data={
                    "tenant_container_id": context["destination"].id,
                    "parent_company_id": destination_parent_company_id,
                    "moved_row_counts": counts,
                    "source_container_archived": plan.source_will_archive,
                },
            )
        )
        for container_id, before_id, after_id in (
            (context["source"].id, context["source"].id, context["destination"].id),
            (context["destination"].id, context["source"].id, context["destination"].id),
        ):
            db.session.add(
                PlatformAuditEvent(
                    tenant_container_id=container_id,
                    actor_user_id=actor_user_id,
                    action="company.container_transferred",
                    entity_type="company",
                    entity_id=company_id,
                    before_data={"tenant_container_id": before_id},
                    after_data={
                        "tenant_container_id": after_id,
                        "source_container_archived": plan.source_will_archive,
                        "moved_row_counts": counts,
                    },
                    reason=reason,
                )
            )

        db.session.flush()
        _validate_moved_foreign_keys(context)

        if mysql_checks_disabled:
            connection.exec_driver_sql("SET SESSION FOREIGN_KEY_CHECKS=1")
            mysql_checks_disabled = False
        db.session.commit()
    except CompanyTransferError:
        db.session.rollback()
        raise
    except Exception as error:
        db.session.rollback()
        if isinstance(error, SQLAlchemyError):
            raise CompanyTransferError("The transfer could not be committed. The database transaction was rolled back.") from error
        raise
    finally:
        if mysql_checks_disabled and connection is not None:
            try:
                connection.exec_driver_sql("SET SESSION FOREIGN_KEY_CHECKS=1")
            except Exception:
                connection.invalidate()

    for user_id in moved_user_ids:
        try:
            clear_user_subscriptions(user_id)
        except Exception as error:
            current_app.logger.warning("Company-transfer socket cleanup deferred (%s)", type(error).__name__)
    for event_id in published_event_ids:
        try:
            publish_realtime_event(event_id)
        except Exception as error:
            # The durable outbox row remains and can be replayed by the worker.
            current_app.logger.warning("Company-transfer revocation publish deferred (%s)", type(error).__name__)

    return {
        "company_id": company_id,
        "source_container_id": context["source"].id,
        "destination_container_id": context["destination"].id,
        "moved_row_counts": plan.row_counts,
        "moved_store_count": plan.store_count,
        "moved_member_count": plan.member_count,
        "source_container_archived": plan.source_will_archive,
    }
