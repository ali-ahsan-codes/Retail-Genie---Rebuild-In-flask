"""Explicit registry refresh, authenticated encrypted file/LAN ingress, never auto approval."""

import hashlib, os
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
import click
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import inspect
from .extensions import db, csrf
from .field_integration import FieldConnection, cipher, trusted_origins
from .field_transport import cloud_request
from .integration_contract import origin, uid, loads
from .mobile_crypto import decrypt_parcel, peek_device, verify, fingerprint, MobileError
from .field_orders import stage_message
from .sync_core import Transport

bp = Blueprint("mobile_gateway", __name__)


def parse_utc(value):
    if type(value) is not str or len(value) > 40 or not value.endswith("Z"):
        raise MobileError("UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise MobileError("UTC timestamp required") from None


class DeviceRegistry(db.Model):
    __tablename__ = "hybrid_office_device_registry"
    company_id = db.Column(db.String(36), primary_key=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    devices = db.Column(db.JSON, nullable=False)
    refreshed_at = db.Column(db.DateTime, nullable=False)
    valid_until = db.Column(db.DateTime, nullable=False)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class DeviceIngress(db.Model):
    __tablename__ = "hybrid_device_ingress"
    company_id = db.Column(db.String(36), primary_key=True)
    order_id = db.Column(db.String(36), primary_key=True)
    device_id = db.Column(db.String(36), nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)
    message_id = db.Column(db.String(36), nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def store_registry(connection, data, max_age_minutes=15):
    if type(max_age_minutes) is not int or not 1 <= max_age_minutes <= 1440:
        raise MobileError("Explicit freshness limit required")
    now = datetime.utcnow()
    if (
        type(data) is not dict
        or set(data)
        != {
            "schema_version",
            "company_id",
            "instance_id",
            "office_id",
            "generated_at",
            "devices",
        }
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise MobileError("Invalid registry schema")
    expected = (connection.company_id, connection.instance_id, connection.office_id)
    if (
        tuple(uid(data[k]) for k in ["company_id", "instance_id", "office_id"])
        != expected
    ):
        raise MobileError("Registry identity mismatch")
    if abs((parse_utc(data["generated_at"]) - now).total_seconds()) > 60:
        raise MobileError("Registry clock/staleness mismatch")
    devices = data["devices"]
    if type(devices) is not list or len(devices) > 100:
        raise MobileError("Bounded registry required")
    seen = set()
    for device in devices:
        if type(device) is not dict or set(device) != {
            "device_id",
            "owner_id",
            "public_key",
            "expires_at",
        }:
            raise MobileError("Invalid registry device")
        ident = uid(device["device_id"])
        if (
            ident in seen
            or type(device["owner_id"]) is not int
            or device["owner_id"] <= 0
        ):
            raise MobileError("Invalid registry identity")
        seen.add(ident)
        fingerprint(device["public_key"])
        parse_utc(device["expires_at"])
    row = db.session.get(DeviceRegistry, connection.company_id)
    if row and (row.instance_id, row.office_id) != expected[1:]:
        raise MobileError("Registry pin mismatch")
    if not row:
        row = DeviceRegistry(
            company_id=expected[0], instance_id=expected[1], office_id=expected[2]
        )
        db.session.add(row)
    row.devices = devices
    row.refreshed_at = now
    row.valid_until = now + timedelta(minutes=max_age_minutes)
    db.session.flush()
    return row


def refresh_registry(company_id, max_age_minutes=15):
    connection = db.session.get(FieldConnection, uid(company_id))
    if (
        not connection
        or not connection.instance_id
        or not connection.credential_encrypted
    ):
        raise MobileError("Pair office first")
    base = origin(connection.base_url)
    if base not in trusted_origins():
        raise MobileError("Cloud origin not trusted")
    headers = {
        "Authorization": "Bearer "
        + cipher().decrypt(connection.credential_encrypted.encode()).decode("ascii"),
        "X-Company-ID": connection.company_id,
        "X-Instance-ID": connection.instance_id,
        "X-Office-ID": connection.office_id,
    }
    identity = (connection.company_id, connection.instance_id, connection.office_id)
    db.session.commit()
    data = cloud_request(base, "/api/v1/devices/registry", headers)
    current = db.session.get(FieldConnection, company_id)
    if (
        not current
        or (current.company_id, current.instance_id, current.office_id) != identity
    ):
        raise MobileError("Office changed during refresh")
    return store_registry(current, data, max_age_minutes)


def accept_parcel(company_id, parcel):
    connection = db.session.get(FieldConnection, uid(company_id))
    if not connection or not connection.instance_id:
        raise MobileError("Paired office required")
    identity = (connection.company_id, connection.instance_id, connection.office_id)
    registry = db.session.get(DeviceRegistry, company_id)
    now = datetime.utcnow()
    if (
        not registry
        or registry.valid_until <= now
        or (registry.instance_id, registry.office_id) != identity[1:]
    ):
        raise MobileError("Refresh device registry before offline ingress")
    key = current_app.config.get("FIELD_OFFICE_PRIVATE_KEY_BASE64") or os.environ.get(
        "FIELD_OFFICE_PRIVATE_KEY_BASE64", ""
    )
    if not key:
        raise MobileError(
            "Office recipient private key required; no plaintext fallback"
        )
    wire = decrypt_parcel(parcel, key, identity)
    device_id = peek_device(wire)
    device = next(
        (row for row in registry.devices if row["device_id"] == device_id), None
    )
    if not device or parse_utc(device["expires_at"]) <= now:
        raise MobileError("Unknown/revoked/expired cached device")
    order = verify(wire, device["public_key"], identity, device_id)
    previous = db.session.get(DeviceIngress, (company_id, order["order_id"]))
    if previous and previous.owner_id != device["owner_id"]:
        raise MobileError("Business ID belongs to another owner")
    message_id = str(
        uuid5(
            NAMESPACE_URL,
            "retail.hybrid.device.order.v1:" + company_id + ":" + order["order_id"],
        )
    )
    # Same deterministic transport ID for repeated LAN/file deliveries. Cloud transport may
    # use another ID; Phase 5 business-ID dedup still produces one native proposal/sale.
    sender = Transport("gyro", *identity)
    receiver = Transport("retail", *identity)
    receiver.accept(sender.envelope("field.order", order, message_id=message_id))
    proposal = stage_message(company_id, message_id)
    if not previous:
        db.session.add(
            DeviceIngress(
                company_id=company_id,
                order_id=order["order_id"],
                device_id=device_id,
                owner_id=device["owner_id"],
                message_id=message_id,
            )
        )
    db.session.flush()
    return dict(
        schema_version=1,
        order_id=proposal.id,
        status="office_received_unconfirmed",
        native_approval="unknown",
    )


@bp.post("/api/v1/field-device/orders")
@csrf.exempt
def receive_lan():
    # Only signed+encrypted parcels, not cookies or bearer auth. Explicit opt-in, no discovery.
    if current_app.config.get("FIELD_LAN_INGRESS_ENABLED") is not True:
        return jsonify(error="LAN ingress disabled"), 404
    if request.headers.get("Authorization") or request.headers.get("Cookie"):
        return jsonify(error="No cloud/session credentials accepted on LAN"), 400
    if not request.is_json:
        return jsonify(error="Encrypted JSON parcel required"), 400
    try:
        parcel = loads(request.stream.read(65537), limit=65536)
        result = accept_parcel(parcel["company_id"], parcel)
        db.session.commit()
        return jsonify(result)
    except Exception:
        db.session.rollback()
        return (
            jsonify(
                error="Parcel rejected; refresh registry/check scope/key/signature. No native posting performed."
            ),
            409,
        )


def register(app):
    app.config.setdefault(
        "FIELD_LAN_INGRESS_ENABLED",
        os.environ.get("FIELD_LAN_INGRESS_ENABLED", "false").lower() == "true",
    )
    app.register_blueprint(bp)

    @app.cli.command("init-office-mobile")
    def initialize():
        for model in [DeviceRegistry, DeviceIngress, DecisionDelivery]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Office registry/ingress tables ready. LAN remains opt-in; no auto approval."
        )

    @app.cli.command("field-device-registry-refresh")
    @click.option("--company-id", required=True)
    @click.option("--max-age-minutes", default=15, type=click.IntRange(1, 1440))
    def refresh(company_id, max_age_minutes):
        try:
            refresh_registry(company_id, max_age_minutes)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Registry refresh failed; no untrusted registry imported."
            ) from None
        click.echo(
            "Registry refreshed. Offline revocation delay bounded by configured freshness window."
        )

    @app.cli.command("field-device-decisions-push")
    @click.option("--company-id", required=True)
    @click.option("--limit", default=100, type=click.IntRange(1, 100))
    def push_decisions(company_id, limit):
        import json

        try:
            result = publish_decisions(company_id, limit)
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Decision transfer failed; native decisions retained. Retry safely."
            ) from None
        click.echo(json.dumps(result))

    @app.cli.command("field-device-import")
    @click.option("--company-id", required=True)
    @click.argument("parcel_file", type=click.File("rb"))
    def file_import(company_id, parcel_file):
        try:
            accept_parcel(company_id, loads(parcel_file.read(65537), limit=65536))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Encrypted parcel rejected; inbox/proposal transaction rolled back."
            ) from None
        click.echo(
            "Parcel staged for human review. Not approved; do not discard device order."
        )


