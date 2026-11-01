"""Separate scoped device enrollment. Legacy keys never authorize these routes."""

import hashlib, json, os, secrets
from datetime import datetime, timedelta
from uuid import uuid4
import click
from flask import Blueprint, current_app, jsonify, request, session, render_template
from flask_login import current_user
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from models import db, User
from integration_contract import uid, origin, loads
from integration_api import Office, Audit, Credential, authenticate as office_auth
from mobile_crypto import fingerprint, verify, MobileError, public, un64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
from field_orders import SubmittedOrder, enqueue_proposal
from sync_core import Transport, canonical

bp = Blueprint("mobile", __name__)
SCOPES = ["catalog:read", "orders:submit"]
GRANT_FIELDS = {
    "schema_version",
    "company_id",
    "instance_id",
    "office_id",
    "device_id",
    "grant_id",
    "pairing_code",
    "expires_at",
    "base_url",
    "key_fingerprint",
    "scopes",
}


def digest(raw):
    return hashlib.sha256(("retail.hybrid.device.v1:" + raw).encode()).hexdigest()


def utc(dt):
    return dt.isoformat() + "Z"


class Device(db.Model):
    __tablename__ = "hybrid_field_devices"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)
    public_key = db.Column(db.String(400), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class DeviceGrant(db.Model):
    __tablename__ = "hybrid_device_grants"
    id = db.Column(db.String(36), primary_key=True)
    device_id = db.Column(db.String(36), nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)
    key_fingerprint = db.Column(db.String(64), nullable=False)
    secret_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


@bp.before_request
def guard():
    if current_app.config["GYRO_DEPLOYMENT_MODE"] != "dedicated":
        return jsonify(error="Dedicated deployment required"), 409
    if request.content_length and request.content_length > 65536:
        return jsonify(error="Request too large"), 413
    if not inspect(db.engine).has_table(Office.__tablename__):
        return jsonify(error="Initialize/pair office first"), 503
    slot = db.session.get(Office, 1)
    if slot is None or not slot.current_credential_id:
        return jsonify(error="Active office pairing required"), 409
    if not inspect(db.engine).has_table(Credential.__tablename__):
        return jsonify(error="Initialize office credentials explicitly"), 503
    credential = db.session.get(Credential, slot.current_credential_id)
    if (
        not credential
        or credential.revoked_at
        or credential.expires_at <= datetime.utcnow()
    ):
        return jsonify(error="Active office pairing required"), 401
    if not all(
        inspect(db.engine).has_table(m.__tablename__) for m in [Device, DeviceGrant]
    ):
        return jsonify(error="Initialize device tables explicitly"), 503


@bp.after_request
def private(response):
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        }
    )
    return response


def identity():
    return (
        current_app.config["GYRO_COMPANY_ID"],
        current_app.config["GYRO_INSTANCE_ID"],
        db.session.get(Office, 1).office_id,
    )


def current_device(scope):
    header = request.headers.get("Authorization", "")
    if (
        not header.startswith("Bearer ")
        or len(header) != 50
        or not header.isascii()
        or scope not in SCOPES
    ):
        return None
    row = db.session.get(Device, request.headers.get("X-Device-ID", ""))
    if not row or row.revoked_at or row.expires_at <= datetime.utcnow():
        return None
    owner = db.session.get(User, row.owner_id)
    if not owner or not owner.is_active:
        return None
    if (row.company_id, row.instance_id, row.office_id) != identity():
        return None
    if (
        tuple(
            request.headers.get(k)
            for k in ["X-Company-ID", "X-Instance-ID", "X-Office-ID"]
        )
        != identity()
    ):
        return None
    return row if secrets.compare_digest(row.token_hash, digest(header[7:])) else None


