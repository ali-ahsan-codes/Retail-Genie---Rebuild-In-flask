from test_sales import SALES_PERMISSIONS, _create_api_order, _sign_in


def test_lcd_display_is_store_scoped_role_restricted_and_minimizes_customer_data(client, create_user):
    create_user("display.cashier", role="manager", permissions=SALES_PERMISSIONS)
    create_user("display.screen", role="display", permissions=[])
    create_user("display.unprivileged", role="cashier", permissions=["use_sales_pos"])
    _sign_in(client, "display.cashier")
    order = _create_api_order(client, quantity=1, price="3.000")
    client.post("/logout")
    _sign_in(client, "display.screen")
    page = client.get("/lcd-display?store_id=test-store")
    assert page.status_code == 200
    assert b"order.customer_phone" not in page.data
    response = client.get("/api/v1/display/orders?store_id=test-store")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["orders"]
    assert len(payload) == 1 and payload[0]["id"] == order["id"]
    assert "customer_phone" not in payload[0] and "payments" not in payload[0]
    assert client.get("/api/v1/display/orders?store_id=unassigned").status_code == 403
    client.post("/logout")
    _sign_in(client, "display.unprivileged")
    assert client.get("/lcd-display?store_id=test-store").status_code == 403
