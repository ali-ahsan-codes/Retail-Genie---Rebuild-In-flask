from retail_genie.extensions import db
from retail_genie.models import AuditEvent, CatalogProduct, Company, InventoryBalance, InventoryMovement, StockAuditItem


def test_stock_audit_posts_variance_only_when_completed(app, client, create_user):
    auditor_id = create_user("audit.manager", role="manager", permissions=["manage_audits", "conduct_audits", "inventory.view", "inventory.add", "inventory.edit", "product_catalog.view"])
    with app.app_context():
        company = db.session.get(Company, "test-company")
        product = CatalogProduct(tenant_container_id=company.tenant_container_id, company_id=company.id, name="Audit item", sku="AUD-1", price="1.000", is_active=True)
        db.session.add(product)
        db.session.flush()
        db.session.add(InventoryBalance(tenant_container_id=company.tenant_container_id, company_id=company.id, store_id="test-store", product_owner_company_id=company.id, product_id=product.id, quantity_on_hand=5))
        db.session.add(InventoryMovement(tenant_container_id=company.tenant_container_id, company_id=company.id, store_id="test-store", product_owner_company_id=company.id, product_id=product.id, movement_type="opening", quantity_delta=5, reason="Opening count"))
        db.session.commit()
        product_id = product.id
    client.post("/login", data={"username": "audit.manager", "password": "A-long-test-password-4!"})
    assert client.get("/audits").status_code == 200
    assert client.get("/audits/create").status_code == 200
    created = client.post("/api/v1/audits", json={"store_id": "test-store", "title": "Monthly count", "product_ids": [product_id], "auditor_id": auditor_id})
    assert created.status_code == 201, created.get_json()
    audit_id = created.get_json()["audit"]["id"]
    assert client.get(f"/audits/{audit_id}").status_code == 200
    assert client.get(f"/audits/{audit_id}/report").status_code == 200
    started = client.post(f"/api/v1/audits/{audit_id}/start", json={"auditor_id": auditor_id})
    assert started.status_code == 200
    with app.app_context():
        item = StockAuditItem.query.filter_by(audit_id=audit_id).one()
        item_id = item.id
        assert item.current_stock == 5
    count = client.post(f"/api/v1/audits/{audit_id}/items/{item_id}/counts", json={"count": 4, "notes": "One missing"})
    assert count.status_code == 201, count.get_json()
    with app.app_context():
        assert InventoryBalance.query.filter_by(product_id=product_id).one().quantity_on_hand == 5
    completed = client.post(f"/api/v1/audits/{audit_id}/complete", json={})
    assert completed.status_code == 200, completed.get_json()
    with app.app_context():
        assert InventoryBalance.query.filter_by(product_id=product_id).one().quantity_on_hand == 4
        assert InventoryMovement.query.filter_by(product_id=product_id, movement_type="adjustment").one().quantity_delta == -1
        assert AuditEvent.query.filter_by(action="audit.stock.completed").count() == 1
