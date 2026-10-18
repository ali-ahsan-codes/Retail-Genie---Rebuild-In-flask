from datetime import date

import pytest

from retail_genie.extensions import db
from retail_genie.models import (
    AuditEvent,
    BillingSeries,
    CatalogProduct,
    Company,
    ContainerMembership,
    DailyCashup,
    InventoryBalance,
    InventoryMovement,
    OrderNumberSeries,
    OrderPayment,
    OrderRemovalRequest,
    OrderReturn,
    OrderReturnLine,
    RealtimeEvent,
    SalesOrder,
    SalesOrderLine,
    Store,
    TenantContainer,
    User,
    UserStoreAssignment,
)
from retail_genie.sales.service import company_today, create_order
from retail_genie.tenancy.service import seed_tenant_data_policies


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


def _seed_product(application, *, company_id="test-company", store_id="test-store", name="Coffee", sku="COF-01", price="5.000", quantity=100):
    with application.app_context():
        company = db.session.get(Company, company_id)
        store = db.session.get(Store, store_id)
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
                company_id=store.company_id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=quantity,
            )
        )
        db.session.commit()
        return product.id


def _sign_in(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _create_payload(store_id="test-store", phone="+968 9123 4567", quantity=2, price="5.000"):
    return {
        "store_id": store_id,
        "customer_phone": phone,
        "customer_name": "Sam Customer",
        "items": [{"name": "Coffee", "sku": "COF-01", "quantity": quantity, "unit_price": price}],
    }


def _create_api_order(client, **kwargs):
    payload = _create_payload(**kwargs)
    source_item = payload["items"][0]
    product_id = _seed_product(
        client.application,
        store_id=payload["store_id"],
        name=source_item["name"],
        sku=source_item["sku"],
        price=source_item["unit_price"],
    )
    payload["items"] = [{"product_id": product_id, "quantity": source_item["quantity"]}]
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["order"]


def test_company_scoped_phone_lookup_and_super_admin_controlled_cross_store_access(app, client, create_user):
    create_user("sales.one", role="cashier", permissions=SALES_PERMISSIONS)
    branch_staff_id = create_user("sales.branch", role="cashier", permissions=["use_sales_pos", "open_bills.view"])
    _sign_in(client, "sales.one")
    order = _create_api_order(client, quantity=1, price="8.000")

    with app.app_context():
        second_store = Store(id="test-store-two", tenant_container_id="test-container", company_id="test-company", code="BR2", name="Second Branch")
        foreign_container = TenantContainer(id="other-container", name="Other Tenant", slug="other-tenant")
        db.session.add_all([second_store, foreign_container])
        db.session.flush()
        seed_tenant_data_policies(foreign_container.id)
        foreign_company = Company(
            id="other-company",
            tenant_container_id=foreign_container.id,
            name="Other Company",
            slug="other-company",
        )
        db.session.add(foreign_company)
        db.session.flush()
        db.session.add(
            OrderNumberSeries(
                tenant_container_id=foreign_container.id,
                company_id=foreign_company.id,
                prefix="ORD-",
                next_number=1,
            )
        )
        foreign_store = Store(id="other-store", tenant_container_id=foreign_container.id, company_id=foreign_company.id, code="OTH", name="Other Shop")
        foreign_user = User(company_id=foreign_company.id, username="other.cashier", role="cashier", permissions=SALES_PERMISSIONS)
        foreign_user.set_password("A-long-test-password-4!")
        db.session.add_all([foreign_store, foreign_user])
        db.session.flush()
        foreign_product = CatalogProduct(
            tenant_container_id=foreign_container.id,
            company_id=foreign_company.id,
            name="Foreign item",
            price="2.000",
            is_active=True,
        )
        db.session.add(foreign_product)
        db.session.flush()
        db.session.add(
            InventoryBalance(
                tenant_container_id=foreign_container.id,
                company_id=foreign_company.id,
                store_id=foreign_store.id,
                product_owner_company_id=foreign_company.id,
                product_id=foreign_product.id,
                quantity_on_hand=5,
            )
        )
        db.session.add(
            ContainerMembership(
                tenant_container_id=foreign_container.id,
                user_id=foreign_user.id,
                company_id=foreign_company.id,
                role="cashier",
                permissions=SALES_PERMISSIONS,
                is_default=True,
                is_active=True,
            )
        )
        db.session.add_all(
            [
                UserStoreAssignment(tenant_container_id=foreign_container.id, company_id=foreign_company.id, user_id=foreign_user.id, store_id=foreign_store.id),
                UserStoreAssignment(tenant_container_id="test-container", company_id="test-company", user_id=branch_staff_id, store_id=second_store.id),
            ]
        )
        db.session.commit()
        foreign_user_id = foreign_user.id
        foreign_product_id = foreign_product.id
        second_store_id = second_store.id

        actor = db.session.get(User, foreign_user_id)
        foreign_order = create_order(
            actor,
            store_id="other-store",
            customer_phone="+968 9123 4567",
            customer_name="Other Tenant",
            items=[{"product_id": foreign_product_id, "quantity": 1}],
        )
        foreign_order_id = foreign_order.id

    found = client.get("/api/v1/orders/open", query_string={"store_id": "test-store", "phone": "96891234567"})
    assert found.status_code == 200
    assert [row["id"] for row in found.get_json()["orders"]] == [order["id"]]
    cross_tenant = client.get(
        "/api/v1/orders/open",
        query_string={"store_id": "test-store", "phone": "96891234567", "company_id": "other-company"},
    )
    assert cross_tenant.status_code == 404
    foreign_store_lookup = client.get(
        "/api/v1/orders/open",
        query_string={"store_id": "other-store", "phone": "96891234567"},
    )
    assert foreign_store_lookup.status_code == 404
    foreign_detail = client.get(f"/api/v1/orders/{foreign_order_id}", query_string={"store_id": "test-store"})
    assert foreign_detail.status_code == 404
    foreign_payment = client.post(
        f"/api/v1/orders/{foreign_order_id}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "1.000", "idempotency_key": "foreign-test"},
    )
    assert foreign_payment.status_code == 404

    branch_client = app.test_client()
    _sign_in(branch_client, "sales.branch")
    blocked = branch_client.get(
        "/api/v1/orders/open",
        query_string={"store_id": second_store_id, "phone": "96891234567"},
    )
    assert blocked.status_code == 200
    assert blocked.get_json()["orders"] == []
    with app.app_context():
        assignment = UserStoreAssignment.query.filter_by(user_id=branch_staff_id, store_id=second_store_id).one()
        assignment.can_view_shared_bills = True
        db.session.commit()
    granted = branch_client.get(
        "/api/v1/orders/open",
        query_string={"store_id": second_store_id, "phone": "96891234567"},
    )
    assert granted.status_code == 200
    assert [row["id"] for row in granted.get_json()["orders"]] == [order["id"]]
    with app.app_context():
        assert SalesOrder.query.filter_by(id=foreign_order_id).count() == 1


def test_partial_payments_keep_bill_open_and_mixed_tender_invoice_is_issued_on_full_settlement(app, client, create_user):
    seller_id = create_user("seller", role="cashier", permissions=SALES_PERMISSIONS)
    with app.app_context():
        company = db.session.get(Company, "test-company")
        company.mixed_tender_category = "bank_transfer"
        db.session.commit()
    _sign_in(client, "seller")
    order = _create_api_order(client, quantity=2, price="5.000")
    assert order["order_number"] == "ORD-000001"
    assert order["invoice_number"] is None
    with app.app_context():
        assert OrderNumberSeries.query.filter_by(company_id="test-company").one().next_number == 2

    partial = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "2.000", "idempotency_key": "cash-part-1"},
    )
    assert partial.status_code == 200, partial.get_json()
    assert partial.get_json()["order"]["status"] == "open"
    assert partial.get_json()["order"]["invoice_number"] is None
    assert partial.get_json()["order"]["balance"] == "8.000"

    lookup = client.get(
        "/api/v1/orders/open",
        query_string={"store_id": "test-store", "phone": "91234567"},
    )
    assert lookup.status_code == 200
    assert len(lookup.get_json()["orders"]) == 1

    final_payload = {"store_id": "test-store", "method": "bank", "amount": "8.000", "idempotency_key": "final-payment"}
    final = client.post(f"/api/v1/orders/{order['id']}/payments", json=final_payload)
    assert final.status_code == 200, final.get_json()
    final_order = final.get_json()["order"]
    assert final_order["status"] == "closed"
    assert final_order["invoice_category"] == "bank_transfer"
    assert final_order["invoice_number"] == "BT-000001"
    replay = client.post(f"/api/v1/orders/{order['id']}/payments", json=final_payload)
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["order"]["invoice_number"] == "BT-000001"
    assert client.get("/api/v1/orders/open", query_string={"store_id": "test-store", "phone": "91234567"}).get_json()["orders"] == []

    with app.app_context():
        assert OrderPayment.query.filter_by(order_id=order["id"]).count() == 2
        assert BillingSeries.query.filter_by(company_id="test-company", category="bank_transfer").one().next_number == 2
        assert SalesOrder.query.filter_by(id=order["id"]).one().updated_by_id == seller_id