@bp.route("/integrations/devices", methods=["GET", "POST"])
def manage():
    if (
        not current_user.is_authenticated
        or not current_user.is_active
        or current_user.role != "admin"
    ):
        return jsonify(error="Active administrator required"), 403
    slot = db.session.get(Office, 1)
    if slot is None:
        return jsonify(error="Pair office first"), 409
    if "hybrid_csrf" not in session:
        session["hybrid_csrf"] = secrets.token_urlsafe(32)
    bundle = None
    if request.method == "POST":
        csrf = request.form.get("csrf_token", "")
        if not csrf.isascii() or not secrets.compare_digest(
            csrf, session["hybrid_csrf"]
        ):
            return jsonify(error="CSRF validation failed"), 400
        try:
            device_id = uid(request.form.get("device_id"))
            now = datetime.utcnow().replace(microsecond=0)
            # Whole seconds survive both SQLite and MySQL DATETIME(0) exactly.
            # Serialize enrollment, rotation and revocation against the persistent office slot.
            Office.query.filter_by(id=1).with_for_update().populate_existing().one()
            row = db.session.get(Device, device_id)
            if request.form.get("action") == "revoke":
                if row:
                    row.revoked_at = now
                DeviceGrant.query.filter_by(
                    device_id=device_id, consumed_at=None, revoked_at=None
                ).update({"revoked_at": now})
                db.session.add(
                    Audit(
                        action="device_revoked",
                        reference_id=device_id,
                        actor_id=current_user.id,
                    )
                )
            elif request.form.get("action") == "issue":
                owner = db.session.get(User, int(request.form.get("owner_id", "")))
                thumb = request.form.get("key_fingerprint", "")
                if (
                    not owner
                    or not owner.is_active
                    or len(thumb) != 64
                    or any(c not in "0123456789abcdef" for c in thumb)
                ):
                    raise ValueError()
                if row and (
                    row.owner_id != owner.id or fingerprint(row.public_key) != thumb
                ):
                    raise ValueError(
                        "Owner/signing key pinned; use reviewed replacement device"
                    )
                DeviceGrant.query.filter_by(
                    device_id=device_id, consumed_at=None, revoked_at=None
                ).update({"revoked_at": now})
                raw = secrets.token_urlsafe(32)
                grant = DeviceGrant(
                    id=str(uuid4()),
                    device_id=device_id,
                    owner_id=owner.id,
                    key_fingerprint=thumb,
                    secret_hash=digest(raw),
                    expires_at=now + timedelta(minutes=10),
                )
                db.session.add(grant)
                company, instance, office = identity()
                bundle = dict(
                    schema_version=1,
                    company_id=company,
                    instance_id=instance,
                    office_id=office,
                    device_id=device_id,
                    grant_id=grant.id,
                    pairing_code=raw,
                    expires_at=utc(grant.expires_at),
                    base_url=current_app.config["GYRO_PUBLIC_BASE_URL"],
                    key_fingerprint=thumb,
                    scopes=list(SCOPES),
                )
                db.session.add(
                    Audit(
                        action="device_grant",
                        reference_id=grant.id,
                        actor_id=current_user.id,
                    )
                )
            else:
                raise ValueError()
            db.session.commit()
        except (ValueError, TypeError, IntegrityError):
            db.session.rollback()
            return jsonify(error="Invalid or conflicting device request"), 409
    return render_template(
        "field_devices.html",
        csrf=session["hybrid_csrf"],
        bundle=json.dumps(bundle) if bundle else None,
    )


