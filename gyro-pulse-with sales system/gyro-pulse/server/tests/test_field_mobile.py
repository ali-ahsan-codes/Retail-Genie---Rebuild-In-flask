import base64, json, hashlib, re, html
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from test_dedicated_recovery import dedicated_app
from test_pairing import paired_app
from test_field_orders import ready
from field_mobile import Device, DeviceGrant
from mobile_crypto import b64, fingerprint
from models import db, User
from sync_core import Outbox, canonical


@pytest.fixture
def enrolled(ready):
    pair, cloud, payload = ready
    app, c, _ = pair
    key = ec.generate_private_key(ec.SECP256R1())
    pub = b64(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    device_id = str(uuid4())
    owner = User.query.filter_by(username="pair-admin").one()
    with c.session_transaction() as session:
        csrf = session["hybrid_csrf"]
    response = c.post(
        "/integrations/devices",
        data={
            "csrf_token": csrf,
            "action": "issue",
            "device_id": device_id,
            "owner_id": str(owner.id),
            "key_fingerprint": fingerprint(pub),
        },
    )
    assert response.status_code == 200, response.data
    grant = json.loads(
        html.unescape(
            re.search(r"<textarea[^>]*>(.*?)</textarea>", response.text, re.S).group(1)
        )
    )
    proof = b64(
        key.sign(
            (
                "retail.hybrid.device.enroll.v1|"
                + grant["grant_id"]
                + "|"
                + grant["pairing_code"]
            ).encode(),
            ec.ECDSA(hashes.SHA256()),
        )
    )
    return pair, cloud, payload, key, pub, grant, proof


def exchange(fixture):
    pair, cloud, payload, key, pub, grant, proof = fixture
    return pair[1].post(
        "/api/v1/devices/enroll",
        json={"grant": grant, "public_key": pub, "proof": proof},
    )


def headers(token):
    return {
        "Authorization": "Bearer " + token["access_token"],
        "X-Company-ID": token["company_id"],
        "X-Instance-ID": token["instance_id"],
        "X-Office-ID": token["office_id"],
        "X-Device-ID": token["device_id"],
    }


def wire(key, grant, payload):
    body = dict(
        schema_version=1,
        company_id=grant["company_id"],
        instance_id=grant["instance_id"],
        office_id=grant["office_id"],
        device_id=grant["device_id"],
        order=payload,
    )
    raw = json.dumps(body, ensure_ascii=False).encode()
    return dict(body=b64(raw), signature=b64(key.sign(raw, ec.ECDSA(hashes.SHA256()))))


def test_separate_scopes_signed_submit_and_business_dedup(enrolled):
    pair, cloud, payload, key, pub, grant, proof = enrolled
    c = pair[1]
    response = exchange(enrolled)
    assert response.status_code == 200, response.data
    token = response.json
    h = headers(token)
    assert token["scopes"] == ["catalog:read", "orders:submit"]
    assert grant["pairing_code"] not in str(DeviceGrant.query.one().__dict__)
    assert token["access_token"] not in str(Device.query.one().__dict__)
    assert exchange(enrolled).status_code == 401
    assert c.get("/api/v1/sync/pull", headers=h).status_code == 401
    assert c.get("/api/v1/device/catalog/store-1", headers=h).json["read_only"] is True
    signed = wire(key, grant, payload)
    first = c.post("/api/v1/device/orders", headers=h, json=signed)
    assert first.status_code == 200, first.data
    assert (
        first.json["status"] == "cloud_received"
        and first.json["native_approval"] == "unknown"
    )
    assert (
        first.json["payload_sha256"]
        == hashlib.sha256(canonical(payload).encode()).hexdigest()
    )
    assert c.post("/api/v1/device/orders", headers=h, json=signed).json == first.json
    assert Outbox.query.count() == 1
    assert c.post("/api/products", headers=h, json={}).status_code == 409


@pytest.mark.parametrize(
    "bad", ["proof", "fingerprint", "company", "expired", "revoked", "owner_inactive"]
)
def test_enrollment_denials_without_consumption(enrolled, bad):
    pair, cloud, payload, key, pub, grant, proof = enrolled
    c = pair[1]
    data = dict(grant=deepcopy(grant), public_key=pub, proof=proof)
    if bad == "proof":
        data["proof"] = b64(b"wrong")
    elif bad == "fingerprint":
        data["grant"]["key_fingerprint"] = "0" * 64
    elif bad == "company":
        data["grant"]["company_id"] = str(uuid4())
    elif bad == "expired":
        DeviceGrant.query.one().expires_at = datetime.utcnow() - timedelta(seconds=1)
    elif bad == "revoked":
        DeviceGrant.query.one().revoked_at = datetime.utcnow()
    else:
        User.query.filter_by(username="pair-admin").one().is_active = False
    db.session.commit()
    assert c.post("/api/v1/devices/enroll", json=data).status_code == 401
    assert DeviceGrant.query.one().consumed_at is None and Device.query.count() == 0


@pytest.mark.parametrize(
    "bad",
    [
        "unsigned",
        "changed_body",
        "wrong_key",
        "wrong_company_header",
        "expired",
        "revoked",
        "owner_inactive",
    ],
)
def test_device_order_denials(enrolled, bad):
    pair, _, payload, key, _, grant, _ = enrolled
    c = pair[1]
    token = exchange(enrolled).json
    h = headers(token)
    signed = wire(key, grant, payload)
    if bad == "unsigned":
        signed["signature"] = ""
    elif bad == "changed_body":
        signed["body"] = b64(b"{}")
    elif bad == "wrong_key":
        signed = wire(ec.generate_private_key(ec.SECP256R1()), grant, payload)
    elif bad == "wrong_company_header":
        h["X-Company-ID"] = str(uuid4())
    elif bad == "expired":
        Device.query.one().expires_at = datetime.utcnow() - timedelta(seconds=1)
    elif bad == "revoked":
        Device.query.one().revoked_at = datetime.utcnow()
    else:
        User.query.filter_by(username="pair-admin").one().is_active = False
    db.session.commit()
    assert c.post("/api/v1/device/orders", headers=h, json=signed).status_code in {
        401,
        409,
    }
    assert Outbox.query.count() == 0


def test_admin_csrf_and_revoke_pending_grant(enrolled):
    pair, _, _, _, _, grant, _ = enrolled
    c = pair[1]
    assert (
        c.post(
            "/integrations/devices",
            data={"action": "revoke", "device_id": grant["device_id"]},
        ).status_code
        == 400
    )
    with c.session_transaction() as session:
        csrf = session["hybrid_csrf"]
    assert (
        c.post(
            "/integrations/devices",
            data={
                "csrf_token": csrf,
                "action": "revoke",
                "device_id": grant["device_id"],
            },
        ).status_code
        == 200
    )
    assert exchange(enrolled).status_code == 401