def test_settled_order_returns_refund_once_restore_stock_and_reduce_cashup_collections(app, client, create_user):
    create_user("return.manager", role="manager", permissions=SALES_PERMISSIONS + ["inventory.add"])
    _sign_in(client, "return.manager")
    order = _create_api_order(client, quantity=2, price="5.000")
    line_id = order["items"][0]["id"]
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "10.000", "idempotency_key": "return-sale-payment"},
    )
    assert paid.status_code == 200
    payload = {
        "store_id": "test-store",
        "items": [{"line_id": line_id, "quantity": 1}],
        "reason": "Customer returned one item",
        "refund_method": "bank",
        "transaction_reference": "BANK-REF-22",
        "idempotency_key": "return-once-1",
    }
    returned = client.post(f"/api/v1/orders/{order['id']}/returns", json=payload)
    assert returned.status_code == 201, returned.get_json()
    assert returned.get_json()["return_transaction"]["refund_amount"] == "5.000"
    assert returned.get_json()["order"]["items"][0]["returned_quantity"] == 1
    assert returned.get_json()["order"]["items"][0]["returnable_quantity"] == 1

    replay = client.post(f"/api/v1/orders/{order['id']}/returns", json=payload)
    assert replay.status_code == 200, replay.get_json()
    assert replay.get_json()["replayed"] is True
    changed_replay = client.post(
        f"/api/v1/orders/{order['id']}/returns",
        json={**payload, "reason": "Different use of same key"},
    )
    assert changed_replay.status_code == 409
    assert changed_replay.get_json()["error"] == "idempotency_conflict"

    overreturn = client.post(
        f"/api/v1/orders/{order['id']}/returns",
        json={**payload, "items": [{"line_id": line_id, "quantity": 2}], "idempotency_key": "return-too-many"},
    )
    assert overreturn.status_code == 409
    assert overreturn.get_json()["error"] == "return_quantity_exceeded"

    second_return = client.post(
        f"/api/v1/orders/{order['id']}/returns",
        json={**payload, "refund_method": "cash", "transaction_reference": None, "idempotency_key": "return-once-2"},
    )
    assert second_return.status_code == 201, second_return.get_json()
    assert second_return.get_json()["order"]["items"][0]["returnable_quantity"] == 0

    return_page = client.get(f"/returns?store_id=test-store&q={order['order_number']}")
    assert return_page.status_code == 200
    assert b"No additional quantities are returnable on this bill" in return_page.data
    with app.app_context():
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=order["items"][0]["product_id"]).one()
        assert balance.quantity_on_hand == 100
        assert OrderReturn.query.filter_by(order_id=order["id"]).count() == 2
        assert OrderReturnLine.query.count() == 2
        assert InventoryMovement.query.filter_by(movement_type="return").count() == 2
        assert AuditEvent.query.filter_by(action="sales.return_refunded").count() == 2
        today = company_today(db.session.get(Company, "test-company")).isoformat()

    cashup = client.post(
        "/api/v1/cashups",
        json={
            "store_id": "test-store",
            "business_date": today,
            "counted": {"cash": "5.000", "bank": "0", "bank_transfer": "0", "other": "0"},
        },
    )
    assert cashup.status_code == 201, cashup.get_json()
    assert cashup.get_json()["cashup"]["expected"]["cash"] == "5.000"
    assert cashup.get_json()["cashup"]["expected"]["bank"] == "-5.000"


