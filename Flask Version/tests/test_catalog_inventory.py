import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from retail_genie.extensions import db
from retail_genie.models import (
    AuditEvent,
    CatalogProduct,
    Company,
    InventoryBalance,
    InventoryMovement,
    RealtimeEvent,
    Store,
    TenantContainer,
    TenantDataPolicy,
    UserStoreAssignment,
)
from retail_genie.tenancy.service import seed_tenant_data_policies


CATALOG_PERMISSIONS = [
    "product_catalog.view",
    "product_catalog.add",
    "product_catalog.edit",
    "product_catalog.delete",
    "inventory.view",
    "inventory.add",
    "inventory.edit",
]


def _login(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _create_product(client, *, name="Olive Oil", sku="OIL-001", company_id="test-company"):
    response = client.post(
        "/api/v1/products",
        json={
            "company_id": company_id,
            "name": name,
            "sku": sku,
            "category": "Grocery",
            "price": "3.250",
        },
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["product"]


def test_main_admin_must_select_a_tenant_before_opening_products(client, create_user):
    create_user("catalog.platform", role="super_admin", permissions=[])
    _login(client, "catalog.platform")
    response = client.get("/catalog/products")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/tenant")


def test_catalog_inventory_adjustments_are_scoped_audited_and_reconciled(client, create_user, app):
    create_user("inventory.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "inventory.manager")

    product = _create_product(client)
    listed = client.get("/api/v1/products", query_string={"store_id": "test-store"})
    assert listed.status_code == 200
    assert listed.get_json()["can_view_inventory"] is True
    assert listed.get_json()["products"][0]["id"] == product["id"]
    assert listed.get_json()["products"][0]["stock_quantity"] == 0

    received = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 12, "reason": "Supplier delivery"},
    )
    assert received.status_code == 201, received.get_json()
    assert received.get_json()["inventory"]["quantity_on_hand"] == 12
    assert received.get_json()["movement"]["movement_type"] == "receive"

    adjustment = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": -3, "reason": "Damaged units"},
    )
    assert adjustment.status_code == 201
    assert adjustment.get_json()["inventory"]["quantity_on_hand"] == 9

    insufficient = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": -10, "reason": "Should not overdraw"},
    )
    assert insufficient.status_code == 409
    assert insufficient.get_json()["error"] == "insufficient_stock"

    movements = client.get(
        f"/api/v1/products/{product['id']}/inventory-movements",
        query_string={"store_id": "test-store"},
    )
    assert movements.status_code == 200
    assert [row["quantity_delta"] for row in movements.get_json()["movements"]] == [-3, 12]
    assert [row["reason"] for row in movements.get_json()["movements"]] == ["Damaged units", "Supplier delivery"]

    with app.app_context():
        balance = InventoryBalance.query.filter_by(product_id=product["id"], store_id="test-store").one()
        assert balance.quantity_on_hand == 9
        assert CatalogProduct.query.count() == 1
        assert InventoryMovement.query.count() == 2
        assert db.session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "inventory.adjusted")
        ).scalar_one() == 2
        assert db.session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "catalog_product.created")
        ).scalar_one() == 1

    page = client.get("/catalog/products?store_id=test-store")
    assert page.status_code == 200
    assert b"Olive Oil" in page.data
    assert b"Stock adjustment" in page.data
    assert b"catalog-realtime.js" in page.data
    assert b"socket.io.min.js" in page.data


