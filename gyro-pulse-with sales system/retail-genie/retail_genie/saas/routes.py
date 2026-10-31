"""Platform-managed subscription plans and tenant billing portal."""

from datetime import date

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.permissions import company_admin_required, super_admin_required
from ..auth.tenant_context import current_tenant_container_id
from ..extensions import db
from ..models import (
    PlanChangeRequest,
    PlatformAuditEvent,
    SubscriptionInvoice,
    SubscriptionPlan,
    TenantContainer,
    TenantSubscription,
)
from .forms import PlanChangeRequestForm, ReviewPlanRequestForm, SubscriptionPlanForm, TenantSubscriptionForm
from .service import (
    SaaSRuleError,
    assign_subscription,
    create_plan_change_request,
    create_subscription_invoice,
    mark_subscription_invoice_paid,
    review_plan_change_request,
    tenant_subscription,
    tenant_usage,
)

from . import saas_bp


@saas_bp.before_app_request
def enforce_suspended_subscription_read_only():
    """Allow suspended tenants to inspect/request service but block writes."""
    if request.method in {"GET", "HEAD", "OPTIONS"} or not current_user.is_authenticated or current_user.is_super_admin:
        return None
    if request.endpoint in {"auth.logout", "auth.change_password", "auth.select_tenant", "saas.tenant_portal", "static"}:
        return None
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        return None
    subscription, _plan = tenant_subscription(tenant_id)
    if subscription is None or subscription.status not in {"suspended", "canceled"}:
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="tenant_subscription_inactive"), 403
    flash("This tenant is read-only because its subscription is suspended or canceled. Review the plan page or contact the Main Admin.", "error")
    return redirect(url_for("saas.tenant_portal"))


def _platform_audit(action: str, entity_type: str, entity_id: str, *, before=None, after=None, reason=None):
    db.session.add(
        PlatformAuditEvent(
            actor_user_id=current_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            reason=(reason or "").strip()[:500] or None,
        )
    )


@saas_bp.route("/admin/saas/plans", methods=["GET", "POST"])
@super_admin_required
def plans():
    form = SubscriptionPlanForm()
    if form.validate_on_submit():
        plan = SubscriptionPlan(
            code=(form.code.data or "").strip().lower(),
            name=(form.name.data or "").strip(),
            description=(form.description.data or "").strip() or None,
            monthly_price=form.monthly_price.data,
            max_companies=form.max_companies.data,
            max_stores=form.max_stores.data,
            max_active_users=form.max_active_users.data,
            features=sorted({value.strip() for value in (form.features.data or "").split(",") if value.strip()}),
            is_active=bool(form.is_active.data),
            sort_order=form.sort_order.data or 100,
        )
        db.session.add(plan)
        db.session.flush()
        _platform_audit(
            "saas.plan_created",
            "subscription_plan",
            plan.id,
            after={"code": plan.code, "name": plan.name, "monthly_price": str(plan.monthly_price)},
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.code.errors.append("That plan code is already in use.")
        else:
            flash(f"Plan '{plan.name}' created.", "success")
            return redirect(url_for("saas.plans"))
    plan_rows = SubscriptionPlan.query.order_by(SubscriptionPlan.sort_order, SubscriptionPlan.name).all()
    return render_template("saas/plans.html", form=form, plans=plan_rows)


@saas_bp.post("/admin/saas/plans/<string:plan_id>/toggle")
@super_admin_required
def toggle_plan(plan_id: str):
    plan = db.session.get(SubscriptionPlan, plan_id)
    if plan is None:
        abort(404)
    before = {"is_active": plan.is_active}
    plan.is_active = not plan.is_active
    _platform_audit(
        "saas.plan_status_changed",
        "subscription_plan",
        plan.id,
        before=before,
        after={"is_active": plan.is_active},
    )
    db.session.commit()
    flash(f"Plan '{plan.name}' is now {'available' if plan.is_active else 'archived'}.", "success")
    return redirect(url_for("saas.plans"))


@saas_bp.get("/admin/saas/subscriptions")
@super_admin_required
def subscriptions():
    tenants = TenantContainer.query.order_by(TenantContainer.name.asc()).all()
    current_by_tenant = {
        row.tenant_container_id: row
        for row in TenantSubscription.query.order_by(TenantSubscription.updated_at.desc()).all()
    }
    plan_by_id = {row.id: row for row in SubscriptionPlan.query.all()}
    usage_by_tenant = {tenant.id: tenant_usage(tenant.id) for tenant in tenants}
    tenant_by_id = {tenant.id: tenant for tenant in tenants}
    invoices = SubscriptionInvoice.query.order_by(SubscriptionInvoice.issued_at.desc()).limit(100).all()
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.sort_order, SubscriptionPlan.name).all()
    return render_template(
        "saas/subscriptions.html",
        tenants=tenants,
        subscriptions=current_by_tenant,
        plan_by_id=plan_by_id,
        usage_by_tenant=usage_by_tenant,
        tenant_by_id=tenant_by_id,
        invoices=invoices,
        plans=plans,
        status_choices=["trialing", "active", "past_due", "suspended", "canceled"],
    )


