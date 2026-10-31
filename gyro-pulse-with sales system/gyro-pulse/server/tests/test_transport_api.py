from uuid import uuid4
from datetime import datetime, timedelta
import pytest
from test_pairing import paired_app, issue, exchange, headers
from test_dedicated_recovery import dedicated_app
from integration_api import db, Credential
from sync_core import Transport, Inbox, Outbox


def authorized(pair):
    app, client, office = pair
    value = exchange(pair, issue(pair)).json
    with client.session_transaction() as session:
        csrf = session["hybrid_csrf"]
    assert (
        client.post(
            "/integrations", data={"action": "transport_enable", "csrf_token": csrf}
        ).status_code
        == 200
    )
    return (
        value,
        headers(value),
        Transport(
            "retail", value["company_id"], value["instance_id"], value["office_id"]
        ),
        Transport(
            "gyro", value["company_id"], value["instance_id"], value["office_id"]
        ),
    )


def test_metadata_grant_cannot_escalate_or_transfer(paired_app):
    bundle = issue(paired_app)
    bundle["scopes"] += ["transport:exchange"]
    assert exchange(paired_app, bundle).status_code == 401
    bundle["scopes"] = ["connection:read"]
    value = exchange(paired_app, bundle).json
    app, c, _ = paired_app
    h = headers(value)
    assert c.get("/api/v1/sync/pull", headers=h).status_code == 401
    assert c.post("/api/v1/sync/messages", headers=h, json={}).status_code == 401
    assert (
        c.post("/integrations", data={"action": "transport_enable"}).status_code == 400
    )


def test_incoming_durable_duplicate_and_conflict(paired_app):
    value, h, office, cloud = authorized(paired_app)
    app, c, _ = paired_app
    env = office.envelope("catalog.snapshot", {"items": []})
    first = c.post("/api/v1/sync/messages", headers=h, json=env)
    assert first.status_code == 200 and first.json["status"] == "received"
    assert c.post("/api/v1/sync/messages", headers=h, json=env).json == first.json
    assert Inbox.query.count() == 1
    assert (
        c.post(
            "/api/v1/sync/messages", headers=h, json={**env, "payload": {"items": [1]}}
        ).status_code
        == 409
    )
    assert c.post("/api/products", headers=h, json={}).status_code == 409


def test_pull_ack_lost_receipt_and_stale_token(paired_app):
    value, h, office, cloud = authorized(paired_app)
    app, c, _ = paired_app
    row = cloud.enqueue(cloud.envelope("field.order", {"lines": []}))
    db.session.commit()
    job = c.get("/api/v1/sync/pull", headers=h).json["message"]
    receipt = office.accept(job["envelope"])
    db.session.commit()
    assert c.get("/api/v1/sync/pull", headers=h).json == {"message": None}
    # ACK lost: lease expires, same immutable order is redelivered with a new fencing token.
    db.session.get(Outbox, row.id).lease_until = datetime.utcnow() - timedelta(
        seconds=1
    )
    db.session.commit()
    again = c.get("/api/v1/sync/pull", headers=h).json["message"]
    assert (
        again["envelope"] == job["envelope"]
        and again["lease_token"] != job["lease_token"]
    )
    bad = dict(
        message_id=job["message_id"], lease_token=job["lease_token"], receipt=receipt
    )
    assert c.post("/api/v1/sync/ack", headers=h, json=bad).status_code == 409
    good = {**bad, "lease_token": again["lease_token"]}
    assert c.post("/api/v1/sync/ack", headers=h, json=good).json == {
        "status": "acknowledged"
    }
    assert c.get("/api/v1/sync/pull", headers=h).json == {"message": None}
    assert Inbox.query.count() == 1


def test_transport_disable_and_cross_company_fail_closed(paired_app):
    value, h, office, cloud = authorized(paired_app)
    app, c, _ = paired_app
    assert c.get("/api/v1/integration/status", headers=h).json["scopes"] == [
        "connection:read",
        "transport:exchange",
    ]
    assert (
        c.get(
            "/api/v1/sync/pull", headers={**h, "X-Company-ID": str(uuid4())}
        ).status_code
        == 401
    )
    with c.session_transaction() as s:
        csrf = s["hybrid_csrf"]
    assert (
        c.post(
            "/integrations", data={"action": "transport_disable", "csrf_token": csrf}
        ).status_code
        == 200
    )
    assert c.get("/api/v1/sync/pull", headers=h).status_code == 401
    assert c.get("/api/v1/integration/status", headers=h).status_code == 200


def test_unicode_and_large_legal_envelope(paired_app):
    value, h, office, cloud = authorized(paired_app)
    app, c, _ = paired_app
    env = office.envelope("catalog.snapshot", {"data": "آ" * 40000})
    import json

    raw = json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(raw) > 16384
    assert (
        c.post(
            "/api/v1/sync/messages",
            headers=h,
            data=raw,
            content_type="application/json",
        ).status_code
        == 200
    )
    cloud.enqueue(cloud.envelope("field.order", {"data": "آ" * 60000}))
    db.session.commit()
    response = c.get("/api/v1/sync/pull", headers=h)
    assert response.status_code == 200 and len(response.data) < 132096
    assert response.json["message"]["envelope"]["payload"]["data"] == "آ" * 60000