class DecisionDelivery(db.Model):
    __tablename__ = "hybrid_device_decision_delivery"
    company_id = db.Column(db.String(36), primary_key=True)
    order_id = db.Column(db.String(36), primary_key=True)
    record_sha256 = db.Column(db.String(64), nullable=False)
    record = db.Column(db.JSON, nullable=False)
    acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def decision_record(company_id, proposal_id):
    from .field_orders import FieldProposal, FieldReviewAudit
    from .models import SalesOrder
    from .sync_core import canonical

    proposal = db.session.get(FieldProposal, (company_id, proposal_id))
    if proposal is None or proposal.state not in {"approved", "rejected"}:
        raise MobileError("Terminal native decision required")
    context = Transport("retail", company_id, proposal.instance_id, proposal.office_id)
    current = db.session.get(FieldConnection, company_id)
    if not current or (current.instance_id, current.office_id) != context.identity[1:]:
        raise MobileError("Office binding changed")
    if (
        hashlib.sha256(canonical(proposal.payload).encode()).hexdigest()
        != proposal.payload_sha256
    ):
        raise MobileError("Immutable content mismatch")
    audits = FieldReviewAudit.query.filter_by(
        company_id=company_id, proposal_id=proposal_id
    ).all()
    if (
        len(audits) != 1
        or audits[0].action != proposal.state
        or audits[0].native_order_id != proposal.native_order_id
    ):
        raise MobileError("Decision audit mismatch")
    if proposal.state == "approved":
        order = db.session.get(SalesOrder, proposal.native_order_id)
        if not order or (order.company_id, order.origin_store_id) != (
            company_id,
            proposal.store_id,
        ):
            raise MobileError("Native order mapping broken")
    elif proposal.native_order_id is not None:
        raise MobileError("Rejected proposal has native order")
    ingress = db.session.get(DeviceIngress, (company_id, proposal_id))
    return dict(
        schema_version=1,
        company_id=company_id,
        instance_id=proposal.instance_id,
        office_id=proposal.office_id,
        order_id=proposal.id,
        payload_sha256=proposal.payload_sha256,
        device_id=ingress.device_id if ingress else None,
        state=proposal.state,
        native_order_id=proposal.native_order_id,
    )


