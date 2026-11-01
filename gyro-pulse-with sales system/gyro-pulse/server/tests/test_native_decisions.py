from copy import deepcopy
import hashlib
from uuid import uuid4
import pytest
from test_field_mobile import enrolled, exchange, headers, wire
from test_field_orders import ready
from test_dedicated_recovery import dedicated_app
from test_pairing import paired_app
from models import db
from sync_core import canonical, Outbox
from field_mobile import NativeDecision
from catalog_bridge import CatalogHead


def office_headers(pair):
    from integration_api import Office, Credential, digest
    import secrets

    token = secrets.token_urlsafe(32)
    credential = db.session.get(
        Credential, db.session.get(Office, 1).current_credential_id
    )
    credential.secret_hash = digest(token)
    credential.scopes = list(dict.fromkeys(list(credential.scopes) + ["transport:exchange"]))
    db.session.commit()
    identity = pair[0].config
    return {
        "Authorization": "Bearer " + token,
        "X-Company-ID": identity["GYRO_COMPANY_ID"],
        "X-Instance-ID": identity["GYRO_INSTANCE_ID"],
        "X-Office-ID": Office.query.one().office_id,
    }


def record(grant, payload, state="approved"):
    return dict(
        schema_version=1,
        company_id=grant["company_id"],
        instance_id=grant["instance_id"],
        office_id=grant["office_id"],
        order_id=payload["order_id"],
        payload_sha256=hashlib.sha256(canonical(payload).encode()).hexdigest(),
        device_id=grant["device_id"],
        state=state,
        native_order_id=str(uuid4()) if state == "approved" else None,
    )


@pytest.mark.parametrize("state", ["approved", "rejected"])
def test_offline_first_decision_reconciles_stale_catalog_without_second_delivery(
    enrolled, state
):
    pair, _, payload, key, _, grant, _ = enrolled
    c = pair[1]
    token = exchange(enrolled).json
    h = headers(token)
    signed = wire(key, grant, payload)
    CatalogHead.query.one().message_id = str(uuid4())
    db.session.commit()
    assert c.post("/api/v1/device/orders", headers=h, json=signed).status_code == 409
    office = office_headers(pair)
    data = record(grant, payload, state)
    assert c.post("/api/v1/devices/decisions", headers=h, json=data).status_code == 401
    first = c.post("/api/v1/devices/decisions", headers=office, json=data)
    assert first.status_code == 200, first.data
    assert (
        c.post("/api/v1/devices/decisions", headers=office, json=data).json
        == first.json
    )
    response = c.post("/api/v1/device/orders", headers=h, json=signed)
    assert response.status_code == 200 and response.json["native_approval"] == state
    assert response.json["native_order_id"] == data["native_order_id"]
    assert Outbox.query.count() == 0 and NativeDecision.query.count() == 1
    changed = deepcopy(data)
    changed["payload_sha256"] = "0" * 64
    assert (
        c.post("/api/v1/devices/decisions", headers=office, json=changed).status_code
        == 409
    )
    changed_payload = deepcopy(payload)
    changed_payload["customer_name"] = "altered"
    assert (
        c.post(
            "/api/v1/device/orders", headers=h, json=wire(key, grant, changed_payload)
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "bad",
    [
        "scope",
        "device",
        "hash",
        "pending",
        "approved_without_order",
        "rejected_with_order",
    ],
)
def test_invalid_decision_never_creates_fact(enrolled, bad):
    pair, _, payload, _, _, grant, _ = enrolled
    exchange(enrolled)
    h = office_headers(pair)
    data = record(grant, payload)
    if bad == "scope":
        data["company_id"] = str(uuid4())
    elif bad == "device":
        data["device_id"] = str(uuid4())
    elif bad == "hash":
        data["payload_sha256"] = "x" * 64
    elif bad == "pending":
        data["state"] = "pending"
    elif bad == "approved_without_order":
        data["native_order_id"] = None
    else:
        data["state"] = "rejected"
    assert (
        pair[1].post("/api/v1/devices/decisions", headers=h, json=data).status_code
        == 409
    )
    assert NativeDecision.query.count() == 0 and Outbox.query.count() == 0
