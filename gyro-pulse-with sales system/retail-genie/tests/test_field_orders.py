from copy import deepcopy
from decimal import Decimal
from uuid import uuid4
import pytest
from test_field_catalog import native
from retail_genie.extensions import db
from retail_genie.models import (
    User,
    OrderNumberSeries,
    SalesOrder,
    InventoryBalance,
    InventoryMovement,
    TaxSetting,
)
from retail_genie.field_integration import FieldConnection
from retail_genie.field_orders import (
    stage_message,
    review,
    FieldProposal,
    FieldReviewAudit,
    context_for,
)
from retail_genie.order_contract import OrderError, validate
from retail_genie.sync_core import Transport
from retail_genie.sales.service import SalesRuleError


@pytest.fixture
def staged(native):
    app, company, store, product = native
    app.secret_key = "native-review-tests-only-" + "x" * 32
    from retail_genie.realtime.service import initialize_realtime_registry

    initialize_realtime_registry(app)
    from retail_genie.tenancy.service import seed_tenant_data_policies

    seed_tenant_data_policies(company.tenant_container_id)
    actor = User(username="native-approver", password_hash="unused", role="super_admin")
    db.session.add(actor)
    db.session.add(
        OrderNumberSeries(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            prefix="FIELD-",
            next_number=1,
        )
    )
    db.session.commit()
    connection = db.session.get(FieldConnection, company.id)
    cloud = Transport("gyro", company.id, connection.instance_id, connection.office_id)
    payload = dict(
        schema_version=1,
        order_id=str(uuid4()),
        store_id=store.id,
        catalog_message_id=str(uuid4()),
        customer_phone="+968 91234567",
        customer_name="Synthetic Customer",
        items=[dict(product_id=product.id, quantity=2, unit_price="1.250")],
    )
    envelope = cloud.envelope("field.order", payload)
    office = context_for(company.id)
    office.accept(envelope)
    db.session.commit()
    proposal = stage_message(company.id, envelope["message_id"])
    db.session.commit()
    return app, company, store, product, actor, cloud, payload, proposal


def test_stage_never_posts_and_business_id_dedup(staged):
    _, c, s, p, actor, cloud, payload, proposal = staged
    assert (
        SalesOrder.query.count() == 0
        and InventoryMovement.query.count() == 0
        and InventoryBalance.query.one().quantity_on_hand == 12
    )
    second = cloud.envelope("field.order", payload)
    context_for(c.id).accept(second)
    db.session.commit()
    assert stage_message(c.id, second["message_id"]).id == proposal.id
    assert FieldProposal.query.count() == 1
    altered = deepcopy(payload)
    altered["items"][0]["quantity"] = 3
    third = cloud.envelope("field.order", altered)
    context_for(c.id).accept(third)
    db.session.commit()
    with pytest.raises(OrderError):
        stage_message(c.id, third["message_id"])


def test_actual_native_posting_once_and_final_rejection(staged):
    app, c, s, p, actor, _, payload, proposal = staged
    with app.test_request_context():
        native_id = review(actor, c.id, proposal.id, approve=True)
        assert review(actor, c.id, proposal.id, approve=True) == native_id
    assert SalesOrder.query.count() == 1 and FieldReviewAudit.query.count() == 1
    assert (
        InventoryBalance.query.one().quantity_on_hand == 10
        and InventoryMovement.query.count() == 1
    )
    assert (
        FieldProposal.query.one().state == "approved"
        and SalesOrder.query.one().total_amount == Decimal("2.500")
    )
    with app.test_request_context(), pytest.raises(OrderError):
        review(actor, c.id, proposal.id, approve=False, reason="too late")


