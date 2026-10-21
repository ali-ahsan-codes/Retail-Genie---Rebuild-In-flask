import pytest

from retail_genie.commercial.emailing import CommercialEmailError, send_commercial_email
from retail_genie.extensions import db
from retail_genie.models import (
    AuditEvent,
    CatalogProduct,
    Company,
    DemandNotice,
    DemandNoticeFulfillment,
    InventoryBalance,
    InventoryMovement,
    Quotation,
    QuotationLine,
    SalesOrder,
)


SALES_PERMISSIONS = [
    "use_sales_pos",
    "open_bills.view",
    "open_bills.add",
    "open_bills.edit",
    "sales.view",
    "sales.add",
    "sales.edit",
    "product_catalog.view",
    "inventory.view",
]


def _sign_in(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _seed_product(app, *, name="Coffee", sku="COF-1", price="5.000", quantity=20):
    with app.app_context():
        company = db.session.get(Company, "test-company")
        product = CatalogProduct(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            name=name,
            sku=sku,
            price=price,
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(
            InventoryBalance(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                store_id="test-store",
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=quantity,
            )
        )
        db.session.commit()
        return product.id


def test_demand_notice_conversion_links_order_preserves_agreed_price_and_replays(app, client, create_user):
    create_user("notice.sales", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "notice.sales")
    product_id = _seed_product(app)

    created = client.post(
        "/api/v1/demand-notices",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "customer_phone": "+968 9123 4567",
            "customer_name": "Nora Customer",
            "product_id": product_id,
            "quantity_requested": 2,
            "agreed_price": "4.500",
            "expected_availability_date": "2026-11-01",
        },
    )
    assert created.status_code == 201, created.get_json()
    notice = created.get_json()["demand_notice"]
    assert notice["notice_number"] == "DN-000001"
    assert notice["status"] == "open"

    converted = client.post(
        f"/api/v1/demand-notices/{notice['id']}/convert",
        json={"company_id": "test-company"},
    )
    assert converted.status_code == 201, converted.get_json()
    order = converted.get_json()["order"]
    assert order["source_demand_notice_id"] == notice["id"]
    assert order["items"][0]["unit_price"] == "4.500"
    assert order["total_amount"] == "9.000"

    replay = client.post(
        f"/api/v1/demand-notices/{notice['id']}/convert",
        json={"company_id": "test-company"},
    )
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["order"]["id"] == order["id"]

    with app.app_context():
        stored_notice = db.session.get(DemandNotice, notice["id"])
        assert stored_notice.status == "converted"
        assert stored_notice.quantity_fulfilled == 2
        assert SalesOrder.query.filter_by(source_demand_notice_id=notice["id"]).count() == 1
        assert InventoryMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 1
        assert AuditEvent.query.filter(AuditEvent.action.in_(["demand_notice.created", "order.created"])).count() == 2


def test_unlinked_demand_notice_must_be_cancelled_or_linked_before_conversion(app, client, create_user):
    create_user("notice.unlinked", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "notice.unlinked")
    created = client.post(
        "/api/v1/demand-notices",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "customer_phone": "91234567",
            "product_name": "Special imported tea",
            "product_sku": "TEA-NEW",
            "quantity_requested": 3,
            "is_new_product": True,
        },
    )
    assert created.status_code == 201, created.get_json()
    notice_id = created.get_json()["demand_notice"]["id"]
    refused = client.post(f"/api/v1/demand-notices/{notice_id}/convert", json={"company_id": "test-company"})
    assert refused.status_code == 409
    assert refused.get_json()["error"] == "product_link_required"

    cancelled = client.post(
        f"/api/v1/demand-notices/{notice_id}/cancel",
        json={"company_id": "test-company", "reason": "Customer no longer needs it."},
    )
    assert cancelled.status_code == 200
    assert cancelled.get_json()["demand_notice"]["status"] == "cancelled"