def test_catalog_preserves_expiry_demand_notice_and_store_threshold(client, create_user, app):
    create_user("metadata.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "metadata.manager")
    created = client.post(
        "/api/v1/products",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "name": "Short-life item",
            "sku": "EXP-01",
            "price": "5.000",
            "low_stock_price": "4.250",
            "expiry_date": "2027-02-03",
            "is_demand_notice_product": True,
            "low_stock_threshold": 3,
        },
    )
    assert created.status_code == 201, created.get_json()
    product = created.get_json()["product"]
    assert product["expiry_date"].startswith("2027-02-03")
    assert product["is_demand_notice_product"] is True
    assert product["low_stock_price"] == "4.250"

    listed = client.get("/api/v1/products", query_string={"store_id": "test-store"})
    row = listed.get_json()["products"][0]
    assert row["low_stock_threshold"] == 3
    assert row["is_low_stock"] is True
    page = client.get("/catalog/products?store_id=test-store")
    assert page.status_code == 200
    assert b"2027-02-03" in page.data
    assert b"Demand notice" in page.data

    updated = client.patch(
        f"/api/v1/products/{product['id']}",
        json={
            "store_id": "test-store",
            "low_stock_threshold": 5,
            "expiry_date": None,
            "is_demand_notice_product": False,
        },
    )
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()["product"]["expiry_date"] is None
    assert updated.get_json()["product"]["is_demand_notice_product"] is False

    with app.app_context():
        balance = InventoryBalance.query.filter_by(product_id=product["id"], store_id="test-store").one()
        assert balance.low_stock_threshold == 5
        event = AuditEvent.query.filter_by(action="catalog_product.updated", entity_id=product["id"]).one()
        assert event.before_data["low_stock_threshold"] == 3
        assert event.after_data["low_stock_threshold"] == 5


def test_catalog_domain_permissions_sku_conflicts_and_unassigned_store_are_enforced(client, create_user, app):
    create_user("catalog.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "catalog.manager")
    product = _create_product(client, name="Tea", sku="TEA-7")

    duplicate = client.post(
        "/api/v1/products",
        json={"company_id": "test-company", "name": "Duplicate tea", "sku": "tea-7"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"] == "duplicate_sku"

    with app.app_context():
        db.session.add(Store(
            id="unassigned-store",
            tenant_container_id="test-container",
            company_id="test-company",
            code="OTHER",
            name="Unassigned Store",
        ))
        db.session.commit()

    denied_store = client.get("/api/v1/products", query_string={"store_id": "unassigned-store"})
    assert denied_store.status_code == 403
    denied_stock = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "unassigned-store", "quantity_delta": 1, "reason": "Not assigned"},
    )
    assert denied_stock.status_code == 403

    create_user("catalog.no-permissions", role="manager", permissions=[])
    other_client = app.test_client()
    _login(other_client, "catalog.no-permissions")
    denied_catalog = other_client.get("/api/v1/products", query_string={"store_id": "test-store"})
    assert denied_catalog.status_code == 403
    denied_create = other_client.post(
        "/api/v1/products",
        json={"company_id": "test-company", "name": "Not permitted"},
    )
    assert denied_create.status_code == 403


def test_catalog_permission_does_not_grant_inventory_changes(app, create_user):
    create_user(
        "catalog.only",
        role="manager",
        permissions=["product_catalog.view", "product_catalog.add", "product_catalog.edit"],
    )
    client = app.test_client()
    _login(client, "catalog.only")
    product = _create_product(client, name="Catalog-only item", sku="CAT-ONLY")

    stock_change = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 1, "reason": "No inventory grant"},
    )
    assert stock_change.status_code == 403
    threshold_change = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"store_id": "test-store", "low_stock_threshold": 2},
    )
    assert threshold_change.status_code == 403
    threshold_on_create = client.post(
        "/api/v1/products",
        json={
            "company_id": "test-company",
            "store_id": "test-store",
            "name": "No threshold permission",
            "sku": "NO-THRESHOLD",
            "low_stock_threshold": 2,
        },
    )
    assert threshold_on_create.status_code == 403