def test_rejection_is_final_without_native_stock_change(staged):
    app, c, _, _, actor, _, _, proposal = staged
    with app.test_request_context():
        review(actor, c.id, proposal.id, approve=False, reason="Customer cancelled")
        review(actor, c.id, proposal.id, approve=False, reason="same retry")
        with pytest.raises(OrderError):
            review(actor, c.id, proposal.id, approve=True)
    assert (
        FieldProposal.query.one().state == "rejected"
        and FieldReviewAudit.query.count() == 1
    )
    assert (
        SalesOrder.query.count() == 0
        and InventoryBalance.query.one().quantity_on_hand == 12
    )


@pytest.mark.parametrize(
    "failure", ["price", "archived", "stock", "tax", "audit_failure"]
)
def test_failure_rolls_back_native_order_stock_series_and_link(
    staged, failure, monkeypatch
):
    app, c, s, p, actor, _, _, proposal = staged
    if failure == "price":
        p.price = Decimal("2.000")
    elif failure == "archived":
        p.is_active = False
    elif failure == "stock":
        InventoryBalance.query.one().quantity_on_hand = 1
    elif failure == "tax":
        db.session.add(
            TaxSetting(
                tenant_container_id=c.tenant_container_id,
                company_id=c.id,
                name="Test tax",
                rate=Decimal("5"),
                is_enabled=True,
            )
        )
    db.session.commit()
    before = InventoryBalance.query.one().quantity_on_hand
    if failure == "audit_failure":
        from retail_genie import field_orders

        original = field_orders._decision

        def crash(*args):
            original(*args)
            raise OrderError("Crash before native commit")

        monkeypatch.setattr(field_orders, "_decision", crash)
    with app.test_request_context(), pytest.raises((OrderError, SalesRuleError)):
        review(actor, c.id, proposal.id, approve=True)
    db.session.rollback()
    assert (
        SalesOrder.query.count() == 0
        and InventoryMovement.query.count() == 0
        and FieldReviewAudit.query.count() == 0
    )
    assert (
        FieldProposal.query.one().state == "pending"
        and FieldProposal.query.one().native_order_id is None
    )
    assert (
        InventoryBalance.query.one().quantity_on_hand == before
        and OrderNumberSeries.query.one().next_number == 1
    )


def test_inactive_approver_and_foreign_company_denied(staged):
    app, c, _, _, actor, _, _, proposal = staged
    actor.is_active = False
    db.session.commit()
    with app.test_request_context(), pytest.raises(SalesRuleError):
        review(actor, c.id, proposal.id, approve=True)
    db.session.rollback()
    with pytest.raises(OrderError):
        review(actor, str(uuid4()), proposal.id, approve=True)
    assert SalesOrder.query.count() == 0


@pytest.mark.parametrize(
    "key,value",
    [
        ("quantity", True),
        ("quantity", 0),
        ("unit_price", 1.25),
        ("unit_price", "0.000"),
    ],
)
def test_contract_strict_numbers(staged, key, value):
    *_, payload, proposal = staged
    bad = deepcopy(payload)
    bad["items"][0][key] = value
    with pytest.raises(OrderError):
        validate(bad)


def test_missing_native_policy_and_nonapprover_denied(staged):
    app, c, _, _, actor, _, _, proposal = staged
    from retail_genie.models import TenantDataPolicy

    TenantDataPolicy.query.filter_by(
        tenant_container_id=c.tenant_container_id, domain="sales"
    ).delete()
    db.session.commit()
    with app.test_request_context(), pytest.raises(SalesRuleError):
        review(actor, c.id, proposal.id, approve=True)
    cashier = User(
        username="no-approve", password_hash="unused", role="cashier", permissions=[]
    )
    db.session.add(cashier)
    db.session.commit()
    with app.test_request_context(), pytest.raises(SalesRuleError):
        review(cashier, c.id, proposal.id, approve=False, reason="not allowed")
    assert SalesOrder.query.count() == 0 and FieldReviewAudit.query.count() == 0