def test_accepted_quotation_converts_atomically_to_open_bill_at_snapshot_price(app, client, create_user):
    create_user("quote.sales", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "quote.sales")
    product_id = _seed_product(app, price="5.000", quantity=9)

    created = client.post(
        "/api/v1/quotations",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "customer_name": "Omar Buyer",
            "customer_phone": "91234567",
            "valid_until": "2026-12-31",
            "lines": [{"product_id": product_id, "quantity": 2, "unit_price": "4.250"}],
        },
    )
    assert created.status_code == 201, created.get_json()
    quotation = created.get_json()["quotation"]
    assert quotation["quotation_number"] == "QT-000001"
    assert quotation["total_amount"] == "8.500"
    assert quotation["status"] == "draft"

    sent = client.post(f"/api/v1/quotations/{quotation['id']}/status", json={"company_id": "test-company", "status": "sent"})
    assert sent.status_code == 200
    accepted = client.post(f"/api/v1/quotations/{quotation['id']}/status", json={"company_id": "test-company", "status": "accepted"})
    assert accepted.status_code == 200

    converted = client.post(f"/api/v1/quotations/{quotation['id']}/convert", json={"company_id": "test-company"})
    assert converted.status_code == 201, converted.get_json()
    order = converted.get_json()["order"]
    assert order["source_quotation_id"] == quotation["id"]
    assert order["items"][0]["unit_price"] == "4.250"
    assert order["total_amount"] == "8.500"
    replay = client.post(f"/api/v1/quotations/{quotation['id']}/convert", json={"company_id": "test-company"})
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["order"]["id"] == order["id"]

    with app.app_context():
        stored_quote = db.session.get(Quotation, quotation["id"])
        assert stored_quote.status == "converted"
        assert QuotationLine.query.filter_by(quotation_id=quotation["id"], converted=True).count() == 1
        assert SalesOrder.query.filter_by(source_quotation_id=quotation["id"]).count() == 1
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=product_id).one()
        assert balance.quantity_on_hand == 7
        assert InventoryMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 1


def test_external_quotation_is_not_stock_converted_until_catalog_link_exists(client, create_user):
    create_user("quote.external", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "quote.external")
    created = client.post(
        "/api/v1/quotations",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "customer_phone": "91234567",
            "lines": [{"is_external": True, "product_name": "Imported accessory", "product_sku": "IMP-1", "quantity": 1, "unit_price": "3.000"}],
        },
    )
    assert created.status_code == 201, created.get_json()
    quote_id = created.get_json()["quotation"]["id"]
    assert client.post(f"/api/v1/quotations/{quote_id}/status", json={"company_id": "test-company", "status": "sent"}).status_code == 200
    assert client.post(f"/api/v1/quotations/{quote_id}/status", json={"company_id": "test-company", "status": "accepted"}).status_code == 200
    refused = client.post(f"/api/v1/quotations/{quote_id}/convert", json={"company_id": "test-company"})
    assert refused.status_code == 409
    assert refused.get_json()["error"] == "external_line_unlinked"


def test_commercial_pages_and_tenant_scoping(app, client, create_user):
    create_user("commercial.ui", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "commercial.ui")
    notices = client.get("/demand-notices?store_id=test-store")
    quotes = client.get("/quotations?store_id=test-store")
    assert notices.status_code == 200
    assert b"Record a customer request" in notices.data
    assert quotes.status_code == 200
    assert b"Prepare a quotation" in quotes.data

    foreign = client.get("/api/v1/quotations?company_id=other-company")
    assert foreign.status_code in {403, 404}


def test_sales_view_only_cannot_create_or_email_commercial_documents(client, create_user):
    create_user("commercial.readonly", role="salesperson", permissions=["sales.view"])
    create_user("commercial.writer", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "commercial.writer")
    created = client.post(
        "/api/v1/demand-notices",
        json={"company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567", "product_name": "Restricted email", "quantity_requested": 1},
    )
    assert created.status_code == 201
    notice_id = created.get_json()["demand_notice"]["id"]
    client.post("/logout")
    _sign_in(client, "commercial.readonly")
    response = client.post(
        "/api/v1/demand-notices",
        json={"company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567", "product_name": "No permission", "quantity_requested": 1},
    )
    assert response.status_code == 403
    emailed = client.post(f"/api/v1/demand-notices/{notice_id}/email", json={"company_id": "test-company", "recipient": "external@example.test"})
    assert emailed.status_code == 403


