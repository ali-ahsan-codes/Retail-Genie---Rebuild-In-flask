from copy import deepcopy
from uuid import uuid4
import json
import pytest
from test_dedicated_recovery import dedicated_app
from test_pairing import paired_app
from test_transport_api import authorized
from test_catalog_bridge import payload as catalog_payload, receive
from models import db
from catalog_bridge import apply_message
from field_orders import SubmittedOrder, enqueue_proposal
from order_contract import OrderError
from sync_core import Outbox


@pytest.fixture
def ready(paired_app):
    value, h, office, cloud = authorized(paired_app)
    mid = receive(office, cloud, catalog_payload())
    apply_message(cloud, mid)
    db.session.commit()
    payload = dict(
        schema_version=1,
        order_id=str(uuid4()),
        store_id="store-1",
        catalog_message_id=mid,
        customer_phone="+96891234567",
        customer_name="Synthetic",
        items=[dict(product_id="product-1", quantity=2, unit_price="1.250")],
    )
    return paired_app, cloud, payload


def test_cloud_business_id_dedup_and_no_legacy_write(ready):
    pair, cloud, payload = ready
    row = enqueue_proposal(cloud, payload, 1)
    db.session.commit()
    assert enqueue_proposal(cloud, payload, 1).message_id == row.message_id
    assert Outbox.query.count() == 1 and SubmittedOrder.query.count() == 1
    altered = deepcopy(payload)
    altered["customer_name"] = "Changed"
    with pytest.raises(OrderError):
        enqueue_proposal(cloud, altered, 1)


@pytest.mark.parametrize("bad", ["stale", "price", "product", "quantity", "extra"])
def test_malformed_or_stale_proposals_rejected(ready, bad):
    pair, cloud, payload = ready
    if bad == "stale":
        payload["catalog_message_id"] = str(uuid4())
    elif bad == "price":
        payload["items"][0]["unit_price"] = "9.000"
    elif bad == "product":
        payload["items"][0]["product_id"] = "other-company-product"
    elif bad == "quantity":
        payload["items"][0]["quantity"] = True
    else:
        payload["paid"] = True
    with pytest.raises(OrderError):
        enqueue_proposal(cloud, payload, 1)
    assert Outbox.query.count() == 0 and SubmittedOrder.query.count() == 0


def test_cloud_ui_admin_csrf_and_bounded_submit(ready):
    pair, cloud, payload = ready
    app, c, _ = pair
    from flask import g

    # Fixture retains an outer app context; real requests do not share g across clients.
    g.pop("_login_user", None)
    assert app.test_client().get("/integrations/orders").status_code == 403
    g.pop("_login_user", None)
    assert c.get("/integrations/orders").status_code == 200
    assert (
        c.post(
            "/integrations/orders", data={"proposal": json.dumps(payload)}
        ).status_code
        == 400
    )
    with c.session_transaction() as session:
        csrf = session["hybrid_csrf"]
    response = c.post(
        "/integrations/orders",
        data={"csrf_token": csrf, "proposal": json.dumps(payload)},
    )
    assert (
        response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    )
    assert SubmittedOrder.query.count() == 1 and Outbox.query.count() == 1


def test_rollback_removes_business_mapping_and_outbox(ready):
    _, cloud, payload = ready
    enqueue_proposal(cloud, payload, 1)
    db.session.rollback()
    assert SubmittedOrder.query.count() == 0 and Outbox.query.count() == 0