def test_assigned_store_policy_applies_to_product_catalog_operations(app, client, create_user):
    create_user("assigned.catalog", role="manager", permissions=CATALOG_PERMISSIONS)
    with app.app_context():
        policy = TenantDataPolicy.query.filter_by(tenant_container_id="test-container", domain="product_catalog").one()
        policy.sharing_mode = "assigned_store"
        db.session.commit()

    _login(client, "assigned.catalog")
    product = _create_product(client, name="Assigned item", sku="ASG-1")
    listed = client.get("/api/v1/products", query_string={"store_id": "test-store"})
    assert listed.status_code == 200
    assert [row["id"] for row in listed.get_json()["products"]] == [product["id"]]

    updated = client.patch(f"/api/v1/products/{product['id']}", json={"name": "Updated assigned item"})
    assert updated.status_code == 200
    assert updated.get_json()["product"]["name"] == "Updated assigned item"


def test_company_default_policy_hides_sibling_products_until_main_admin_enables_sharing(app, client, create_user):
    with app.app_context():
        sibling = Company(
            id="sibling-company",
            tenant_container_id="test-container",
            name="Sibling Company",
            slug="sibling-company",
        )
        db.session.add(sibling)
        db.session.flush()
        sibling_store = Store(
            id="sibling-store",
            tenant_container_id="test-container",
            company_id=sibling.id,
            code="SIB",
            name="Sibling Store",
        )
        db.session.add(sibling_store)
        db.session.commit()

    create_user(
        "sibling.admin",
        role="company_admin",
        permissions=CATALOG_PERMISSIONS,
        company_id="sibling-company",
        tenant_container_id="test-container",
    )
    sibling_client = app.test_client()
    _login(sibling_client, "sibling.admin")
    sibling_product = _create_product(sibling_client, name="Sibling item", sku="SIB-01", company_id="sibling-company")

    create_user("company.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "company.manager")
    own_product = _create_product(client, name="Local item", sku="LOCAL-01")
    own_catalog = client.get("/api/v1/products", query_string={"store_id": "test-store"})
    assert own_catalog.status_code == 200
    own_ids = {row["id"] for row in own_catalog.get_json()["products"]}
    assert own_ids == {own_product["id"]}

    with app.app_context():
        policy = TenantDataPolicy.query.filter_by(
            tenant_container_id="test-container", domain="product_catalog"
        ).one()
        assert policy.sharing_mode == "company"
        policy.sharing_mode = "container"
        db.session.commit()

    shared_catalog = client.get("/api/v1/products", query_string={"store_id": "test-store"})
    assert shared_catalog.status_code == 200
    shared_ids = {row["id"] for row in shared_catalog.get_json()["products"]}
    assert shared_ids == {own_product["id"], sibling_product["id"]}


def test_foreign_container_products_are_not_visible_or_mutable(app, client, create_user):
    with app.app_context():
        foreign_container = TenantContainer(id="foreign-container", name="Other Tenant", slug="other-tenant")
        db.session.add(foreign_container)
        db.session.flush()
        seed_tenant_data_policies(foreign_container.id)
        foreign_company = Company(
            id="foreign-company",
            tenant_container_id=foreign_container.id,
            name="Foreign Company",
            slug="foreign-company",
        )
        db.session.add(foreign_company)
        db.session.flush()
        foreign_store = Store(
            id="foreign-store",
            tenant_container_id=foreign_container.id,
            company_id=foreign_company.id,
            code="F1",
            name="Foreign Store",
        )
        foreign_product = CatalogProduct(
            id="foreign-product",
            tenant_container_id=foreign_container.id,
            company_id=foreign_company.id,
            name="Foreign stock",
            sku="F-1",
            price=Decimal("5.000"),
            is_active=True,
        )
        db.session.add_all([foreign_store, foreign_product])
        db.session.commit()

    create_user("tenant.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "tenant.manager")
    foreign_list = client.get("/api/v1/products", query_string={"store_id": "foreign-store"})
    assert foreign_list.status_code == 404
    foreign_edit = client.patch("/api/v1/products/foreign-product", json={"name": "Taken over"})
    assert foreign_edit.status_code == 404
    foreign_inventory = client.post(
        "/api/v1/products/foreign-product/inventory",
        json={"store_id": "foreign-store", "quantity_delta": 10, "reason": "Cross-tenant attempt"},
    )
    assert foreign_inventory.status_code == 404

    with app.app_context():
        assert CatalogProduct.query.filter_by(id="foreign-product").one().name == "Foreign stock"
        assert InventoryBalance.query.count() == 0
        assert InventoryMovement.query.count() == 0
        db.session.add(
            InventoryBalance(
                tenant_container_id="test-container",
                company_id="test-company",
                store_id="test-store",
                product_owner_company_id="foreign-company",
                product_id="foreign-product",
                quantity_on_hand=10,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_inventory_transfer_moves_stock_atomically_and_emits_store_scoped_history(app, client, create_user):
    manager_id = create_user("transfer.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    with app.app_context():
        target = Store(
            id="transfer-store",
            tenant_container_id="test-container",
            company_id="test-company",
            code="B",
            name="Second Store",
        )
        db.session.add(target)
        db.session.flush()
        db.session.add(
            UserStoreAssignment(
                tenant_container_id="test-container",
                company_id="test-company",
                user_id=manager_id,
                store_id=target.id,
            )
        )
        db.session.commit()

    _login(client, "transfer.manager")
    product = _create_product(client, name="Transfer item", sku="MOVE-1")
    received = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 11, "reason": "Initial receipt"},
    )
    assert received.status_code == 201

    transfer = client.post(
        f"/api/v1/products/{product['id']}/transfers",
        json={
            "source_store_id": "test-store",
            "destination_store_id": "transfer-store",
            "quantity": 4,
            "reason": "Balance stock between branches",
        },
    )
    assert transfer.status_code == 201, transfer.get_json()
    result = transfer.get_json()["transfer"]
    assert result["source_quantity_on_hand"] == 7
    assert result["destination_quantity_on_hand"] == 4
    assert len(result["event_ids"]) == 2

    movements = client.get(
        f"/api/v1/products/{product['id']}/inventory-movements",
        query_string={"store_id": "test-store"},
    )
    assert movements.status_code == 200
    assert movements.get_json()["movements"][0]["movement_type"] == "transfer_out"
    target_inventory = client.get("/api/v1/products", query_string={"store_id": "transfer-store"})
    assert target_inventory.status_code == 200
    assert target_inventory.get_json()["products"][0]["stock_quantity"] == 4

    overdraw = client.post(
        f"/api/v1/products/{product['id']}/transfers",
        json={
            "source_store_id": "test-store",
            "destination_store_id": "transfer-store",
            "quantity": 8,
            "reason": "Must fail without partial transfer",
        },
    )
    assert overdraw.status_code == 409
    assert overdraw.get_json()["error"] == "insufficient_stock"

    with app.app_context():
        source = InventoryBalance.query.filter_by(store_id="test-store", product_id=product["id"]).one()
        destination = InventoryBalance.query.filter_by(store_id="transfer-store", product_id=product["id"]).one()
        assert (source.quantity_on_hand, destination.quantity_on_hand) == (7, 4)
        transfer_moves = InventoryMovement.query.filter(
            InventoryMovement.product_id == product["id"],
            InventoryMovement.movement_type.in_(["transfer_in", "transfer_out"]),
        ).all()
        assert sorted(move.quantity_delta for move in transfer_moves) == [-4, 4]
        audit = AuditEvent.query.filter_by(action="inventory.transferred").one()
        assert audit.after_data["quantity"] == 4
        transfer_events = [
            event for event in RealtimeEvent.query.filter_by(product_id=product["id"]).all()
            if (event.payload or {}).get("transfer_id")
        ]
        assert len(transfer_events) == 2
        assert {event.store_id for event in transfer_events} == {"test-store", "transfer-store"}

    page = client.get("/catalog/products?store_id=test-store")
    assert b"Store transfer" in page.data
    assert b"Second Store" in page.data


def test_product_csv_import_export_supports_barcode_search_and_is_atomic(app, client, create_user):
    create_user("csv.manager", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "csv.manager")
    first_csv = (
        "Product Name,Product Code,Barcode,Product Category,Unit Price,Qty,Expiry Date,"
        "Is Demand Item,Low Stock Threshold,Low Stock Price\n"
        "Olive Oil,CSV-001,6291234567890,Grocery,2.750,8,2027-04-05,true,3,2.500\n"
    )
    response = client.post(
        "/catalog/products/import",
        data={
            "store_id": "test-store",
            "file": (io.BytesIO(first_csv.encode("utf-8")), "products.csv"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"1 created" in response.data
    with app.app_context():
        product = CatalogProduct.query.filter_by(sku="CSV-001").one()
        product_id = product.id
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=product.id).one()
        assert balance.quantity_on_hand == 8
        assert balance.low_stock_threshold == 3

    barcode_match = client.get(
        "/api/v1/products",
        query_string={"store_id": "test-store", "q": "6291234567890"},
    )
    assert barcode_match.status_code == 200
    assert barcode_match.get_json()["products"][0]["id"] == product_id

    update_csv = "name,sku,price,quantity in stock\nOlive Oil Updated,CSV-001,3.125,5\n"
    updated = client.post(
        "/catalog/products/import",
        data={"store_id": "test-store", "file": (io.BytesIO(update_csv.encode()), "update.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b"1 updated" in updated.data
    with app.app_context():
        product = db.session.get(CatalogProduct, product_id)
        balance = InventoryBalance.query.filter_by(store_id="test-store", product_id=product_id).one()
        assert product.name == "Olive Oil Updated"
        assert str(product.price) == "3.125"
        assert balance.quantity_on_hand == 5
        assert InventoryMovement.query.filter_by(product_id=product_id).count() == 2

    exported = client.get("/catalog/products/export.csv?store_id=test-store")
    assert exported.status_code == 200
    assert exported.mimetype == "text/csv"
    row = next(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
    assert row["sku"] == "CSV-001"
    assert row["barcode"] == "6291234567890"
    assert row["quantityInStock"] == "5"
    assert row["lowStockThreshold"] == "3"

    invalid_csv = "name,sku,price\nShould Roll Back,ATOMIC-1,1.000\nMissing SKU, ,2.000\n"
    invalid = client.post(
        "/catalog/products/import",
        data={"store_id": "test-store", "file": (io.BytesIO(invalid_csv.encode()), "invalid.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"CSV row" in invalid.data
    with app.app_context():
        assert CatalogProduct.query.filter_by(sku="ATOMIC-1").count() == 0


def test_catalog_only_csv_export_does_not_disclose_inventory_and_stock_import_is_rejected(app, create_user):
    create_user(
        "csv.catalog.only",
        role="manager",
        permissions=["product_catalog.view", "product_catalog.add", "product_catalog.edit"],
    )
    client = app.test_client()
    _login(client, "csv.catalog.only")
    created = _create_product(client, name="Restricted stock", sku="CSV-PRIV")
    with app.app_context():
        balance = InventoryBalance.query.filter_by(product_id=created["id"], store_id="test-store").one()
        balance.quantity_on_hand = 9
        balance.low_stock_threshold = 2
        db.session.commit()

    exported = client.get("/catalog/products/export.csv?store_id=test-store")
    assert exported.status_code == 200
    row = next(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
    assert row["quantityInStock"] == ""
    assert row["lowStockThreshold"] == ""

    stock_csv = "name,sku,quantity in stock\nRestricted stock,CSV-PRIV,4\n"
    rejected = client.post(
        "/catalog/products/import",
        data={"store_id": "test-store", "file": (io.BytesIO(stock_csv.encode()), "stock.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"not allowed to" in rejected.data.lower()
    with app.app_context():
        balance = InventoryBalance.query.filter_by(product_id=created["id"], store_id="test-store").one()
        assert balance.quantity_on_hand == 9
