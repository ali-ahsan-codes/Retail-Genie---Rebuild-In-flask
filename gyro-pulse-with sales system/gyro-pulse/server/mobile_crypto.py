"""P-256 signed device orders and ECDH/HKDF/AES-GCM office parcels, v1.
No bearer, shared master secret, CBC or plaintext fallback in offline/LAN packets.
"""

import base64, hashlib, json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from integration_contract import loads, uid
from order_contract import validate

LABEL = b"retail.hybrid.office-envelope.v1"
MAX_BODY = 16384


class MobileError(ValueError):
    pass


def b64(raw):
    return base64.b64encode(raw).decode("ascii")


def un64(value, limit):
    try:
        if type(value) is not str or len(value) > limit * 2:
            raise ValueError()
        raw = base64.b64decode(value, validate=True)
        if len(raw) > limit:
            raise ValueError()
        return raw
    except (ValueError, TypeError):
        raise MobileError("Invalid bounded base64") from None


def public(value):
    try:
        raw = un64(value, 256)
        key = serialization.load_der_public_key(raw)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            raise ValueError()
        return key
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise MobileError("P-256 public key required") from None


def fingerprint(value):
    key = public(value)
    return hashlib.sha256(
        key.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).hexdigest()


def verify(wire, public_key, identity, device_id):
    try:
        if type(wire) is not dict or set(wire) != {"body", "signature"}:
            raise ValueError()
        raw = un64(wire["body"], MAX_BODY)
        signature = un64(wire["signature"], 80)
        public(public_key).verify(signature, raw, ec.ECDSA(hashes.SHA256()))
        body = loads(raw.decode("utf-8"), limit=MAX_BODY)
        if (
            type(body) is not dict
            or set(body)
            != {
                "schema_version",
                "company_id",
                "instance_id",
                "office_id",
                "device_id",
                "order",
            }
            or type(body["schema_version"]) is not int
            or body["schema_version"] != 1
        ):
            raise ValueError()
        if (
            tuple(uid(body[k]) for k in ["company_id", "instance_id", "office_id"])
            != tuple(identity)
            or uid(body["device_id"]) != device_id
        ):
            raise ValueError()
        validate(body["order"])
        return body["order"]
    except (ValueError, TypeError, KeyError, InvalidSignature, UnicodeError):
        raise MobileError("Invalid signed device order") from None


def peek_device(wire):
    # Untrusted routing hint ONLY. Caller must verify signature before using order data.
    try:
        return uid(loads(un64(wire["body"], MAX_BODY).decode("utf-8"))["device_id"])
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise MobileError("Invalid device routing hint") from None


def aad(identity):
    return LABEL + b"|" + b"|".join(uid(item).encode("ascii") for item in identity)


def decrypt_parcel(parcel, private_der_b64, identity):
    try:
        if (
            type(parcel) is not dict
            or set(parcel)
            != {
                "schema_version",
                "company_id",
                "instance_id",
                "office_id",
                "ephemeral_key",
                "nonce",
                "ciphertext",
            }
            or type(parcel["schema_version"]) is not int
            or parcel["schema_version"] != 1
        ):
            raise ValueError()
        if tuple(
            uid(parcel[k]) for k in ["company_id", "instance_id", "office_id"]
        ) != tuple(identity):
            raise ValueError()
        private = serialization.load_der_private_key(
            un64(private_der_b64, 512), password=None
        )
        if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(
            private.curve, ec.SECP256R1
        ):
            raise ValueError()
        shared = private.exchange(ec.ECDH(), public(parcel["ephemeral_key"]))
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=LABEL).derive(
            shared
        )
        nonce = un64(parcel["nonce"], 12)
        if len(nonce) != 12:
            raise ValueError()
        raw = AESGCM(key).decrypt(
            nonce, un64(parcel["ciphertext"], 32768), aad(identity)
        )
        return loads(raw.decode("utf-8"), limit=32768)
    except (ValueError, TypeError, KeyError, InvalidTag, UnicodeError):
        raise MobileError("Invalid authenticated office parcel") from None
