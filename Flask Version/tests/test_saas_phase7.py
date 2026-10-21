"""Phase 7 SaaS plan, quota, request, and manual subscription invoice tests."""

from datetime import date
from decimal import Decimal

import pytest

from retail_genie.extensions import db
from retail_genie.models import (
    PlanChangeRequest,
    PlatformAuditEvent,
    SubscriptionInvoice,
    SubscriptionPlan,
    TenantContainer,
    TenantSubscription,
    User,
)
from retail_genie.saas.service import (
    SaaSRuleError,
    assign_subscription,
    create_subscription_invoice,
    ensure_capacity,
    mark_subscription_invoice_paid,
)


def _plan(app, **values):
    with app.app_context():
        plan = SubscriptionPlan(
            code=values.get("code", "phase7-standard"),
            name=values.get("name", "Phase 7 Standard"),
            monthly_price=Decimal(values.get("monthly_price", "12.500")),
            max_companies=values.get("max_companies", 3),
            max_stores=values.get("max_stores", 5),
            max_active_users=values.get("max_active_users", 10),
            is_active=values.get("is_active", True),
            features=values.get("features", ["inventory", "reports"]),
        )
        db.session.add(plan)
        db.session.commit()
        return plan.id


def _login(client, username):
    return client.post("/login", data={"username": username, "password": "A-long-test-password-4!"})


def test_platform_admin_manages_plan_catalog_and_audit(app, create_user):
    create_user("saas.platform", role="super_admin")
    client = app.test_client()
    _login(client, "saas.platform")

    response = client.post("/admin/saas/plans", data={
        "code": "starter", "name": "Starter", "monthly_price": "0.000",
        "max_companies": "1", "max_stores": "2", "max_active_users": "5",
        "features": "POS, reports", "sort_order": "1", "is_active": "y", "submit": "Create plan",
    })

    assert response.status_code == 302
    with app.app_context():
        plan = SubscriptionPlan.query.filter_by(code="starter").one()
        assert plan.monthly_price == Decimal("0.000")
        assert plan.features == ["POS", "reports"]
        assert PlatformAuditEvent.query.filter_by(action="saas.plan_created", entity_id=plan.id).one()


def test_tenant_admin_can_view_usage_and_request_a_plan_change(app, client, create_user):
    create_user("saas.tenant", role="company_admin")
    plan_id = _plan(app)
    _login(client, "saas.tenant")

    page = client.get("/subscription")
    assert page.status_code == 200
    assert b"grandfathered/unmetered" in page.data
    assert b"Companies" in page.data and b"Stores" in page.data
    requested = client.post("/subscription", data={"plan_id": plan_id, "note": "Need a second branch", "submit": "Request plan change"})
    assert requested.status_code == 302
    with app.app_context():
        change = PlanChangeRequest.query.filter_by(tenant_container_id="test-container").one()
        assert change.status == "pending"
        assert change.request_note == "Need a second branch"


def test_only_platform_admin_can_manage_plan_catalog(client, create_user):
    create_user("saas.manager", role="manager", permissions=["manage_settings"])
    _login(client, "saas.manager")
    assert client.get("/admin/saas/plans").status_code == 403
    assert client.post("/admin/saas/subscriptions/test-container").status_code == 403


def test_platform_approval_assigns_plan_and_enforces_company_quota(app, create_user):
    create_user("saas.tenant", role="company_admin")
    create_user("saas.platform", role="super_admin")
    plan_id = _plan(app, max_companies=1, max_stores=1, max_active_users=1)
    with app.app_context():
        from retail_genie.saas.service import create_plan_change_request
        tenant_user_id = User.query.filter_by(username="saas.tenant").one().id
        change = create_plan_change_request("test-container", tenant_user_id, plan_id)
        request_id = change.id

    platform_client = app.test_client()
    _login(platform_client, "saas.platform")
    reviewed = platform_client.post(f"/admin/saas/requests/{request_id}", data={"decision": "approve", "review_note": "Approved"})
    assert reviewed.status_code == 302
    with app.app_context():
        subscription = TenantSubscription.query.filter_by(tenant_container_id="test-container").one()
        assert subscription.plan_id == plan_id
        assert subscription.status == "trialing"
        assert db.session.get(PlanChangeRequest, request_id).status == "approved"
        for resource, label in (("company", "company"), ("store", "store"), ("active_user", "active user")):
            with pytest.raises(SaaSRuleError, match=f"allows 1 {label}"):
                ensure_capacity("test-container", resource)