@saas_bp.post("/admin/saas/subscriptions/<string:tenant_container_id>")
@super_admin_required
def save_subscription(tenant_container_id: str):
    form = TenantSubscriptionForm()
    form.plan_id.choices = [(plan.id, f"{plan.name} · OMR {plan.monthly_price}") for plan in SubscriptionPlan.query.filter_by(is_active=True).all()]
    if not form.validate_on_submit():
        flash("Review the subscription fields and try again.", "error")
        return redirect(url_for("saas.subscriptions"))
    try:
        assign_subscription(
            tenant_container_id,
            form.plan_id.data,
            form.status.data,
            current_user.id,
            internal_note=form.internal_note.data,
        )
    except SaaSRuleError as error:
        flash(str(error), "error")
    else:
        flash("Tenant subscription saved and audit recorded.", "success")
    return redirect(url_for("saas.subscriptions"))


@saas_bp.route("/subscription", methods=["GET", "POST"])
@company_admin_required
def tenant_portal():
    tenant_id = current_tenant_container_id(current_user)
    tenant = db.session.get(TenantContainer, tenant_id) if tenant_id else None
    if tenant is None:
        abort(404)
    subscription, plan = tenant_subscription(tenant.id)
    usage = tenant_usage(tenant.id)
    request_form = PlanChangeRequestForm()
    available_plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.sort_order, SubscriptionPlan.name).all()
    request_form.plan_id.choices = [(row.id, f"{row.name} · OMR {row.monthly_price}/month") for row in available_plans]
    if request_form.validate_on_submit():
        try:
            create_plan_change_request(
                tenant.id,
                current_user.id,
                request_form.plan_id.data,
                request_form.note.data,
            )
        except SaaSRuleError as error:
            flash(str(error), "error")
        else:
            flash("Plan change request sent to the Main Admin for review.", "success")
            return redirect(url_for("saas.tenant_portal"))
    invoices = SubscriptionInvoice.query.filter_by(tenant_container_id=tenant.id).order_by(SubscriptionInvoice.issued_at.desc()).all()
    pending = PlanChangeRequest.query.filter_by(tenant_container_id=tenant.id, status="pending").first()
    return render_template(
        "saas/tenant_portal.html",
        tenant=tenant,
        subscription=subscription,
        plan=plan,
        usage=usage,
        invoices=invoices,
        pending_request=pending,
        form=request_form,
    )


@saas_bp.get("/admin/saas/requests")
@super_admin_required
def plan_requests():
    requests = PlanChangeRequest.query.order_by(
        PlanChangeRequest.status.asc(), PlanChangeRequest.created_at.desc()
    ).all()
    plans = {plan.id: plan for plan in SubscriptionPlan.query.all()}
    tenants = {tenant.id: tenant for tenant in TenantContainer.query.all()}
    return render_template("saas/requests.html", requests=requests, plans=plans, tenants=tenants)


@saas_bp.post("/admin/saas/requests/<string:request_id>")
@super_admin_required
def review_request(request_id: str):
    form = ReviewPlanRequestForm()
    if not form.validate_on_submit():
        flash("Choose approve or reject and review the note.", "error")
        return redirect(url_for("saas.plan_requests"))
    try:
        review_plan_change_request(
            request_id,
            current_user.id,
            approve=form.decision.data == "approve",
            review_note=form.review_note.data,
        )
    except SaaSRuleError as error:
        flash(str(error), "error")
    else:
        flash("Plan request reviewed.", "success")
    return redirect(url_for("saas.plan_requests"))


@saas_bp.post("/admin/saas/subscriptions/<string:tenant_container_id>/invoices")
@super_admin_required
def issue_invoice(tenant_container_id: str):
    try:
        start = date.fromisoformat(request.form.get("period_start", ""))
        end = date.fromisoformat(request.form.get("period_end", ""))
        due_days = int(request.form.get("due_days", "14"))
        invoice = create_subscription_invoice(
            tenant_container_id,
            current_user.id,
            period_start=start,
            period_end=end,
            due_days=due_days,
        )
    except (ValueError, TypeError) as error:
        flash(str(error) or "Enter valid invoice period dates.", "error")
    else:
        flash(f"Invoice {invoice.invoice_number} issued for OMR {invoice.amount_due}.", "success")
    return redirect(url_for("saas.subscriptions"))


@saas_bp.post("/admin/saas/invoices/<string:invoice_id>/record-payment")
@super_admin_required
def record_invoice_payment(invoice_id: str):
    try:
        mark_subscription_invoice_paid(invoice_id, current_user.id, request.form.get("reference", ""))
    except SaaSRuleError as error:
        flash(str(error), "error")
    else:
        flash("External payment reference recorded; no gateway was called.", "success")
    return redirect(url_for("saas.subscriptions"))


@saas_bp.get("/subscription/invoices/<string:invoice_id>/print")
@company_admin_required
def print_invoice(invoice_id: str):
    tenant_id = current_tenant_container_id(current_user)
    invoice = db.session.execute(
        select(SubscriptionInvoice).where(
            SubscriptionInvoice.id == invoice_id,
            SubscriptionInvoice.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if invoice is None:
        abort(404)
    tenant = db.session.get(TenantContainer, tenant_id)
    return render_template("saas/invoice_print.html", invoice=invoice, tenant=tenant)
