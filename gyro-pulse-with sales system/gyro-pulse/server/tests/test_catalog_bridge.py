from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from test_dedicated_recovery import dedicated_app
from test_pairing import paired_app
from test_transport_api import authorized
from models import db
from sync_core import Inbox, Transport
from catalog_bridge import CatalogHead, CatalogApplication, apply_message, projection
from catalog_contract import CatalogError, validate


def payload(sequence=1):
    return dict(
        schema_version=1,
        mode="full",
        sequence=sequence,
        store=dict(id="store-1", code="MCT", name="Muscat"),
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        currency=None,
        items=[
            dict(
                id="product-1",
                sku="TEA",
                barcode=None,
                name="Tea",
                category=None,
                active=True,
                price="1.250",
                low_stock_price=None,
                on_hand=12,
                low_stock_threshold=3,
            )
        ],
    )


def receive(office, cloud, data):
    env = office.envelope("catalog.snapshot", data)
    cloud.accept(env)
    db.session.commit()
    return env["message_id"]


def test_atomic_apply_duplicate_and_read_only_api(paired_app):
    value, h, office, cloud = authorized(paired_app)
    _, client, _ = paired_app
    mid = receive(office, cloud, payload())
    assert client.get("/api/v1/catalog/snapshot/store-1", headers=h).status_code == 404
    assert apply_message(cloud, mid) == "applied"
    db.session.commit()
    assert apply_message(cloud, mid) == "applied"
    db.session.commit()
    assert CatalogApplication.query.count() == 1 and CatalogHead.query.count() == 1
    result = client.get("/api/v1/catalog/snapshot/store-1", headers=h)
    assert result.status_code == 200 and result.json["read_only"] is True
    assert result.json["payload"]["items"][0]["on_hand"] == 12
    assert db.session.get(Inbox, mid).receipt["status"] == "received"
    assert client.post("/api/products", headers=h, json={}).status_code == 409
    assert client.get("/api/v1/catalog/snapshot/store-1").status_code == 401


def test_reordering_full_replacement_and_conflicting_sequence(paired_app):
    _, _, office, cloud = authorized(paired_app)
    newest = payload(2)
    newest["items"] = []
    mid = receive(office, cloud, newest)
    apply_message(cloud, mid)
    db.session.commit()
    older = receive(office, cloud, payload(1))
    assert apply_message(cloud, older) == "stale"
    db.session.commit()
    assert projection(cloud, "store-1")["payload"]["items"] == []
    conflict = receive(office, cloud, payload(2))
    with pytest.raises(CatalogError):
        apply_message(cloud, conflict)
    db.session.rollback()
    assert projection(cloud, "store-1")["payload"]["sequence"] == 2


def test_rollback_and_cross_scope_do_not_change_projection(paired_app):
    _, _, office, cloud = authorized(paired_app)
    mid = receive(office, cloud, payload())
    apply_message(cloud, mid)
    db.session.rollback()
    assert CatalogHead.query.count() == 0 and CatalogApplication.query.count() == 0
    foreign = Transport("gyro", str(uuid4()), str(uuid4()), str(uuid4()))
    with pytest.raises(CatalogError):
        apply_message(foreign, mid)


@pytest.mark.parametrize(
    "bad",
    [
        "float",
        "negative_price",
        "bool_sequence",
        "duplicate",
        "delta",
        "currency",
        "huge_name",
        "unknown",
        "bool_stock",
    ],
)
def test_strict_catalog_contract(bad):
    data = payload()
    if bad == "float":
        data["items"][0]["price"] = 1.25
    elif bad == "negative_price":
        data["items"][0]["price"] = "-1.000"
    elif bad == "bool_sequence":
        data["sequence"] = True
    elif bad == "duplicate":
        data["items"] *= 2
    elif bad == "delta":
        data["mode"] = "delta"
    elif bad == "currency":
        data["currency"] = "OMR"
    elif bad == "huge_name":
        data["items"][0]["name"] = "x" * 501
    elif bad == "unknown":
        data["items"][0]["write_stock"] = True
    else:
        data["items"][0]["on_hand"] = True
    with pytest.raises(CatalogError):
        validate(data)
