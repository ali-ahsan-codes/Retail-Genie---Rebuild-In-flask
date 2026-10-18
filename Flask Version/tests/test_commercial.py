from retail_genie.extensions import db
from retail_genie.models import (
    AuditEvent,
    CatalogProduct,
    Company,
    DemandNotice,
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


def test_sales_view_only_cannot_create_commercial_documents(client, create_user):
    create_user("commercial.readonly", role="salesperson", permissions=["sales.view"])
    _sign_in(client, "commercial.readonly")
    response = client.post(
        "/api/v1/demand-notices",
        json={"company_id": "test-company", "store_id": "test-store", "customer_phone": "91234567", "product_name": "No permission", "quantity_requested": 1},
    )
    assert response.status_code == 403