def test_returns_are_manager_only_and_inventory_permission_failure_rolls_back(app, client, create_user):
    create_user("manager.no.return.stock", role="manager", permissions=SALES_PERMISSIONS)
    _sign_in(client, "manager.no.return.stock")
    order = _create_api_order(client, quantity=1, price="5.000")
    line_id = order["items"][0]["id"]
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "5.000", "idempotency_key": "no-stock-return-pay"},
    )
    assert paid.status_code == 200
    denied = client.post(
        f"/api/v1/orders/{order['id']}/returns",
        json={
            "store_id": "test-store",
            "items": [{"line_id": line_id, "quantity": 1}],
            "reason": "No stock grant",
            "refund_method": "cash",
            "idempotency_key": "no-stock-return-refund",
        },
    )
    assert denied.status_code == 403
    with app.app_context():
        assert OrderReturn.query.count() == 0
        balance = InventoryBalance.query.filter_by(product_id=order["items"][0]["product_id"], store_id="test-store").one()
        assert balance.quantity_on_hand == 99
        assert InventoryMovement.query.filter_by(movement_type="return").count() == 0

    create_user("cashier.no.refund", role="cashier", permissions=SALES_PERMISSIONS + ["inventory.add"])
    cashier_client = app.test_client()
    _sign_in(cashier_client, "cashier.no.refund")
    forbidden = cashier_client.post(
        f"/api/v1/orders/{order['id']}/returns",
        json={
            "store_id": "test-store",
            "items": [{"line_id": line_id, "quantity": 1}],
            "reason": "Cashier cannot refund directly",
            "refund_method": "cash",
            "idempotency_key": "cashier-return-forbidden",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == "return_forbidden"


@pytest.mark.parametrize(
    ("method", "category", "prefix"),
    [("cash", "cash", "CASH-"), ("bank", "bank", "BANK-"), ("bank_transfer", "bank_transfer", "BT-"), ("other", "other", "OTH-")],
)
def test_single_tender_uses_its_own_invoice_series(client, create_user, method, category, prefix):
    create_user(f"seller.{method}", role="cashier", permissions=SALES_PERMISSIONS)
    _sign_in(client, f"seller.{method}")
    order = _create_api_order(client, quantity=1, price="1.000", phone=f"+968 9{len(method):03d} 4567")
    response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": method, "amount": "1.000", "idempotency_key": f"single-{method}"},
    )
    assert response.status_code == 200, response.get_json()
    invoice = response.get_json()["order"]
    assert invoice["invoice_category"] == category
    assert invoice["invoice_number"] == f"{prefix}000001"


def test_order_rejects_fractional_item_quantity_without_partial_write(app, client, create_user):
    create_user("quantity.cashier", role="cashier", permissions=SALES_PERMISSIONS)
    product_id = _seed_product(app, price="2.000", quantity=5)
    _sign_in(client, "quantity.cashier")
    response = client.post(
        "/api/v1/orders",
        json={
            "store_id": "test-store",
            "customer_phone": "91234567",
            "items": [{"product_id": product_id, "quantity": 1.5}],
        },
    )
    assert response.status_code == 400
    with app.app_context():
        assert SalesOrder.query.count() == 0
        assert SalesOrderLine.query.count() == 0


def test_catalog_sales_use_server_price_deduct_stock_and_record_realtime_audit(app, client, create_user):
    create_user("catalog.seller", role="cashier", permissions=SALES_PERMISSIONS)
    product_id = _seed_product(app, name="Olive oil", sku="OLIVE-1", price="4.250", quantity=7)
    _sign_in(client, "catalog.seller")

    response = client.post(
        "/api/v1/orders",
        json={
            "store_id": "test-store",
            "customer_phone": "91234567",
            "items": [{
                "product_id": product_id,
                "quantity": 3,
                "name": "Forged item name",
                "unit_price": "0.001",
            }],
        },
    )

    assert response.status_code == 201, response.get_json()
    order = response.get_json()["order"]
    assert order["order_number"] == "ORD-000001"
    assert order["total_amount"] == "12.750"
    assert order["items"][0]["product_id"] == product_id
    assert order["items"][0]["name"] == "Olive oil"
    assert order["items"][0]["unit_price"] == "4.250"
    with app.app_context():
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=product_id).one()
        assert balance.quantity_on_hand == 4
        movement = InventoryMovement.query.filter_by(product_id=product_id, movement_type="sale").one()
        assert movement.quantity_delta == -3
        assert AuditEvent.query.filter_by(action="inventory.sale_deducted", entity_id=balance.id).count() == 1
        assert RealtimeEvent.query.filter_by(product_id=product_id, event_type="inventory.updated").count() == 1


