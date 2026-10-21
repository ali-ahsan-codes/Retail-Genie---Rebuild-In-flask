from retail_genie.extensions import db
from retail_genie.models import AuditEvent, InventoryMovement, OrderPayment, SalesOrder, StoreCredit
from test_sales import SALES_PERMISSIONS, _create_api_order, _seed_product, _sign_in


def test_exchange_credit_settlement_and_surplus_credit_commit_with_events(app, client, create_user):
    replacement_product_id = _seed_product(app, name="Replacement", sku="REP-01", price="3.000", quantity=10)
    create_user("exchange.manager", role="manager", permissions=SALES_PERMISSIONS + ["inventory.add"])
    _sign_in(client, "exchange.manager")
    order = _create_api_order(client, quantity=2, price="5.000")
    paid = client.post(f"/api/v1/orders/{order['id']}/payments", json={"store_id": "test-store", "method": "cash", "amount": "10.000", "idempotency_key": "exchange-source-payment"})
    assert paid.status_code == 200
    response = client.post(f"/api/v1/orders/{order['id']}/returns", json={
        "store_id": "test-store",
        "items": [{"line_id": order["items"][0]["id"], "quantity": 1}],
        "reason": "Exchange one item",
        "refund_method": "other",
        "kind": "exchange",
        "exchange_items": [{"product_id": replacement_product_id, "quantity": 1}],
        "idempotency_key": "exchange-return-1",
    })
    assert response.status_code == 201, response.get_json()
    result = response.get_json()
    assert result["return_transaction"]["refund_amount"] == "5.000"
    with app.app_context():
        exchange = SalesOrder.query.filter(SalesOrder.id != order["id"]).one()
        assert exchange.status == "closed"
        assert str(exchange.total_amount) == "3.000"
        assert OrderPayment.query.filter_by(order_id=exchange.id).one().amount == 3
        credit = StoreCredit.query.filter_by(source_return_id=result["return_transaction"]["id"]).one()
        assert credit.amount == 2
        assert credit.remaining_amount == 2
        assert InventoryMovement.query.filter_by(product_id=replacement_product_id, movement_type="sale").count() == 1
        assert InventoryMovement.query.filter_by(movement_type="return").count() == 1
        assert AuditEvent.query.filter_by(action="order.exchange_created").count() == 1
    replay = client.post(f"/api/v1/orders/{order['id']}/returns", json={
        "store_id": "test-store",
        "items": [{"line_id": order["items"][0]["id"], "quantity": 1}],
        "reason": "Exchange one item",
        "refund_method": "other",
        "kind": "exchange",
        "exchange_items": [{"product_id": replacement_product_id, "quantity": 1}],
        "idempotency_key": "exchange-return-1",
    })
    assert replay.status_code == 200, replay.get_json()
    assert replay.get_json()["replayed"] is True
