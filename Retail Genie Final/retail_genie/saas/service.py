"""Tenant subscription usage, quota enforcement, and plan-change workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    AuditEvent,
    Company,
    ContainerMembership,
    PlanChangeRequest,
    PlatformAuditEvent,
    Store,
    SubscriptionInvoice,
    SubscriptionPlan,
    TenantContainer,
    TenantSubscription,
)


class SaaSRuleError(ValueError):
    """A plan, quota, or subscription operation violates platform policy."""


@dataclass(frozen=True)
class TenantUsage:
    companies: int
    stores: int
    active_users: int


def tenant_usage(tenant_container_id: str) -> TenantUsage:
    """Count active tenant resources without crossing container boundaries."""
    companies = db.session.scalar(
        select(func.count(Company.id)).where(
            Company.tenant_container_id == tenant_container_id,
            Company.is_active.is_(True),
        )
    ) or 0
    stores = db.session.scalar(
        select(func.count(Store.id)).where(
            Store.tenant_container_id == tenant_container_id,
            Store.is_active.is_(True),
        )
    ) or 0
    active_users = db.session.scalar(
        select(func.count(distinct(ContainerMembership.user_id))).where(
            ContainerMembership.tenant_container_id == tenant_container_id,
            ContainerMembership.is_active.is_(True),
        )
    ) or 0
    return TenantUsage(companies=int(companies), stores=int(stores), active_users=int(active_users))


def tenant_subscription(tenant_container_id: str) -> tuple[TenantSubscription | None, SubscriptionPlan | None]:
    subscription = db.session.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_container_id == tenant_container_id)
    ).scalar_one_or_none()
    plan = db.session.get(SubscriptionPlan, subscription.plan_id) if subscription else None
    return subscription, plan


def _limit_for(plan: SubscriptionPlan, resource: str) -> int | None:
    return {
        "company": plan.max_companies,
        "store": plan.max_stores,
        "active_user": plan.max_active_users,
    }[resource]


def ensure_capacity(tenant_container_id: str, resource: str, *, additional: int = 1) -> None:
    """Lock the tenant row and enforce a currently assigned plan's quota.

    No subscription means a grandfathered, unmetered tenant. This avoids
    silently imposing commercial terms on existing customers during rollout.
    """
    if resource not in {"company", "store", "active_user"} or additional < 1:
        raise ValueError("Unsupported quota resource or additional count.")
    tenant = db.session.execute(
        select(TenantContainer)
        .where(TenantContainer.id == tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise SaaSRuleError("This tenant is not active.")
    subscription, plan = tenant_subscription(tenant_container_id)
    if subscription is None or plan is None:
        return
    if subscription.status in {"suspended", "canceled"}:
        raise SaaSRuleError("Provisioning is unavailable for a suspended or canceled subscription.")
    limit = _limit_for(plan, resource)
    if limit is None:
        return
    usage = tenant_usage(tenant_container_id)
    current = {
        "company": usage.companies,
        "store": usage.stores,
        "active_user": usage.active_users,
    }[resource]
    if current + additional > limit:
        label = {"company": "company", "store": "store", "active_user": "active user"}[resource]
        raise SaaSRuleError(
            f"The {plan.name} plan allows {limit} {label}{'' if limit == 1 else 's'}; "
            f"current usage is {current}. Ask a Main Admin to review your plan."
        )


def plan_fits_usage(plan: SubscriptionPlan, usage: TenantUsage) -> bool:
    """Return whether the current tenant fits all non-null plan limits."""
    return all(
        limit is None or used <= limit
        for limit, used in (
            (plan.max_companies, usage.companies),
            (plan.max_stores, usage.stores),
            (plan.max_active_users, usage.active_users),
        )
    )


def _audit_subscription_change(
    tenant_container_id: str,
    actor_user_id: str | None,
    *,
    action: str,
    entity_id: str,
    before: dict | None,
    after: dict | None,
    reason: str | None = None,
) -> None:
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_container_id,
            company_id=None,
            store_id=None,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="tenant_subscription",
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            reason=reason,
        )
    )


def _platform_audit(
    actor_user_id: str | None,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    tenant_container_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> None:
    db.session.add(
        PlatformAuditEvent(
            actor_user_id=actor_user_id,
            tenant_container_id=tenant_container_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            reason=(reason or "").strip()[:500] or None,
        )
    )


def create_subscription_invoice(
    tenant_container_id: str,
    actor_user_id: str,
    *,
    period_start: date,
    period_end: date,
    due_days: int = 14,
) -> SubscriptionInvoice:
    if period_end <= period_start or not 1 <= due_days <= 90:
        raise SaaSRuleError("Choose a valid billing period and a due window from 1 to 90 days.")
    tenant = db.session.execute(
        select(TenantContainer)
        .where(TenantContainer.id == tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise SaaSRuleError("This tenant is not active.")
    subscription = db.session.execute(
        select(TenantSubscription)
        .where(TenantSubscription.tenant_container_id == tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    plan = db.session.get(SubscriptionPlan, subscription.plan_id) if subscription else None
    if subscription is None or plan is None:
        raise SaaSRuleError("Assign a subscription plan before issuing an invoice.")
    if subscription.status in {"suspended", "canceled"}:
        raise SaaSRuleError("A subscription invoice cannot be issued for a suspended or canceled subscription.")
    invoice = SubscriptionInvoice(
        tenant_container_id=tenant_container_id,
        subscription_id=subscription.id,
        invoice_number=f"SINV-{datetime.now(timezone.utc):%Y%m}-{uuid4().hex[:8].upper()}",
        period_start=period_start,
        period_end=period_end,
        amount_due=plan.monthly_price,
        currency="OMR",
        status="open",
        due_at=datetime.now(timezone.utc) + timedelta(days=due_days),
        created_by_user_id=actor_user_id,
    )
    db.session.add(invoice)
    try:
        db.session.flush()
        _platform_audit(
            actor_user_id,
            action="subscription.invoice_issued",
            entity_type="subscription_invoice",
            entity_id=invoice.id,
            tenant_container_id=tenant_container_id,
            after={
                "invoice_number": invoice.invoice_number,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "amount_due": str(invoice.amount_due),
                "currency": "OMR",
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise SaaSRuleError("An invoice already exists for this subscription period.") from None
    return invoice


def mark_subscription_invoice_paid(invoice_id: str, actor_user_id: str, reference: str) -> SubscriptionInvoice:
    invoice = db.session.execute(
        select(SubscriptionInvoice).where(SubscriptionInvoice.id == invoice_id).with_for_update()
    ).scalar_one_or_none()
    if invoice is None:
        raise SaaSRuleError("Subscription invoice was not found.")
    if invoice.status != "open":
        raise SaaSRuleError("Only an open invoice can be marked as paid.")
    reference = (reference or "").strip()
    if not reference or len(reference) > 128:
        raise SaaSRuleError("Enter the external payment or receipt reference (up to 128 characters).")
    before = {"status": invoice.status, "paid_reference": invoice.paid_reference}
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.paid_reference = reference
    _platform_audit(
        actor_user_id,
        action="subscription.invoice_paid_recorded",
        entity_type="subscription_invoice",
        entity_id=invoice.id,
        tenant_container_id=invoice.tenant_container_id,
        before=before,
        after={"status": invoice.status, "paid_reference": reference},
    )
    db.session.commit()
    return invoice


def create_plan_change_request(
    tenant_container_id: str,
    requested_by_user_id: str,
    requested_plan_id: str,
    note: str | None = None,
) -> PlanChangeRequest:
    tenant = db.session.execute(
        select(TenantContainer)
        .where(TenantContainer.id == tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise SaaSRuleError("This tenant is not active.")
    plan = db.session.get(SubscriptionPlan, requested_plan_id)
    if plan is None or not plan.is_active:
        raise SaaSRuleError("Choose an active subscription plan.")
    pending = db.session.execute(
        select(PlanChangeRequest).where(
            PlanChangeRequest.tenant_container_id == tenant_container_id,
            PlanChangeRequest.status == "pending",
        )
    ).scalar_one_or_none()
    if pending:
        raise SaaSRuleError("A plan request is already awaiting Main Admin review.")
    subscription, _current_plan = tenant_subscription(tenant_container_id)
    if subscription and subscription.plan_id == plan.id and subscription.status not in {"suspended", "canceled"}:
        raise SaaSRuleError("This plan is already assigned to your tenant.")
    request = PlanChangeRequest(
        tenant_container_id=tenant_container_id,
        requested_plan_id=plan.id,
        requested_by_user_id=requested_by_user_id,
        request_note=(note or "").strip()[:500] or None,
    )
    db.session.add(request)
    db.session.flush()
    _audit_subscription_change(
        tenant_container_id,
        requested_by_user_id,
        action="subscription.plan_change_requested",
        entity_id=request.id,
        before={"plan_id": subscription.plan_id if subscription else None},
        after={"requested_plan_id": plan.id, "status": "pending"},
        reason=request.request_note,
    )
    db.session.commit()
    return request


def review_plan_change_request(
    request_id: str,
    reviewer_user_id: str,
    *,
    approve: bool,
    review_note: str | None = None,
) -> PlanChangeRequest:
    change_request = db.session.execute(
        select(PlanChangeRequest).where(PlanChangeRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if change_request is None or change_request.status != "pending":
        raise SaaSRuleError("This request is no longer pending review.")
    plan = db.session.get(SubscriptionPlan, change_request.requested_plan_id)
    tenant = db.session.execute(
        select(TenantContainer)
        .where(TenantContainer.id == change_request.tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    if plan is None or tenant is None or not tenant.is_active:
        raise SaaSRuleError("The requested plan or tenant is no longer active.")

    subscription, current_plan = tenant_subscription(tenant.id)
    before = {
        "plan_id": current_plan.id if current_plan else None,
        "status": subscription.status if subscription else None,
    }
    if approve:
        usage = tenant_usage(tenant.id)
        if not plan_fits_usage(plan, usage):
            raise SaaSRuleError("The tenant exceeds one or more requested plan limits; reduce usage before approval.")
        if subscription is None:
            subscription = TenantSubscription(
                tenant_container_id=tenant.id,
                plan_id=plan.id,
                status="trialing",
                starts_at=datetime.now(timezone.utc),
                updated_by_user_id=reviewer_user_id,
            )
            db.session.add(subscription)
            db.session.flush()
        else:
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.cancel_at_period_end = False
            subscription.updated_by_user_id = reviewer_user_id
        change_request.status = "approved"
    else:
        change_request.status = "rejected"

    change_request.reviewed_by_user_id = reviewer_user_id
    change_request.reviewed_at = datetime.now(timezone.utc)
    change_request.review_note = (review_note or "").strip()[:500] or None
    db.session.flush()
    _audit_subscription_change(
        tenant.id,
        reviewer_user_id,
        action=f"subscription.plan_change_{change_request.status}",
        entity_id=change_request.id,
        before=before,
        after={"plan_id": plan.id if approve else before["plan_id"], "status": subscription.status if subscription else None},
        reason=change_request.review_note,
    )
    db.session.commit()
    return change_request


def assign_subscription(
    tenant_container_id: str,
    plan_id: str,
    status: str,
    actor_user_id: str,
    *,
    internal_note: str | None = None,
) -> TenantSubscription:
    if status not in {"trialing", "active", "past_due", "suspended", "canceled"}:
        raise SaaSRuleError("Choose a valid subscription status.")
    tenant = db.session.execute(
        select(TenantContainer)
        .where(TenantContainer.id == tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    plan = db.session.get(SubscriptionPlan, plan_id)
    if tenant is None or not tenant.is_active:
        raise SaaSRuleError("Choose an active tenant.")
    if plan is None or not plan.is_active:
        raise SaaSRuleError("Choose an active plan.")
    subscription, old_plan = tenant_subscription(tenant.id)
    if status not in {"suspended", "canceled"} and not plan_fits_usage(plan, tenant_usage(tenant.id)):
        raise SaaSRuleError("Current tenant usage exceeds the selected plan limits.")
    before = {"plan_id": old_plan.id if old_plan else None, "status": subscription.status if subscription else None}
    if subscription is None:
        subscription = TenantSubscription(
            tenant_container_id=tenant.id,
            plan_id=plan.id,
            status=status,
            updated_by_user_id=actor_user_id,
            internal_note=(internal_note or "").strip()[:2000] or None,
        )
        db.session.add(subscription)
        db.session.flush()
    else:
        subscription.plan_id = plan.id
        subscription.status = status
        subscription.updated_by_user_id = actor_user_id
        subscription.internal_note = (internal_note or "").strip()[:2000] or None
        subscription.cancel_at_period_end = status == "canceled"
    _audit_subscription_change(
        tenant.id,
        actor_user_id,
        action="subscription.admin_assigned",
        entity_id=subscription.id,
        before=before,
        after={"plan_id": plan.id, "status": status},
        reason=internal_note,
    )
    db.session.commit()
    return subscription
