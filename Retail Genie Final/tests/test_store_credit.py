from retail_genie.extensions import db
from retail_genie.models import CatalogProduct, Company, InventoryBalance, OrderPayment, SalesOrder, Store, StoreCredit, StoreCreditRedemption
from test_sales import SALES_PERMISSIONS, _create_api_order, _seed_product, _sign_in


def test_store_credit_issued_from_return_can_be_applied_once_to_matching_customer_bill(app, client, create_user):
    _seed_product(app, quantity=100)
    create_user("credit.manager", role="manager", permissions=SALES_PERMISSIONS + ["inventory.add"])
    _sign_in(client, "credit.manager")
    source_order = _create_api_order(client, quantity=2, price="5.000")
    payment = client.post(f"/api/v1/orders/{source_order['id']}/payments", json={"store_id": "test-store", "method": "cash", "amount": "10.000", "idempotency_key": "source-payment"})
    assert payment.status_code == 200
    returned = client.post(f"/api/v1/orders/{source_order['id']}/returns", json={
        "store_id": "test-store",
        "items": [{"line_id": source_order["items"][0]["id"], "quantity": 1}],
        "reason": "Customer chose credit",
        "refund_method": "other",
        "kind": "store_credit",
        "idempotency_key": "credit-return-1",
    })
    assert returned.status_code == 201, returned.get_json()
    issued = returned.get_json()["store_credit"]
    assert issued["amount"] == "5.000"
    second_order = _create_api_order(client, quantity=2, price="5.000")
    credits = client.get("/api/v1/store-credits?phone=91234567")
    assert credits.status_code == 200
    assert len(credits.get_json()["credits"]) == 1
    payload = {"store_id": "test-store", "customer_phone": "+968 9123 4567", "amount": "5.000", "idempotency_key": "redeem-credit-1"}
    redeemed = client.post(f"/api/v1/orders/{second_order['id']}/store-credits/{issued['id']}/redeem", json=payload)
    assert redeemed.status_code == 201, redeemed.get_json()
    assert redeemed.get_json()["order"]["status"] == "open"
    assert redeemed.get_json()["order"]["paid_amount"] == "5.000"
    replay = client.post(f"/api/v1/orders/{second_order['id']}/store-credits/{issued['id']}/redeem", json=payload)
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    wrong_phone = client.post(f"/api/v1/orders/{second_order['id']}/store-credits/{issued['id']}/redeem", json={**payload, "customer_phone": "99999999", "idempotency_key": "wrong-phone"})
    assert wrong_phone.status_code == 403
    with app.app_context():
        credit = db.session.get(StoreCredit, issued["id"])
        assert str(credit.remaining_amount) == "0.000" or float(credit.remaining_amount) == 0
        assert StoreCreditRedemption.query.count() == 1
        assert OrderPayment.query.filter_by(order_id=second_order["id"], method="other").count() == 1