def test_suspended_tenant_is_read_only_but_can_request_service(app, create_user):
    create_user("saas.suspended", role="company_admin")
    plan_id = _plan(app)
    with app.app_context():
        user_id = User.query.filter_by(username="saas.suspended").one().id
        assign_subscription("test-container", plan_id, "suspended", user_id)
    client = app.test_client()
    _login(client, "saas.suspended")

    assert client.get("/dashboard").status_code == 200
    blocked = client.post("/api/v1/orders", json={})
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "tenant_subscription_inactive"
    portal = client.post("/subscription", data={"plan_id": plan_id, "note": "Please reactivate", "submit": "Request plan change"})
    assert portal.status_code == 302


def test_subscription_invoice_print_is_tenant_scoped_and_uses_three_omr_decimals(app, create_user):
    create_user("saas.print-admin", role="company_admin")
    create_user("saas.platform", role="super_admin")
    plan_id = _plan(app, monthly_price="7.125")
    with app.app_context():
        platform_id = User.query.filter_by(username="saas.platform").one().id
        assign_subscription("test-container", plan_id, "active", platform_id)
        own_invoice = create_subscription_invoice(
            "test-container", platform_id, period_start=date(2026, 10, 1), period_end=date(2026, 11, 1)
        )
        other_tenant = TenantContainer(id="other-container", name="Other Tenant", slug="other-tenant")
        db.session.add(other_tenant)
        db.session.commit()
        assign_subscription("other-container", plan_id, "active", platform_id)
        other_invoice = create_subscription_invoice(
            "other-container", platform_id, period_start=date(2026, 10, 1), period_end=date(2026, 11, 1)
        )
        own_invoice_id, other_invoice_id = own_invoice.id, other_invoice.id

    client = app.test_client()
    _login(client, "saas.print-admin")
    own_page = client.get(f"/subscription/invoices/{own_invoice_id}/print")
    assert own_page.status_code == 200
    assert b"OMR 7.125" in own_page.data
    assert client.get(f"/subscription/invoices/{other_invoice_id}/print").status_code == 404


def test_manual_subscription_invoice_is_omr_idempotent_and_audited(app, create_user):
    create_user("saas.platform", role="super_admin")
    plan_id = _plan(app, monthly_price="7.125")
    with app.app_context():
        actor_id = User.query.filter_by(username="saas.platform").one().id
        assign_subscription("test-container", plan_id, "active", actor_id)
        invoice = create_subscription_invoice(
            "test-container", actor_id, period_start=date(2026, 10, 1), period_end=date(2026, 11, 1)
        )
        invoice_id = invoice.id
        assert invoice.amount_due == Decimal("7.125")
        assert invoice.currency == "OMR"
        assert invoice.status == "open"
        with pytest.raises(SaaSRuleError, match="already exists"):
            create_subscription_invoice(
                "test-container", actor_id, period_start=date(2026, 10, 1), period_end=date(2026, 11, 1)
            )
        paid = mark_subscription_invoice_paid(invoice_id, actor_id, "BANK-REF-001")
        assert paid.status == "paid"
        assert paid.paid_reference == "BANK-REF-001"
        assert PlatformAuditEvent.query.filter_by(entity_id=invoice_id).count() == 2
        with pytest.raises(SaaSRuleError, match="Only an open invoice"):
            mark_subscription_invoice_paid(invoice_id, actor_id, "BANK-REF-002")