def test_notice_deposits_are_scoped_replay_safe_and_printable_and_quotes_are_editable(app, client, create_user, monkeypatch):
    create_user("commercial.full", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "commercial.full")
    product_id = _seed_product(app, price="10.000")
    notice_response = client.post("/api/v1/demand-notices", json={
        "company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567",
        "customer_name": "Deposit Buyer", "product_id": product_id, "quantity_requested": 2,
        "agreed_price": "10.000",
    })
    assert notice_response.status_code == 201, notice_response.get_json()
    notice = notice_response.get_json()["demand_notice"]
    notice_page = client.get("/demand-notices?store_id=test-store")
    assert notice_page.status_code == 200 and b"Record deposit" in notice_page.data and b"Edit" in notice_page.data
    payment = {"company_id": "test-company", "amount": "5.000", "method": "cash", "idempotency_key": "deposit-001"}
    first = client.post(f"/api/v1/demand-notices/{notice['id']}/payments", json=payment)
    assert first.status_code == 201, first.get_json()
    assert first.get_json()["demand_notice"]["amount_paid"] == "5.000"
    replay = client.post(f"/api/v1/demand-notices/{notice['id']}/payments", json=payment)
    assert replay.status_code == 200 and replay.get_json()["replayed"] is True
    conflicting = client.post(f"/api/v1/demand-notices/{notice['id']}/payments", json={**payment, "amount": "6.000"})
    assert conflicting.status_code == 409
    printed = client.get(f"/commercial/demand-notices/{notice['id']}/print?company_id=test-company")
    assert printed.status_code == 200 and b"5.000 OMR" in printed.data
    assert "إشعار طلب".encode() in printed.data
    assert "العميل".encode() in printed.data
    deliveries = []
    monkeypatch.setattr("retail_genie.commercial.routes.send_commercial_email", lambda **message: deliveries.append(message))
    notice_email = client.post(f"/api/v1/demand-notices/{notice['id']}/email", json={"company_id": "test-company", "recipient": "customer@example.test"})
    assert notice_email.status_code == 201, notice_email.get_json()
    assert deliveries[-1]["subject"] == f"Demand notice {notice['notice_number']}"
    assert "Deposit paid (OMR): 5.000" in deliveries[-1]["html_body"]
    invalid_email = client.post(f"/api/v1/demand-notices/{notice['id']}/email", json={"company_id": "test-company", "recipient": "bad\r\nBcc:other@example.test"})
    assert invalid_email.status_code == 400

    quote_response = client.post("/api/v1/quotations", json={
        "company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567",
        "customer_name": "Original Name", "lines": [{"product_id": product_id, "quantity": 1, "unit_price": "10.000"}],
    })
    assert quote_response.status_code == 201, quote_response.get_json()
    quotation = quote_response.get_json()["quotation"]
    updated = client.patch(f"/api/v1/quotations/{quotation['id']}", json={
        "company_id": "test-company", "customer_name": "Updated Name", "customer_email": "buyer@example.test", "notes": "Confirmed by customer",
        "lines": [{"product_id": product_id, "quantity": 2, "unit_price": "12.500"}],
    })
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()["quotation"]["customer_name"] == "Updated Name"
    assert updated.get_json()["quotation"]["total_amount"] == "25.000"
    assert updated.get_json()["quotation"]["lines"][0]["quantity"] == 2
    sent = client.post(f"/api/v1/quotations/{quotation['id']}/status", json={"company_id": "test-company", "status": "sent"})
    assert sent.status_code == 200
    forbidden_line_edit = client.patch(f"/api/v1/quotations/{quotation['id']}", json={"company_id": "test-company", "lines": [{"product_id": product_id, "quantity": 3, "unit_price": "12.500"}]})
    assert forbidden_line_edit.status_code == 409
    quote_print = client.get(f"/commercial/quotations/{quotation['id']}/print?company_id=test-company")
    assert quote_print.status_code == 200 and b"buyer@example.test" in quote_print.data and b"Email document" in quote_print.data
    assert "عرض سعر".encode() in quote_print.data
    assert "الإجمالي".encode() in quote_print.data
    quote_email = client.post(f"/api/v1/quotations/{quotation['id']}/email", json={"company_id": "test-company"})
    assert quote_email.status_code == 201, quote_email.get_json()
    assert quote_email.get_json()["recipient"] == "buyer@example.test"
    assert quotation["quotation_number"] in deliveries[-1]["subject"]
    def fail_email(**_message):
        raise CommercialEmailError("SMTP unavailable")
    monkeypatch.setattr("retail_genie.commercial.routes.send_commercial_email", fail_email)
    failed_email = client.post(f"/api/v1/quotations/{quotation['id']}/email", json={"company_id": "test-company"})
    assert failed_email.status_code == 503
    with app.app_context():
        assert AuditEvent.query.filter_by(action="commercial.demand_notice.emailed", entity_id=notice["id"]).count() == 1
        assert AuditEvent.query.filter_by(action="commercial.quotation.emailed", entity_id=quotation["id"]).count() == 1
        stored = db.session.get(DemandNotice, notice["id"])
        assert stored.amount_paid == 5
        assert len(stored.payments) == 1
        assert AuditEvent.query.filter_by(entity_id=notice["id"], action="commercial.demand_notice.deposit_received").count() == 1
        from retail_genie.sales.service import _expected_collections, company_today
        company = db.session.get(Company, "test-company")
        assert _expected_collections(company, "test-store", company_today(company))["cash"] == 5


