from test_sales import SALES_PERMISSIONS, _create_api_order, _sign_in


def test_sales_and_activity_reports_are_scoped_and_exportable(client, create_user):
    create_user("report.manager", role="manager", permissions=SALES_PERMISSIONS)
    create_user("report.viewer", role="manager", permissions=["reports.view", "audit.view", "view_reports", "view_salesperson_reports"])
    _sign_in(client, "report.manager")
    order = _create_api_order(client, quantity=1, price="5.000")
    paid = client.post(f"/api/v1/orders/{order['id']}/payments", json={"store_id": "test-store", "method": "cash", "amount": "5.000", "idempotency_key": "report-payment"})
    assert paid.status_code == 200
    notice = client.post("/api/v1/demand-notices", json={"company_id":"test-company","store_id":"test-store","customer_phone":"91234567","product_name":"Report deposit","quantity_requested":1,"agreed_price":"2.000"})
    assert notice.status_code == 201
    notice_id = notice.get_json()["demand_notice"]["id"]
    deposit = client.post(f"/api/v1/demand-notices/{notice_id}/payments", json={"company_id":"test-company","amount":"1.000","method":"bank","idempotency_key":"report-deposit"})
    assert deposit.status_code == 201
    client.post("/logout")
    _sign_in(client, "report.viewer")
    report = client.get("/api/v1/reports/sales?store_id=test-store")
    assert report.status_code == 200, report.get_json()
    assert report.get_json()["totals"]["order_count"] == 1
    assert report.get_json()["totals"]["paid_omr"] == "5.000"
    assert report.get_json()["totals"]["commercial_deposits_omr"] == "1.000"
    assert report.get_json()["deposits"][0]["notice_number"] == "DN-000001"
    page = client.get("/admin/salesperson-reports?store_id=test-store")
    assert page.status_code == 200 and b"Demand-notice deposits" in page.data
    csv = client.get("/api/v1/reports/sales.csv?store_id=test-store")
    assert csv.status_code == 200
    assert b"order_number" in csv.data and b"invoice_number" in csv.data
    assert b"commercial_deposit" in csv.data and b"DN-000001" in csv.data
    activity = client.get("/api/v1/reports/activity?store_id=test-store")
    assert activity.status_code == 200
    assert any(event["action"] == "order.payment_received" for event in activity.get_json()["events"])
    assert client.get("/api/v1/reports/sales?store_id=unknown").status_code == 403