def test_adding_catalog_item_to_open_bill_deducts_stock_and_preserves_order_reference(app, client, create_user):
    create_user("catalog.add-seller", role="cashier", permissions=SALES_PERMISSIONS)
    first_product = _seed_product(app, name="Tea", sku="TEA-1", price="1.250", quantity=8)
    second_product = _seed_product(app, name="Dates", sku="DATES-1", price="2.750", quantity=3)
    _sign_in(client, "catalog.add-seller")
    order = client.post(
        "/api/v1/orders",
        json={"store_id": "test-store", "customer_phone": "91234567", "items": [{"product_id": first_product, "quantity": 2}]},
    ).get_json()["order"]

    added = client.post(
        f"/api/v1/orders/{order['id']}/items",
        json={"store_id": "test-store", "product_id": second_product, "quantity": 1, "unit_price": "0.001"},
    )
    assert added.status_code == 200, added.get_json()
    updated = added.get_json()["order"]
    assert updated["order_number"] == order["order_number"]
    assert updated["total_amount"] == "5.250"
    assert {row["product_id"] for row in updated["items"]} == {first_product, second_product}
    with app.app_context():
        assert InventoryBalance.query.filter_by(product_id=first_product).one().quantity_on_hand == 6
        assert InventoryBalance.query.filter_by(product_id=second_product).one().quantity_on_hand == 2
        assert OrderNumberSeries.query.filter_by(company_id="test-company").one().next_number == 2


