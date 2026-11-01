import json, os
from datetime import datetime, timedelta
from uuid import uuid4
from copy import deepcopy
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from test_field_orders import staged
from test_field_catalog import native
from retail_genie.extensions import db
from retail_genie.field_integration import FieldConnection
from retail_genie.field_mobile import (
    DeviceRegistry,
    DeviceIngress,
    store_registry,
    accept_parcel,
    bp,
)
from retail_genie.mobile_crypto import b64, verify, LABEL, aad, MobileError
from retail_genie.models import SalesOrder, InventoryBalance
from retail_genie.field_orders import FieldProposal, review


def public(key):
    return b64(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def encrypt(wire, key, identity):
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    shared = ephemeral.exchange(ec.ECDH(), key.public_key())
    aes = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=LABEL).derive(
        shared
    )
    nonce = os.urandom(12)
    return dict(
        schema_version=1,
        company_id=identity[0],
        instance_id=identity[1],
        office_id=identity[2],
        ephemeral_key=public(ephemeral),
        nonce=b64(nonce),
        ciphertext=b64(
            AESGCM(aes).encrypt(nonce, json.dumps(wire).encode(), aad(identity))
        ),
    )


@pytest.fixture
def parcel(staged):
    app, company, store, product, actor, cloud, order, proposal = staged
    device = ec.generate_private_key(ec.SECP256R1())
    office = ec.generate_private_key(ec.SECP256R1())
    device_id = str(uuid4())
    connection = db.session.get(FieldConnection, company.id)
    identity = (connection.company_id, connection.instance_id, connection.office_id)
    registry = dict(
        schema_version=1,
        company_id=identity[0],
        instance_id=identity[1],
        office_id=identity[2],
        generated_at=datetime.utcnow().isoformat() + "Z",
        devices=[
            dict(
                device_id=device_id,
                owner_id=1,
                public_key=public(device),
                expires_at=(datetime.utcnow() + timedelta(days=1)).isoformat() + "Z",
            )
        ],
    )
    store_registry(connection, registry)
    db.session.commit()
    app.config["FIELD_OFFICE_PRIVATE_KEY_BASE64"] = b64(
        office.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    body = dict(
        schema_version=1,
        company_id=identity[0],
        instance_id=identity[1],
        office_id=identity[2],
        device_id=device_id,
        order=order,
    )
    raw = json.dumps(body).encode()
    wire = dict(
        body=b64(raw), signature=b64(device.sign(raw, ec.ECDSA(hashes.SHA256())))
    )
    return staged, encrypt(wire, office, identity), wire, device, identity, registry


def test_lan_file_cloud_business_reconciliation_single_native_sale(parcel):
    staged, packet, wire, device, identity, _ = parcel
    app, c, _, _, actor, _, _, proposal = staged
    # The proposal was already staged via cloud in the fixture. File/LAN retries don't duplicate it.
    first = accept_parcel(c.id, packet)
    db.session.commit()
    assert first["status"] == "office_received_unconfirmed"
    assert accept_parcel(c.id, packet) == first
    db.session.commit()
    assert FieldProposal.query.count() == 1 and DeviceIngress.query.count() == 1
    assert (
        SalesOrder.query.count() == 0
        and InventoryBalance.query.one().quantity_on_hand == 12
    )
    with app.test_request_context():
        order_id = review(actor, c.id, proposal.id, approve=True)
        assert review(actor, c.id, proposal.id, approve=True) == order_id
    assert (
        SalesOrder.query.count() == 1
        and InventoryBalance.query.one().quantity_on_hand == 10
    )


@pytest.mark.parametrize(
    "bad",
    [
        "ciphertext",
        "nonce",
        "scope",
        "stale_registry",
        "expired_device",
        "revoked_device",
        "missing_key",
    ],
)
def test_authenticated_parcel_denials_leave_native_unchanged(parcel, bad):
    staged, packet, _, _, identity, registry = parcel
    app, c, *_ = staged
    if bad == "ciphertext":
        packet["ciphertext"] = b64(b"broken")
    elif bad == "nonce":
        packet["nonce"] = b64(b"x")
    elif bad == "scope":
        packet["office_id"] = str(uuid4())
    elif bad == "stale_registry":
        DeviceRegistry.query.one().valid_until = datetime.utcnow() - timedelta(
            seconds=1
        )
    elif bad == "expired_device":
        data = deepcopy(DeviceRegistry.query.one().devices)
        data[0]["expires_at"] = "2000-01-01T00:00:00Z"
        DeviceRegistry.query.one().devices = data
    elif bad == "revoked_device":
        DeviceRegistry.query.one().devices = []
    else:
        app.config["FIELD_OFFICE_PRIVATE_KEY_BASE64"] = ""
    db.session.commit()
    with pytest.raises(MobileError):
        accept_parcel(c.id, packet)
    db.session.rollback()
    assert DeviceIngress.query.count() == 0 and SalesOrder.query.count() == 0


def test_registry_boundary_and_default_lan_disable(parcel):
    staged, packet, _, _, identity, data = parcel
    app, c, *_ = staged
    connection = db.session.get(FieldConnection, c.id)
    data["company_id"] = str(uuid4())
    with pytest.raises(MobileError):
        store_registry(connection, data)
    app.register_blueprint(bp)
    assert (
        app.test_client().post("/api/v1/field-device/orders", json=packet).status_code
        == 404
    )
    app.config["FIELD_LAN_INGRESS_ENABLED"] = True
    assert (
        app.test_client()
        .post(
            "/api/v1/field-device/orders",
            json=packet,
            headers={"Authorization": "Bearer NEVER_SEND_CLOUD_SECRET"},
        )
        .status_code
        == 400
    )


def test_signed_body_substitution_fails(parcel):
    staged, _, wire, device, identity, _ = parcel
    broken = {**wire, "body": b64(b"{}")}
    with pytest.raises(MobileError):
        verify(broken, public(device), identity, staged[0].name)
