from retail_genie.extensions import db
from retail_genie.models import Company, TaxSetting
from test_sales import SALES_PERMISSIONS, _seed_product, _sign_in


def test_refund_allocates_saved_discount_and_tax_across_partial_returns(app, client, create_user):
    product_id = _seed_product(app, quantity=10)
    with app.app_context():
        company = db.session.get(Company, "test-company")
        db.session.add(TaxSetting(tenant_container_id=company.tenant_container_id, company_id=company.id, name="VAT", rate="5.00000000", is_enabled=True))
        db.session.commit()
    create_user("refund.manager", role="manager", permissions=SALES_PERMISSIONS + ["inventory.add", "manage_returns"])
    _sign_in(client, "refund.manager")
    response = client.post("/api/v1/orders", json={
        "store_id": "test-store", "customer_phone": "+968 9123 4567", "customer_name": "Sam Customer",
        "discount_percentage": "10", "items": [{"product_id": product_id, "quantity": 2}],
    })
    assert response.status_code == 201, response.get_json()
    order = response.get_json()["order"]
    assert order["subtotal_amount"] == "10.000"
    assert order["total_amount"] == "9.450"
    paid = client.post(f"/api/v1/orders/{order['id']}/payments", json={"store_id": "test-store", "method": "cash", "amount": "9.450", "idempotency_key": "refund-tax-payment"})
    assert paid.status_code == 200
    return_payload = {
        "store_id": "test-store", "items": [{"line_id": order["items"][0]["id"], "quantity": 1}],
        "reason": "Partial taxed item return", "refund_method": "cash", "idempotency_key": "tax-return-1",
    }
    first = client.post(f"/api/v1/orders/{order['id']}/returns", json=return_payload)
    assert first.status_code == 201, first.get_json()
    assert first.get_json()["return_transaction"]["refund_amount"] == "4.725"
    second = client.post(f"/api/v1/orders/{order['id']}/returns", json={**return_payload, "idempotency_key": "tax-return-2"})
    assert second.status_code == 201, second.get_json()
    assert second.get_json()["return_transaction"]["refund_amount"] == "4.725"