def test_mutated_persisted_proposal_cannot_be_approved(staged):
    app, c, _, _, actor, _, _, proposal = staged
    altered = deepcopy(proposal.payload)
    altered["items"][0]["quantity"] = 9
    proposal.payload = altered
    db.session.commit()
    with app.test_request_context(), pytest.raises(OrderError):
        review(actor, c.id, proposal.id, approve=True)
    assert SalesOrder.query.count() == 0


def test_review_form_csrf_and_explicit_confirmation(staged):
    app, c, _, _, actor, _, _, proposal = staged
    from flask_login import LoginManager
    from flask_wtf.csrf import CSRFProtect
    from jinja2 import FileSystemLoader
    from pathlib import Path
    from retail_genie.field_orders import bp

    app.secret_key = "native-ui-unit-test-only-" + "x" * 32
    login = LoginManager(app)
    login.session_protection = None
    login.user_loader(lambda user_id: db.session.get(User, user_id))
    CSRFProtect(app)
    app.register_blueprint(bp)
    app.jinja_loader = FileSystemLoader(
        str(Path(__file__).resolve().parents[1] / "retail_genie/templates")
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = actor.id
        session["_fresh"] = True
    url = "/settings/field-orders?company_id=" + c.id
    page = client.get(url)
    assert page.status_code == 200
    assert (
        client.post(
            url, data={"proposal_id": proposal.id, "decision": "approve"}
        ).status_code
        == 400
    )
    import re, html

    csrf = html.unescape(
        re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    )
    assert (
        client.post(
            url,
            data={
                "csrf_token": csrf,
                "proposal_id": proposal.id,
                "decision": "approve",
            },
        ).status_code
        == 400
    )
    response = client.post(
        url,
        data={
            "csrf_token": csrf,
            "proposal_id": proposal.id,
            "decision": "approve",
            "confirm_native_prices": "yes",
        },
    )
    assert response.status_code == 200
    assert (
        SalesOrder.query.count() == 1 and FieldProposal.query.one().state == "approved"
    )


def test_real_company_membership_scope_and_company_admin_posting(staged):
    app, c, _, _, _, _, _, proposal = staged
    from flask import session
    from retail_genie.models import ContainerMembership, Company

    other = Company(
        tenant_container_id=c.tenant_container_id,
        name="Foreign Company",
        slug="foreign",
    )
    db.session.add(other)
    db.session.flush()
    actor = User(
        username="company-reviewer",
        password_hash="unused",
        role="company_admin",
        company_id=other.id,
    )
    db.session.add(actor)
    db.session.flush()
    membership = ContainerMembership(
        tenant_container_id=c.tenant_container_id,
        company_id=other.id,
        user_id=actor.id,
        role="company_admin",
    )
    db.session.add(membership)
    db.session.commit()
    with app.test_request_context():
        session["active_container_id"] = c.tenant_container_id
        with pytest.raises(SalesRuleError):
            review(actor, c.id, proposal.id, approve=True)
    assert SalesOrder.query.count() == 0
    membership.company_id = c.id
    actor.company_id = c.id
    db.session.commit()
    with app.test_request_context():
        session["active_container_id"] = c.tenant_container_id
        native_id = review(actor, c.id, proposal.id, approve=True)
    assert (
        FieldProposal.query.one().native_order_id == native_id
        and SalesOrder.query.count() == 1
    )


def test_existing_native_create_order_default_path_unchanged(staged):
    app, c, s, p, actor, _, _, proposal = staged
    from retail_genie.sales.service import create_order

    with app.test_request_context():
        order = create_order(
            actor,
            company_id=c.id,
            store_id=s.id,
            customer_phone="+96891234567",
            items=[{"product_id": p.id, "quantity": 1}],
        )
    assert (
        order.id
        and SalesOrder.query.count() == 1
        and InventoryBalance.query.one().quantity_on_hand == 11
    )
    assert (
        FieldProposal.query.one().state == "pending"
        and FieldReviewAudit.query.count() == 0
    )
