from io import BytesIO

from retail_genie.extensions import db
from retail_genie.models import AuditEvent, CatalogProduct, Company, InventoryBalance, InventoryMovement, PurchaseOrder, RealtimeEvent


def test_purchase_order_partial_receiving_posts_inventory_and_audit_atomically(app, client, create_user, tmp_path):
    app.config["UPLOADS_DIR"] = str(tmp_path / "private-uploads")
    create_user("scm.manager", role="manager", permissions=["manage_suppliers", "create_pos", "approve_pos", "receive_stock", "manage_logistics", "inventory.add", "inventory.view", "product_catalog.view"])
    client.post("/login", data={"username": "scm.manager", "password": "A-long-test-password-4!"})
    assert client.get("/scm").status_code == 200
    assert client.get("/scm/suppliers").status_code == 200
    assert client.get("/scm/purchase-orders").status_code == 200
    with app.app_context():
        company = db.session.get(Company, "test-company")
        product = CatalogProduct(tenant_container_id=company.tenant_container_id, company_id=company.id, name="Parts", sku="PART-1", price="4.000", is_active=True)
        db.session.add(product)
        db.session.commit()
        product_id = product.id
    supplier_response = client.post("/api/v1/suppliers", json={"name": "North Supply", "phone": "+968 9000 0000"})
    assert supplier_response.status_code == 201, supplier_response.get_json()
    supplier_id = supplier_response.get_json()["supplier"]["id"]
    supplier_attachment = client.post(f"/api/v1/suppliers/{supplier_id}/attachments", data={"company_id":"test-company","file":(BytesIO(b"supplier terms"),"terms.txt"),"notes":"Annual terms"}, content_type="multipart/form-data")
    assert supplier_attachment.status_code == 201, supplier_attachment.get_json()
    supplier_attachment_id = supplier_attachment.get_json()["attachment"]["id"]
    supplier_page = client.get(f"/scm/suppliers/{supplier_id}")
    assert supplier_page.status_code == 200 and b"Annual terms" in supplier_page.data
    supplier_download = client.get(f"/api/v1/suppliers/{supplier_id}/attachments/{supplier_attachment_id}?company_id=test-company")
    assert supplier_download.status_code == 200 and supplier_download.data == b"supplier terms"
    po_response = client.post("/api/v1/purchase-orders", json={"supplier_id": supplier_id, "items": [{"product_id": product_id, "quantity": 5, "unit_price": "3.500"}]})
    assert po_response.status_code == 201, po_response.get_json()
    po = po_response.get_json()["purchase_order"]
    po_page = client.get(f"/scm/purchase-orders/{po['id']}")
    assert po_page.status_code == 200 and b"Edit draft purchase order" in po_page.data
    edited = client.patch(f"/api/v1/purchase-orders/{po['id']}", json={"expected_delivery": "2026-11-15", "transportation_details": "Truck 4"})
    assert edited.status_code == 200, edited.get_json()
    po = edited.get_json()["purchase_order"]
    upload = client.post(f"/api/v1/purchase-orders/{po['id']}/attachments", data={"file": (BytesIO(b"private invoice"), "invoice.txt"), "attachment_type": "invoice", "notes": "Supplier invoice"}, content_type="multipart/form-data")
    assert upload.status_code == 201, upload.get_json()
    attachment_id = upload.get_json()["attachment"]["id"]
    po_page = client.get(f"/scm/purchase-orders/{po['id']}")
    assert b"invoice.txt" in po_page.data
    downloaded = client.get(f"/api/v1/purchase-orders/{po['id']}/attachments/{attachment_id}")
    assert downloaded.status_code == 200 and downloaded.data == b"private invoice"
    logistics = client.patch(f"/api/v1/purchase-orders/{po['id']}/logistics", json={"logistics_status": "in_transit", "transportation_details": "Truck 7"})
    assert logistics.status_code == 200, logistics.get_json()
    assert logistics.get_json()["purchase_order"]["logistics_status"] == "in_transit"
    confirmed = client.post(f"/api/v1/purchase-orders/{po['id']}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.get_json()
    item = po["items"][0]
    received = client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"receipts": [{"item_id": item["id"], "quantity": 2, "store_id": "test-store"}]})
    assert received.status_code == 200, received.get_json()
    assert received.get_json()["purchase_order"]["status"] == "partially_received"
    with app.app_context():
        balance = InventoryBalance.query.filter_by(product_id=product_id, store_id="test-store").one()
        assert balance.quantity_on_hand == 2
        assert InventoryMovement.query.filter_by(product_id=product_id, movement_type="receive").one().quantity_delta == 2
        assert AuditEvent.query.filter_by(action="scm.purchase_order.received").count() == 1
        assert RealtimeEvent.query.filter_by(event_type="inventory.updated").count() == 1
        receiving_event = RealtimeEvent.query.filter_by(event_type="scm.purchase_order.received").one()
        assert receiving_event.domain == "inventory"
        assert receiving_event.store_id == "test-store"
        assert receiving_event.payload["quantity_received"] == 2
        saved = db.session.get(PurchaseOrder, po["id"])
        assert saved.status == "partially_received"
