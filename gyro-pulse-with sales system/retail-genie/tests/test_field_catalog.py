from uuid import uuid4
from decimal import Decimal
import pytest
from flask import Flask
from retail_genie.extensions import db
from retail_genie.models.tenancy import TenantContainer, Company, Store
from retail_genie.models.catalog import (
    CatalogProduct,
    InventoryBalance,
    InventoryMovement,
)
from retail_genie.field_integration import FieldConnection
from retail_genie.field_catalog import CatalogStream, enqueue_snapshot
from retail_genie.catalog_contract import CatalogError
from retail_genie.sync_core import Outbox, Inbox, decode


@pytest.fixture
def native():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        tenant = TenantContainer(name="Pilot", slug="pilot")
        db.session.add(tenant)
        db.session.flush()
        company = Company(name="Office", slug="office", tenant_container_id=tenant.id)
        db.session.add(company)
        db.session.flush()
        store = Store(
            name="Muscat",
            code="MCT",
            company_id=company.id,
            tenant_container_id=tenant.id,
        )
        db.session.add(store)
        product = CatalogProduct(
            company_id=company.id,
            tenant_container_id=tenant.id,
            name="Tea",
            sku="TEA",
            price=Decimal("1.250"),
            low_stock_price=Decimal("1.500"),
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(
            FieldConnection(
                company_id=company.id, instance_id=str(uuid4()), office_id=str(uuid4())
            )
        )
        db.session.add(
            InventoryBalance(
                tenant_container_id=tenant.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=12,
                low_stock_threshold=3,
            )
        )
        db.session.commit()
        yield app, company, store, product
        db.session.remove()
        db.drop_all()


def test_actual_native_mapping_without_stock_writes(native):
    _, c, s, p = native
    before = InventoryBalance.query.one().quantity_on_hand
    row = enqueue_snapshot(c.id, s.id)
    db.session.commit()
    payload = decode(row.envelope)["payload"]
    assert payload["store"] == dict(id=s.id, code="MCT", name="Muscat")
    item = payload["items"][0]
    assert (
        item["id"] == p.id
        and item["price"] == "1.250"
        and item["low_stock_price"] == "1.500"
    )
    assert (
        item["on_hand"] == 12
        and item["low_stock_threshold"] == 3
        and payload["currency"] is None
    )
    assert (
        InventoryBalance.query.one().quantity_on_hand == before
        and InventoryMovement.query.count() == 0
    )
    assert CatalogStream.query.one().sequence == 1 and Outbox.query.count() == 1


def test_reexport_sequence_and_null_inactive_missing_balance(native):
    _, c, s, p = native
    enqueue_snapshot(c.id, s.id)
    db.session.commit()
    p.is_active = False
    p.price = None
    p.low_stock_price = None
    InventoryBalance.query.delete()
    db.session.commit()
    row = enqueue_snapshot(c.id, s.id)
    db.session.commit()
    payload = decode(row.envelope)["payload"]
    assert payload["sequence"] == 2
    assert (
        payload["items"][0]["active"] is False
        and payload["items"][0]["price"] is None
        and payload["items"][0]["on_hand"] == 0
    )


def test_negative_native_on_hand_is_preserved_not_adjusted(native):
    _, c, s, _ = native
    InventoryBalance.query.one().quantity_on_hand = -2
    db.session.commit()
    row = enqueue_snapshot(c.id, s.id)
    db.session.commit()
    assert decode(row.envelope)["payload"]["items"][0]["on_hand"] == -2


def test_cross_company_store_and_catalog_excluded(native):
    _, c, s, p = native
    other = Company(
        name="Other", slug="other", tenant_container_id=c.tenant_container_id
    )
    db.session.add(other)
    db.session.flush()
    other_store = Store(
        company_id=other.id,
        tenant_container_id=c.tenant_container_id,
        name="Other",
        code="OTHER",
    )
    db.session.add(other_store)
    foreign = CatalogProduct(
        company_id=other.id,
        tenant_container_id=c.tenant_container_id,
        name="Secret",
        price=Decimal("999.000"),
    )
    db.session.add(foreign)
    db.session.commit()
    with pytest.raises(CatalogError):
        enqueue_snapshot(c.id, other_store.id)
    row = enqueue_snapshot(c.id, s.id)
    db.session.commit()
    assert [item["id"] for item in decode(row.envelope)["payload"]["items"]] == [p.id]


def test_rollback_covers_sequence_and_outbox(native):
    _, c, s, _ = native
    enqueue_snapshot(c.id, s.id)
    db.session.rollback()
    assert Outbox.query.count() == 0 and CatalogStream.query.count() == 0
    row = enqueue_snapshot(c.id, s.id)
    db.session.commit()
    assert decode(row.envelope)["payload"]["sequence"] == 1


@pytest.mark.parametrize("bad", ["limit", "oversize", "inactive_store", "shared"])
def test_invalid_export_no_partial_queue(native, bad):
    _, c, s, p = native
    if bad == "limit":
        for i in range(200):
            db.session.add(
                CatalogProduct(
                    company_id=c.id,
                    tenant_container_id=c.tenant_container_id,
                    name="Product " + str(i),
                )
            )
    elif bad == "oversize":
        p.name = "x" * 501
    elif bad == "inactive_store":
        s.is_active = False
    else:
        InventoryBalance.query.one().product_owner_company_id = str(uuid4())
    db.session.commit()
    with pytest.raises((CatalogError, ValueError)):
        enqueue_snapshot(c.id, s.id)
    db.session.rollback()
    assert Outbox.query.count() == 0 and CatalogStream.query.count() == 0