@bp.post("/api/v1/devices/enroll")
def enroll():
    try:
        data = loads(request.stream.read(65537), limit=65536)
        if type(data) is not dict or set(data) != {"grant", "public_key", "proof"}:
            raise ValueError()
        grant = data["grant"]
        if (
            type(grant) is not dict
            or set(grant) != GRANT_FIELDS
            or type(grant["schema_version"]) is not int
            or grant["schema_version"] != 1
            or grant["scopes"] != SCOPES
        ):
            raise ValueError()
        if (
            tuple(uid(grant[k]) for k in ["company_id", "instance_id", "office_id"])
            != identity()
            or origin(grant["base_url"]) != current_app.config["GYRO_PUBLIC_BASE_URL"]
        ):
            raise ValueError()
        uid(grant["device_id"])
        uid(grant["grant_id"])
        if (
            not isinstance(grant["pairing_code"], str)
            or len(grant["pairing_code"]) != 43
            or not grant["pairing_code"].isascii()
        ):
            raise ValueError()
        thumb = fingerprint(data["public_key"])
        try:
            public(data["public_key"]).verify(
                un64(data["proof"], 80),
                (
                    "retail.hybrid.device.enroll.v1|"
                    + grant["grant_id"]
                    + "|"
                    + grant["pairing_code"]
                ).encode("ascii"),
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature:
            raise MobileError("Signing-key possession required") from None
        Office.query.filter_by(id=1).with_for_update().populate_existing().one()
        row = (
            DeviceGrant.query.filter_by(id=grant["grant_id"])
            .with_for_update()
            .populate_existing()
            .first()
        )
        now = datetime.utcnow()
        if (
            not row
            or row.device_id != grant["device_id"]
            or row.consumed_at
            or row.revoked_at
            or row.expires_at <= now
            or row.key_fingerprint != thumb
            or grant["key_fingerprint"] != thumb
            or grant["expires_at"] != utc(row.expires_at)
            or not secrets.compare_digest(
                row.secret_hash, digest(grant["pairing_code"])
            )
        ):
            raise ValueError()
        owner = db.session.get(User, row.owner_id)
        if not owner or not owner.is_active:
            raise ValueError()
        device = db.session.get(Device, row.device_id)
        if device and (
            device.owner_id != row.owner_id or device.public_key != data["public_key"]
        ):
            raise ValueError()
        changed = (
            DeviceGrant.query.filter_by(id=row.id, consumed_at=None, revoked_at=None)
            .filter(DeviceGrant.expires_at > now)
            .update({"consumed_at": now}, synchronize_session=False)
        )
        if changed != 1:
            raise ValueError()
        raw = secrets.token_urlsafe(32)
        if not device:
            device = Device(
                id=row.device_id,
                company_id=identity()[0],
                instance_id=identity()[1],
                office_id=identity()[2],
                owner_id=row.owner_id,
                public_key=data["public_key"],
            )
            db.session.add(device)
        device.token_hash = digest(raw)
        device.expires_at = now + timedelta(days=30)
        device.revoked_at = None
        gateway = current_app.config.get("FIELD_OFFICE_GATEWAY_URL") or os.environ.get(
            "FIELD_OFFICE_GATEWAY_URL", ""
        )
        recipient = current_app.config.get("FIELD_OFFICE_PUBLIC_KEY") or os.environ.get(
            "FIELD_OFFICE_PUBLIC_KEY", ""
        )
        if gateway:
            gateway = origin(gateway)
        if recipient:
            fingerprint(recipient)
        db.session.add(Audit(action="device_enrolled", reference_id=device.id))
        result = dict(
            schema_version=1,
            company_id=device.company_id,
            instance_id=device.instance_id,
            office_id=device.office_id,
            device_id=device.id,
            key_fingerprint=thumb,
            access_token=raw,
            expires_at=utc(device.expires_at),
            scopes=list(SCOPES),
            base_url=current_app.config["GYRO_PUBLIC_BASE_URL"],
            office_origin=gateway or None,
            office_public_key=recipient or None,
        )
        db.session.commit()
        return jsonify(result)
    except (ValueError, TypeError, KeyError, IntegrityError):
        db.session.rollback()
        return jsonify(error="Invalid, expired, consumed or revoked device grant"), 401


@bp.get("/api/v1/device/catalog/<store_id>")
def catalog(store_id):
    from catalog_bridge import CatalogHead, projection

    device = current_device("catalog:read")
    if device is None:
        return jsonify(error="Active scoped device required"), 401
    if not inspect(db.engine).has_table(CatalogHead.__tablename__):
        return jsonify(error="Initialize catalog projection"), 503
    result = projection(Transport("gyro", *identity()), store_id)
    if result:
        return current_app.response_class(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            mimetype="application/json",
        )
    return jsonify(error="Unknown scoped store"), 404


@bp.post("/api/v1/device/orders")
def submit():
    device = current_device("orders:submit")
    if device is None:
        return jsonify(error="Active scoped device required"), 401
    try:
        if not request.is_json or not inspect(db.engine).has_table(
            SubmittedOrder.__tablename__
        ):
            return jsonify(error="Initialize orders tables"), 503
        payload = verify(
            loads(request.stream.read(65537), limit=65536),
            device.public_key,
            identity(),
            device.id,
        )
        old = db.session.get(SubmittedOrder, payload["order_id"])
        if old and old.submitted_by != device.owner_id:
            raise MobileError("Business ID belongs to another submitter")
        if not inspect(db.engine).has_table(NativeDecision.__tablename__):
            return jsonify(error="Initialize device decision table explicitly"), 503
        decision = db.session.get(NativeDecision, payload["order_id"])
        if decision:
            if (
                (decision.company_id, decision.instance_id, decision.office_id)
                != identity()
                or decision.owner_id != device.owner_id
                or (decision.device_id is not None and decision.device_id != device.id)
                or decision.payload_sha256
                != hashlib.sha256(canonical(payload).encode()).hexdigest()
            ):
                raise MobileError("Decision/content/owner mismatch")
            result = decision_receipt(decision)
            db.session.commit()
            return jsonify(result)
        row = enqueue_proposal(Transport("gyro", *identity()), payload, device.owner_id)
        db.session.commit()
        return jsonify(
            schema_version=1,
            order_id=row.id,
            payload_sha256=row.payload_sha256,
            status="cloud_received",
            native_approval="unknown",
        )
    except (ValueError, TypeError, KeyError, IntegrityError):
        db.session.rollback()
        return jsonify(error="Invalid signed, stale or conflicting proposal"), 409


@bp.get("/api/v1/devices/registry")
def registry():
    if office_auth("transport:exchange") is None:
        return jsonify(error="Scoped office connector required"), 401
    now = datetime.utcnow()
    company, instance, office = identity()
    rows = (
        Device.query.filter_by(
            company_id=company, instance_id=instance, office_id=office, revoked_at=None
        )
        .filter(Device.expires_at > now)
        .all()
    )
    active = [
        row
        for row in rows
        if (
            db.session.get(User, row.owner_id)
            and db.session.get(User, row.owner_id).is_active
        )
    ]
    if len(active) > 100:
        return jsonify(error="Device registry pilot limit exceeded"), 409
    return jsonify(
        schema_version=1,
        company_id=company,
        instance_id=instance,
        office_id=office,
        generated_at=utc(now),
        devices=[
            dict(
                device_id=r.id,
                owner_id=r.owner_id,
                public_key=r.public_key,
                expires_at=utc(r.expires_at),
            )
            for r in active
        ],
    )


def register(app):
    app.register_blueprint(bp)

    @app.cli.command("init-field-devices")
    def initialize():
        for model in [Device, DeviceGrant, NativeDecision]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo("Scoped device tables ready; legacy credentials are not accepted.")


class NativeDecision(db.Model):
    """Office-authoritative terminal facts, never a cloud stock/order posting."""

    __tablename__ = "hybrid_native_device_decisions"
    order_id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)
    device_id = db.Column(db.String(36))
    payload_sha256 = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(16), nullable=False)
    native_order_id = db.Column(db.String(64))
    record_sha256 = db.Column(db.String(64), nullable=False)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def decision_receipt(decision):
    return dict(
        schema_version=1,
        order_id=decision.order_id,
        payload_sha256=decision.payload_sha256,
        status="cloud_received",
        native_approval=decision.state,
        native_order_id=decision.native_order_id,
    )