def test_commercial_email_fails_closed_without_smtp_configuration(app):
    with app.app_context():
        app.config["SMTP_HOST"] = None
        app.config["SMTP_SENDER"] = None
        with pytest.raises(CommercialEmailError, match="not configured"):
            send_commercial_email(recipient="customer@example.test", subject="Test", html_body="<p>Test</p>")


def test_commercial_email_uses_tls_and_sends_html(app, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 15)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            pass

        def starttls(self, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ("mailer", "secret")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("retail_genie.commercial.emailing.smtplib.SMTP", FakeSMTP)
    with app.app_context():
        app.config.update(
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=587,
            SMTP_SENDER="retail@example.test",
            SMTP_USERNAME="mailer",
            SMTP_PASSWORD="secret",
            SMTP_USE_TLS=True,
            SMTP_USE_SSL=False,
        )
        send_commercial_email(recipient="buyer@example.test", subject="Quotation QT-1", html_body="<p>Quote</p>")
    assert len(sent) == 1
    assert sent[0]["To"] == "buyer@example.test"
    assert sent[0].get_body(preferencelist=("html",)).get_content().strip() == "<p>Quote</p>"


def test_demand_notice_partial_fulfillment_replays_and_caps_at_remaining_quantity(app, client, create_user):
    create_user("notice.partial", role="salesperson", permissions=SALES_PERMISSIONS)
    _sign_in(client, "notice.partial")
    product_id = _seed_product(app, price="2.000", quantity=8)
    created = client.post("/api/v1/demand-notices", json={
        "company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567",
        "product_id": product_id, "quantity_requested": 5, "agreed_price": "2.000",
    })
    assert created.status_code == 201, created.get_json()
    notice = created.get_json()["demand_notice"]
    deposit = client.post(f"/api/v1/demand-notices/{notice['id']}/payments", json={"company_id": "test-company", "amount": "4.000", "method": "cash", "idempotency_key": "partial-deposit"})
    assert deposit.status_code == 201, deposit.get_json()
    data = {"company_id": "test-company", "quantity": 2, "idempotency_key": "partial-1"}
    first = client.post(f"/api/v1/demand-notices/{notice['id']}/fulfill", json=data)
    assert first.status_code == 201, first.get_json()
    assert first.get_json()["order"]["items"][0]["quantity"] == 2
    assert first.get_json()["order"]["status"] == "closed"
    assert first.get_json()["order"]["paid_amount"] == "4.000"
    replay = client.post(f"/api/v1/demand-notices/{notice['id']}/fulfill", json=data)
    assert replay.status_code == 200 and replay.get_json()["replayed"] is True
    too_many = client.post(f"/api/v1/demand-notices/{notice['id']}/fulfill", json={**data, "quantity": 4, "idempotency_key": "partial-over"})
    assert too_many.status_code == 409
    final = client.post(f"/api/v1/demand-notices/{notice['id']}/fulfill", json={**data, "quantity": 3, "idempotency_key": "partial-2"})
    assert final.status_code == 201, final.get_json()
    with app.app_context():
        stored = db.session.get(DemandNotice, notice["id"])
        assert stored.quantity_fulfilled == 5
        assert stored.status == "converted"
        assert SalesOrder.query.filter_by(source_demand_notice_id=notice["id"]).count() == 2
        fulfillment_rows = DemandNoticeFulfillment.query.filter_by(notice_id=notice["id"]).order_by(DemandNoticeFulfillment.created_at.asc()).all()
        assert [row.quantity for row in fulfillment_rows] == [2, 3]
        assert fulfillment_rows[0].deposit_applied == 4
        from retail_genie.sales.service import _expected_collections, company_today
        company = db.session.get(Company, "test-company")
        assert _expected_collections(company, "test-store", company_today(company))["cash"] == 4
        assert InventoryBalance.query.filter_by(product_id=product_id, store_id="test-store").one().quantity_on_hand == 3