def test_sales_domain_permission_is_required_before_creating_a_bill(app, client, create_user):
    create_user(
        "restricted.seller",
        role="cashier",
        permissions=["use_sales_pos", "open_bills.add", "product_catalog.view", "inventory.view"],
    )
    product_id = _seed_product(app, price="3.000", quantity=4)
    _sign_in(client, "restricted.seller")
    response = client.post(
        "/api/v1/orders",
        json={
            "store_id": "test-store",
            "customer_phone": "91234567",
            "items": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert response.status_code == 403
    with app.app_context():
        assert SalesOrder.query.count() == 0
        assert OrderNumberSeries.query.filter_by(company_id="test-company").one().next_number == 1
        assert InventoryBalance.query.filter_by(product_id=product_id).one().quantity_on_hand == 4


def test_insufficient_stock_rolls_back_order_number_and_inventory(app, client, create_user):
    create_user("stock.seller", role="cashier", permissions=SALES_PERMISSIONS)
    product_id = _seed_product(app, price="1.500", quantity=1)
    _sign_in(client, "stock.seller")
    response = client.post(
        "/api/v1/orders",
        json={
            "store_id": "test-store",
            "customer_phone": "91234567",
            "items": [{"product_id": product_id, "quantity": 2}],
        },
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "insufficient_stock"
    with app.app_context():
        assert SalesOrder.query.count() == 0
        assert OrderNumberSeries.query.filter_by(company_id="test-company").one().next_number == 1
        assert InventoryBalance.query.filter_by(store_id="test-store", product_id=product_id).one().quantity_on_hand == 1
        assert InventoryMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 0
        assert RealtimeEvent.query.filter_by(product_id=product_id).count() == 0


def test_removal_requires_manager_approval_and_updates_audit(app, client, create_user):
    create_user("sales.requester", role="cashier", permissions=SALES_PERMISSIONS)
    create_user("store.manager", role="manager", permissions=["open_bills.edit", "inventory.add"])
    _sign_in(client, "sales.requester")
    order = _create_api_order(client, quantity=2, price="3.000")
    line_id = order["items"][0]["id"]
    requested = client.post(
        f"/api/v1/orders/{order['id']}/items/{line_id}/removal-requests",
        json={"store_id": "test-store", "quantity_to_remove": 1, "reason": "Customer changed mind"},
    )
    assert requested.status_code == 201
    request_id = requested.get_json()["removal_request"]["id"]
    assert requested.get_json()["removal_request"]["status"] == "pending"

    manager_client = app.test_client()
    _sign_in(manager_client, "store.manager")
    pending = manager_client.get("/api/v1/order-removal-requests")
    assert pending.status_code == 200
    assert [row["id"] for row in pending.get_json()["removal_requests"]] == [request_id]
    reviewed = manager_client.post(
        f"/api/v1/order-removal-requests/{request_id}/review",
        json={"decision": "approve", "review_reason": "Verified with customer"},
    )
    assert reviewed.status_code == 200, reviewed.get_json()
    assert reviewed.get_json()["removal_request"]["status"] == "approved"

    bill = client.get(f"/api/v1/orders/{order['id']}", query_string={"store_id": "test-store"}).get_json()["order"]
    assert bill["total_amount"] == "3.000"
    assert bill["items"][0]["quantity"] == 1
    assert bill["status"] == "open"
    with app.app_context():
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=order["items"][0]["product_id"]).one()
        assert balance.quantity_on_hand == 99
        assert InventoryMovement.query.filter_by(product_id=order["items"][0]["product_id"], movement_type="sale").one().quantity_delta == -2
        assert InventoryMovement.query.filter_by(product_id=order["items"][0]["product_id"], movement_type="return").one().quantity_delta == 1
        request_row = db.session.get(OrderRemovalRequest, request_id)
        assert request_row.status == "approved"
        assert {event.action for event in AuditEvent.query.filter(AuditEvent.entity_id.in_([request_id, line_id])).all()} >= {
            "order.item_removal_requested",
            "order.item_removed",
        }


def test_approved_full_removal_voids_unpaid_bill_without_invoice(app, client, create_user):
    create_user("void.requester", role="cashier", permissions=SALES_PERMISSIONS)
    create_user("void.manager", role="manager", permissions=["open_bills.edit", "inventory.add"])
    _sign_in(client, "void.requester")
    order = _create_api_order(client, quantity=1, price="4.000")
    line_id = order["items"][0]["id"]
    request_response = client.post(
        f"/api/v1/orders/{order['id']}/items/{line_id}/removal-requests",
        json={"store_id": "test-store", "quantity_to_remove": 1, "reason": "Order cancelled by customer"},
    )
    request_id = request_response.get_json()["removal_request"]["id"]
    manager_client = app.test_client()
    _sign_in(manager_client, "void.manager")
    approved = manager_client.post(
        f"/api/v1/order-removal-requests/{request_id}/review",
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    with app.app_context():
        voided = db.session.get(SalesOrder, order["id"])
        assert voided.status == "voided"
        assert voided.invoice_number is None
        assert db.session.get(SalesOrderLine, line_id).is_active is False
        assert AuditEvent.query.filter_by(action="order.voided", entity_id=order["id"]).count() == 1


def test_removal_cannot_reduce_bill_below_paid_total_and_request_remains_pending(app, client, create_user):
    create_user("sales.paid", role="cashier", permissions=SALES_PERMISSIONS)
    create_user("approval.manager", role="manager", permissions=["open_bills.edit", "inventory.add"])
    _sign_in(client, "sales.paid")
    order = _create_api_order(client, quantity=2, price="5.000")
    line_id = order["items"][0]["id"]
    payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "6.000", "idempotency_key": "partial-paid"},
    )
    assert payment.status_code == 200
    request_response = client.post(
        f"/api/v1/orders/{order['id']}/items/{line_id}/removal-requests",
        json={"store_id": "test-store", "quantity_to_remove": 1, "reason": "Wrong size"},
    )
    request_id = request_response.get_json()["removal_request"]["id"]

    manager_client = app.test_client()
    _sign_in(manager_client, "approval.manager")
    response = manager_client.post(
        f"/api/v1/order-removal-requests/{request_id}/review",
        json={"decision": "approve"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "refund_required"
    with app.app_context():
        assert db.session.get(OrderRemovalRequest, request_id).status == "pending"
        assert db.session.get(SalesOrder, order["id"]).total_amount == 10
        assert db.session.get(SalesOrderLine, line_id).quantity == 2


def test_cashup_uses_payments_and_requires_company_admin_review(app, client, create_user):
    create_user("cashier.close", role="cashier", permissions=SALES_PERMISSIONS)
    create_user("manager.close", role="manager")
    create_user("company.admin", role="company_admin")
    _sign_in(client, "cashier.close")
    order = _create_api_order(client, quantity=1, price="7.500")
    payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        json={"store_id": "test-store", "method": "cash", "amount": "7.500", "idempotency_key": "cashup-order"},
    )
    assert payment.status_code == 200
    with app.app_context():
        today = company_today(db.session.get(Company, "test-company")).isoformat()

    manager_client = app.test_client()
    _sign_in(manager_client, "manager.close")
    submitted = manager_client.post(
        "/api/v1/cashups",
        json={
            "store_id": "test-store",
            "business_date": today,
            "counted": {"cash": "7.000", "bank": "0", "bank_transfer": "0", "other": "0"},
            "notes": "Drawer was counted by two staff.",
        },
    )
    assert submitted.status_code == 201, submitted.get_json()
    cashup = submitted.get_json()["cashup"]
    assert cashup["expected"]["cash"] == "7.500"
    assert cashup["variance"]["cash"] == "-0.500"
    cashup_id = cashup["id"]
    forbidden = manager_client.post(f"/api/v1/cashups/{cashup_id}/review", json={"decision": "approve"})
    assert forbidden.status_code == 403

    admin_client = app.test_client()
    _sign_in(admin_client, "company.admin")
    reviewed = admin_client.post(f"/api/v1/cashups/{cashup_id}/review", json={"decision": "approve"})
    assert reviewed.status_code == 200
    assert reviewed.get_json()["cashup"]["status"] == "approved"
    with app.app_context():
        assert db.session.get(DailyCashup, cashup_id).status == "approved"
        assert AuditEvent.query.filter_by(entity_type="daily_cashup", entity_id=cashup_id).count() == 2


def test_super_admin_cashup_submission_uses_selected_company_context(client, create_user):
    create_user("main.cashup", role="super_admin")
    _sign_in(client, "main.cashup")
    today = date.today().isoformat()
    response = client.post(
        "/api/v1/cashups",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "business_date": today,
            "counted": {"cash": "0", "bank": "0", "bank_transfer": "0", "other": "0"},
        },
    )
    assert response.status_code == 201, response.get_json()


def test_rejected_cashup_can_be_resubmitted_by_another_manager(app, create_user):
    create_user("manager.first", role="manager")
    create_user("manager.second", role="manager")
    create_user("cashup.reviewer", role="company_admin")
    with app.app_context():
        today = company_today(db.session.get(Company, "test-company")).isoformat()

    first_client = app.test_client()
    _sign_in(first_client, "manager.first")
    first = first_client.post(
        "/api/v1/cashups",
        json={"store_id": "test-store", "business_date": today, "counted": {"cash": 0, "bank": 0, "bank_transfer": 0, "other": 0}},
    )
    assert first.status_code == 201
    cashup_id = first.get_json()["cashup"]["id"]

    reviewer = app.test_client()
    _sign_in(reviewer, "cashup.reviewer")
    rejected = reviewer.post(f"/api/v1/cashups/{cashup_id}/review", json={"decision": "reject", "note": "Please recount the till."})
    assert rejected.status_code == 200
    assert rejected.get_json()["cashup"]["status"] == "rejected"

    second_client = app.test_client()
    _sign_in(second_client, "manager.second")
    resubmitted = second_client.post(
        "/api/v1/cashups",
        json={"store_id": "test-store", "business_date": today, "counted": {"cash": 0, "bank": 0, "bank_transfer": 0, "other": 0}},
    )
    assert resubmitted.status_code == 201, resubmitted.get_json()
    assert resubmitted.get_json()["cashup"]["id"] == cashup_id
    with app.app_context():
        cashup = db.session.get(DailyCashup, cashup_id)
        assert cashup.status == "submitted"
        assert cashup.submitted_by_id == User.query.filter_by(username="manager.second").one().id
        assert AuditEvent.query.filter_by(entity_id=cashup_id, action="cashup.submitted").count() == 2


def test_billing_admin_configures_mixed_tender_category_and_monotonic_series(app, client, create_user):
    create_user("billing.admin", role="company_admin")
    _sign_in(client, "billing.admin")
    page = client.get("/admin/companies/test-company/billing")
    assert page.status_code == 200
    assert b"Mixed payment classification" in page.data

    data = {
        "mixed_tender_category": "bank_transfer",
        "order_prefix": "ORDERX-",
        "order_next_number": "12",
        "cash_prefix": "CASHX-",
        "cash_next_number": "5",
        "bank_prefix": "BANKX-",
        "bank_next_number": "1",
        "bank_transfer_prefix": "WIRE-",
        "bank_transfer_next_number": "3",
        "other_prefix": "OTHX-",
        "other_next_number": "1",
    }
    saved = client.post("/admin/companies/test-company/billing", data=data, follow_redirects=False)
    assert saved.status_code == 302
    with app.app_context():
        company = db.session.get(Company, "test-company")
        assert company.mixed_tender_category == "bank_transfer"
        order_series = OrderNumberSeries.query.filter_by(company_id=company.id).one()
        assert (order_series.prefix, order_series.next_number) == ("ORDERX-", 12)
        series = BillingSeries.query.filter_by(company_id=company.id).all()
        assert {row.category: (row.prefix, row.next_number) for row in series}["cash"] == ("CASHX-", 5)
        assert AuditEvent.query.filter_by(action="billing_settings.updated").count() == 1

    data["cash_next_number"] = "4"
    data["order_next_number"] = "11"
    rejected = client.post("/admin/companies/test-company/billing", data=data)
    assert rejected.status_code == 200
    assert b"cannot be moved backwards" in rejected.data
    with app.app_context():
        assert BillingSeries.query.filter_by(company_id="test-company", category="cash").one().next_number == 5
        assert OrderNumberSeries.query.filter_by(company_id="test-company").one().next_number == 12


def test_cashier_cannot_review_or_submit_manager_closeout(client, create_user):
    create_user("limited.cashier", role="cashier")
    _sign_in(client, "limited.cashier")
    response = client.post(
        "/api/v1/cashups",
        json={"store_id": "test-store", "business_date": date.today().isoformat(), "counted": {"cash": 0}},
    )
    assert response.status_code == 403


def test_pos_cashup_and_removal_review_pages_render(app, client, create_user):
    create_user("pages.manager", role="manager", permissions=SALES_PERMISSIONS)
    _sign_in(client, "pages.manager")
    assert client.get("/pos").status_code == 200
    assert b"Open customer bill" in client.get("/pos").data
    assert client.get("/cashups").status_code == 200
    assert client.get("/removals").status_code == 200

    main_client = app.test_client()
    create_user("pages.super", role="super_admin")
    _sign_in(main_client, "pages.super")
    pos = main_client.get("/pos")
    assert pos.status_code == 200
    assert b"Select company" in pos.data
    cashups = main_client.get("/cashups")
    assert cashups.status_code == 200
    assert b"Select company" in cashups.data