@bp.post("/api/v1/devices/decisions")
def publish_decision():
    if office_auth("transport:exchange") is None:
        return jsonify(error="Scoped authoritative office required"), 401
    if not inspect(db.engine).has_table(NativeDecision.__tablename__):
        return jsonify(error="Initialize device decision table explicitly"), 503
    try:
        if not request.is_json:
            raise MobileError("JSON required")
        data = loads(request.stream.read(16385), limit=16384)
        if type(data) is not dict or set(data) != {
            "schema_version",
            "company_id",
            "instance_id",
            "office_id",
            "order_id",
            "payload_sha256",
            "device_id",
            "state",
            "native_order_id",
        }:
            raise MobileError("Decision schema")
        if (
            type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or tuple(uid(data[k]) for k in ["company_id", "instance_id", "office_id"])
            != identity()
        ):
            raise MobileError("Decision scope")
        order_id = uid(data["order_id"])
        sha = data["payload_sha256"]
        if (
            type(sha) is not str
            or len(sha) != 64
            or any(ch not in "0123456789abcdef" for ch in sha)
        ):
            raise MobileError("Content hash")
        if data["state"] == "approved":
            uid(data["native_order_id"])
        elif data["state"] != "rejected" or data["native_order_id"] is not None:
            raise MobileError("Terminal decision required")
        # Persistent office slot serializes first receipt and conflicting retries on MySQL.
        Office.query.filter_by(id=1).with_for_update().populate_existing().one()
        submitted = (
            SubmittedOrder.query.filter_by(id=order_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if submitted and (
            (submitted.company_id, submitted.instance_id, submitted.office_id)
            != identity()
            or submitted.payload_sha256 != sha
        ):
            raise MobileError("Submitted order conflict")
        if data["device_id"] is not None:
            device = db.session.get(Device, uid(data["device_id"]))
            if (
                not device
                or (device.company_id, device.instance_id, device.office_id)
                != identity()
            ):
                raise MobileError("Device scope")
            owner_id = device.owner_id
            if submitted and submitted.submitted_by != owner_id:
                raise MobileError("Owner conflict")
        else:
            if not submitted:
                raise MobileError("Offline-first decision requires device identity")
            owner_id = submitted.submitted_by
        record_sha = hashlib.sha256(canonical(data).encode()).hexdigest()
        previous = (
            NativeDecision.query.filter_by(order_id=order_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if previous:
            if previous.record_sha256 != record_sha:
                raise MobileError("Immutable decision conflict")
        else:
            db.session.add(
                NativeDecision(
                    order_id=order_id,
                    company_id=identity()[0],
                    instance_id=identity()[1],
                    office_id=identity()[2],
                    owner_id=owner_id,
                    device_id=data["device_id"],
                    payload_sha256=sha,
                    state=data["state"],
                    native_order_id=data["native_order_id"],
                    record_sha256=record_sha,
                )
            )
            db.session.add(
                Audit(action="native_device_decision", reference_id=order_id)
            )
        db.session.commit()
        return jsonify(
            schema_version=1,
            order_id=order_id,
            record_sha256=record_sha,
            status="decision_received",
        )
    except (ValueError, TypeError, KeyError, IntegrityError):
        db.session.rollback()
        return jsonify(error="Invalid/conflicting native decision"), 409
