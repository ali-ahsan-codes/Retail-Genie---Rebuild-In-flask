from retail_genie.extensions import db
from retail_genie.models import AuditEvent, CatalogProduct, Company, InventoryBalance, InventoryMovement, Store, SalesOrder, OrderPayment


def _product(app, quantity=5):
    with app.app_context():
        company = db.session.get(Company, "test-company")
        store = db.session.get(Store, "test-store")
        product = CatalogProduct(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            name="Express tea",
            sku="TEA-01",
            barcode="12345678",
            price="2.500",
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(InventoryBalance(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            store_id=store.id,
            product_owner_company_id=company.id,
            product_id=product.id,
            quantity_on_hand=quantity,
        ))
        db.session.commit()
        return product.id


def test_express_checkout_is_atomic_idempotent_and_uses_catalog_price(app, client, create_user):
    product_id = _product(app)
    create_user("express.operator", role="express", permissions=["express_checkout", "sales.add", "product_catalog.view", "inventory.view"])
    assert client.post("/login", data={"username": "express.operator", "password": "A-long-test-password-4!"}).status_code == 302
    page = client.get("/express")
    assert page.status_code == 200
    assert b"js/express-checkout.js" in page.data
    assert b"Print invoice" in page.data
    assert "طباعة الفاتورة".encode() in page.data
    script = client.get("/static/js/express-checkout.js")
    assert script.status_code == 200 and b"money(data.order.total_amount).toFixed(3)" in script.data
    assert b"scanExact: true" in script.data
    products = client.get("/api/v1/express/products?store_id=test-store&q=TEA")
    assert products.status_code == 200 and len(products.get_json()["products"]) == 1
    payload = {
        "store_id": "test-store",
        "customer_phone": "+968 9123 4567",
        "items": [{"sku": "TEA-01", "quantity": 2}],
        "payments": [{"method": "cash", "amount": "5.000"}],
        "idempotency_key": "express-unique-1",
    }
    response = client.post("/api/v1/express/checkout", json=payload)
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["order"]["status"] == "closed"
    assert body["order"]["total_amount"] == "5.000"
    assert body["order"]["invoice_number"]
    replay = client.post("/api/v1/express/checkout", json=payload)
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    changed = client.post("/api/v1/express/checkout", json={**payload, "payments": [{"method": "cash", "amount": "4.000"}]})
    assert changed.status_code == 409
    assert changed.get_json()["error"] == "idempotency_conflict"
    with app.app_context():
        assert SalesOrder.query.count() == 1
        assert OrderPayment.query.count() == 1
        assert InventoryMovement.query.filter_by(movement_type="sale").count() == 1
        assert AuditEvent.query.filter_by(action="order.express_checkout_completed").count() == 1
        balance = InventoryBalance.query.filter_by(product_id=product_id).one()
        assert balance.quantity_on_hand == 3


def test_express_checkout_failure_rolls_back_order_stock_payment_and_event(app, client, create_user):
    product_id = _product(app, quantity=1)
    create_user("express.rollback", role="express", permissions=["express_checkout", "sales.add", "product_catalog.view", "inventory.view"])
    client.post("/login", data={"username": "express.rollback", "password": "A-long-test-password-4!"})
    response = client.post("/api/v1/express/checkout", json={
        "store_id": "test-store",
        "customer_phone": "91234567",
        "items": [{"sku": "TEA-01", "quantity": 2}],
        "payments": [{"method": "cash", "amount": "5.000"}],
        "idempotency_key": "express-stock-failure",
    })
    assert response.status_code == 409
    with app.app_context():
        assert SalesOrder.query.count() == 0
        assert OrderPayment.query.count() == 0
        assert InventoryMovement.query.filter_by(movement_type="sale").count() == 0
        balance = InventoryBalance.query.filter_by(product_id=product_id).one()
        assert balance.quantity_on_hand == 1