def publish_decisions(company_id, limit=100):
    from .field_orders import FieldProposal
    from .sync_core import canonical

    if type(limit) is not int or not 1 <= limit <= 100:
        raise MobileError("Invalid limit")
    connection = db.session.get(FieldConnection, uid(company_id))
    if not connection or not connection.credential_encrypted:
        raise MobileError("Pair office first")
    base = origin(connection.base_url)
    if base not in trusted_origins():
        raise MobileError("Untrusted cloud origin")
    binding = (
        connection.instance_id,
        connection.office_id,
        connection.base_url,
        connection.credential_encrypted,
    )
    headers = {
        "Authorization": "Bearer "
        + cipher().decrypt(connection.credential_encrypted.encode()).decode("ascii"),
        "X-Company-ID": company_id,
        "X-Instance-ID": binding[0],
        "X-Office-ID": binding[1],
    }
    rows = (
        FieldProposal.query.outerjoin(
            DecisionDelivery,
            (DecisionDelivery.company_id == FieldProposal.company_id)
            & (DecisionDelivery.order_id == FieldProposal.id),
        )
        .filter(
            FieldProposal.company_id == company_id,
            FieldProposal.state.in_(["approved", "rejected"]),
            (
                DecisionDelivery.order_id.is_(None)
                | (DecisionDelivery.acknowledged == False)
            ),
        )
        .order_by(FieldProposal.created_at, FieldProposal.id)
        .limit(limit)
        .all()
    )
    # Freeze provenance before network I/O; later file duplicates cannot change a lost-ACK retry.
    FieldConnection.query.filter_by(
        company_id=company_id
    ).with_for_update().populate_existing().one()
    records = []
    for row in rows:
        current_record = decision_record(company_id, row.id)
        pending = (
            DecisionDelivery.query.filter_by(company_id=company_id, order_id=row.id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if pending is None:
            pending = DecisionDelivery(
                company_id=company_id,
                order_id=row.id,
                record=current_record,
                record_sha256=hashlib.sha256(
                    canonical(current_record).encode()
                ).hexdigest(),
                acknowledged=False,
            )
            db.session.add(pending)
        if not pending.acknowledged:
            records.append(dict(pending.record))
    db.session.commit()
    count = 0
    for record in records:
        sha = hashlib.sha256(canonical(record).encode()).hexdigest()
        receipt = cloud_request(base, "/api/v1/devices/decisions", headers, record)
        if receipt != dict(
            schema_version=1,
            order_id=record["order_id"],
            record_sha256=sha,
            status="decision_received",
        ):
            raise MobileError("Decision acknowledgement mismatch")
        current = db.session.get(FieldConnection, company_id)
        if (
            not current
            or (
                current.instance_id,
                current.office_id,
                current.base_url,
                current.credential_encrypted,
            )
            != binding
        ):
            raise MobileError("Binding changed during transfer")
        observed = decision_record(company_id, record["order_id"])
        if any(observed[k] != record[k] for k in record if k != "device_id") or (
            record["device_id"] is not None
            and observed["device_id"] != record["device_id"]
        ):
            raise MobileError("Decision changed during transfer")
        # Serialize concurrent publishers only AFTER network I/O. Lost ACK repeats the immutable fact.
        FieldConnection.query.filter_by(
            company_id=company_id
        ).with_for_update().populate_existing().one()
        old = (
            DecisionDelivery.query.filter_by(
                company_id=company_id, order_id=record["order_id"]
            )
            .with_for_update()
            .populate_existing()
            .first()
        )
        if old and old.record_sha256 != sha:
            raise MobileError("Conflicting delivery")
        if not old or old.record != record:
            raise MobileError("Durable decision missing/changed")
        if (
            current.instance_id,
            current.office_id,
            current.base_url,
            current.credential_encrypted,
        ) != binding:
            raise MobileError("Binding changed during acknowledgement")
        old.acknowledged = True
        db.session.commit()
        count += 1
    return dict(decisions_acknowledged=count, automatic_posting=False)
