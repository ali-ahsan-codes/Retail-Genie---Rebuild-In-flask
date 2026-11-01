"""One-office pairing/rotation/revocation; commits receipt only after durable exchange.
Bearer and grant secrets have 256-bit entropy, are returned once and stored hashed only.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from uuid import uuid4
import click
from flask import Blueprint, current_app, jsonify, render_template, request, session
from flask_login import current_user
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from models import db
from integration_contract import uid, origin, SCOPES, BUNDLE_FIELDS, valid_scopes, loads

bp = Blueprint("integration", __name__)


def digest(value):
    return hashlib.sha256(("retail.hybrid.credential.v1:" + value).encode()).hexdigest()


class Office(db.Model):
    __tablename__ = "hybrid_integration_office"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False, unique=True)
    current_credential_id = db.Column(db.String(36))
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Grant(db.Model):
    __tablename__ = "hybrid_pairing_grants"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    secret_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Credential(db.Model):
    __tablename__ = "hybrid_integration_credentials"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    secret_hash = db.Column(db.String(64), nullable=False)
    scopes = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Audit(db.Model):
    __tablename__ = "hybrid_integration_audit"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(30), nullable=False)
    reference_id = db.Column(db.String(36), nullable=False)
    actor_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


@bp.before_request
def only_dedicated():
    if current_app.config["GYRO_DEPLOYMENT_MODE"] != "dedicated":
        return jsonify(error="Dedicated configuration required"), 409
    if request.content_length and request.content_length > (
        131072
        if request.endpoint in {"integration.sync_receive", "integration.sync_ack"}
        else 16384
    ):
        return jsonify(error="Request too large"), 413
    if not all(
        inspect(db.engine).has_table(model.__tablename__)
        for model in [Office, Grant, Credential, Audit]
    ):
        return jsonify(error="Operator must initialize pairing tables"), 503


@bp.after_request
def private(response):
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        }
    )
    return response


def office_lock():
    return Office.query.filter_by(id=1).with_for_update().populate_existing().first()


@bp.route("/integrations", methods=["GET", "POST"])
def manage():
    if (
        not current_user.is_authenticated
        or not current_user.is_active
        or current_user.role != "admin"
    ):
        return jsonify(error="Active administrator required"), 403
    if "hybrid_csrf" not in session:
        session["hybrid_csrf"] = secrets.token_urlsafe(32)
    bundle = None
    message = None
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        if not supplied.isascii() or not secrets.compare_digest(
            supplied, session["hybrid_csrf"]
        ):
            return jsonify(error="CSRF validation failed"), 400
        try:
            company = current_app.config["GYRO_COMPANY_ID"]
            slot = office_lock()
            if request.form.get("action") == "issue":
                office_id = uid(request.form.get("office_id"))
                if slot and (slot.office_id != office_id or slot.company_id != company):
                    raise ValueError("Office identity is pinned; migration required")
                if not slot:
                    slot = Office(id=1, company_id=company, office_id=office_id)
                    db.session.add(slot)
                    db.session.flush()
                # Grant bundle is built before commit: avoid MySQL DATETIME(0)
                # rounding away fractional seconds and invalidating the exact expiry check.
                now = datetime.utcnow().replace(microsecond=0)
                Grant.query.filter_by(
                    company_id=company,
                    office_id=office_id,
                    consumed_at=None,
                    revoked_at=None,
                ).update({"revoked_at": now})
                raw = secrets.token_urlsafe(32)
                grant = Grant(
                    id=str(uuid4()),
                    company_id=company,
                    instance_id=current_app.config["GYRO_INSTANCE_ID"],
                    office_id=office_id,
                    secret_hash=digest(raw),
                    expires_at=now + timedelta(minutes=10),
                )
                db.session.add(grant)
                db.session.add(
                    Audit(
                        action="grant_issued",
                        reference_id=grant.id,
                        actor_id=current_user.id,
                    )
                )
                bundle = dict(
                    schema_version=1,
                    company_id=company,
                    instance_id=grant.instance_id,
                    office_id=office_id,
                    base_url=current_app.config["GYRO_PUBLIC_BASE_URL"],
                    grant_id=grant.id,
                    pairing_code=raw,
                    expires_at=grant.expires_at.isoformat() + "Z",
                    scopes=list(SCOPES),
                )
            elif request.form.get("action") in {
                "transport_enable",
                "transport_disable",
            }:
                row = (
                    db.session.get(Credential, slot.current_credential_id)
                    if slot and slot.current_credential_id
                    else None
                )
                if not row or row.revoked_at or row.expires_at <= datetime.utcnow():
                    raise ValueError("Pair an active office first")
                enabled = request.form["action"] == "transport_enable"
                row.scopes = list(SCOPES) + (["transport:exchange"] if enabled else [])
                db.session.add(
                    Audit(
                        action="transport_enabled" if enabled else "transport_disabled",
                        reference_id=row.id,
                        actor_id=current_user.id,
                    )
                )
                message = "Delivery-only permission updated. This never grants business approval."
            elif request.form.get("action") == "revoke":
                if not slot:
                    raise ValueError("No paired office")
                now = datetime.utcnow()
                Grant.query.filter_by(
                    company_id=company,
                    office_id=slot.office_id,
                    consumed_at=None,
                    revoked_at=None,
                ).update({"revoked_at": now})
                Credential.query.filter_by(
                    company_id=company, office_id=slot.office_id, revoked_at=None
                ).update({"revoked_at": now})
                slot.current_credential_id = None
                db.session.add(
                    Audit(
                        action="office_revoked",
                        reference_id=slot.office_id,
                        actor_id=current_user.id,
                    )
                )
                message = "Office credentials and outstanding grants revoked."
            else:
                raise ValueError("Unknown action")
            db.session.commit()
        except (ValueError, TypeError):
            db.session.rollback()
            return jsonify(error="Invalid request or pinned office conflict"), 400
        except IntegrityError:
            db.session.rollback()
            return (
                jsonify(error="Concurrent pairing change; retry same office identity"),
                503,
            )
    slot = db.session.get(Office, 1)
    return render_template(
        "hybrid_integrations.html",
        csrf=session["hybrid_csrf"],
        office=slot,
        bundle=json.dumps(bundle, sort_keys=True) if bundle else None,
        message=message,
    )


@bp.post("/api/v1/pairing/exchange")
def exchange():
    try:
        if not request.is_json:
            raise ValueError()
        data = loads(request.stream.read(16385))
        if (
            not isinstance(data, dict)
            or set(data) != BUNDLE_FIELDS
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["scopes"] != SCOPES
        ):
            raise ValueError()
        for key in ["company_id", "instance_id", "office_id", "grant_id"]:
            uid(data[key])
        if (data["company_id"], data["instance_id"], origin(data["base_url"])) != (
            current_app.config["GYRO_COMPANY_ID"],
            current_app.config["GYRO_INSTANCE_ID"],
            current_app.config["GYRO_PUBLIC_BASE_URL"],
        ):
            raise ValueError()
        if (
            not isinstance(data["pairing_code"], str)
            or len(data["pairing_code"]) != 43
            or not data["pairing_code"].isascii()
        ):
            raise ValueError()
        slot = office_lock()
        grant = (
            Grant.query.filter_by(id=data["grant_id"])
            .with_for_update()
            .populate_existing()
            .first()
        )
        now = datetime.utcnow()
        if (
            not slot
            or slot.office_id != data["office_id"]
            or not grant
            or (grant.company_id, grant.instance_id, grant.office_id)
            != (data["company_id"], data["instance_id"], data["office_id"])
        ):
            raise ValueError()
        if (
            grant.consumed_at
            or grant.revoked_at
            or grant.expires_at <= now
            or data["expires_at"] != grant.expires_at.isoformat() + "Z"
            or not secrets.compare_digest(
                grant.secret_hash, digest(data["pairing_code"])
            )
        ):
            raise ValueError()
        # Conditional consume is a second replay fence, including databases without row locks.
        consumed = Grant.query.filter(
            Grant.id == grant.id,
            Grant.consumed_at.is_(None),
            Grant.revoked_at.is_(None),
            Grant.expires_at > now,
        ).update({"consumed_at": now}, synchronize_session=False)
        if consumed != 1:
            raise ValueError()
        if slot.current_credential_id:
            old = db.session.get(Credential, slot.current_credential_id)
            if old:
                old.revoked_at = now
        raw = secrets.token_urlsafe(32)
        row = Credential(
            id=str(uuid4()),
            company_id=grant.company_id,
            instance_id=grant.instance_id,
            office_id=grant.office_id,
            secret_hash=digest(raw),
            scopes=list(SCOPES),
            expires_at=now + timedelta(days=30),
        )
        db.session.add(row)
        grant.consumed_at = now
        slot.current_credential_id = row.id
        db.session.add(Audit(action="grant_exchanged", reference_id=grant.id))
        result = dict(
            schema_version=1,
            company_id=row.company_id,
            instance_id=row.instance_id,
            office_id=row.office_id,
            credential_id=row.id,
            access_token=raw,
            expires_at=row.expires_at.isoformat() + "Z",
            scopes=list(SCOPES),
        )
        db.session.commit()
        return jsonify(result)
    except (ValueError, TypeError, KeyError):
        db.session.rollback()
        return jsonify(error="Invalid, expired, revoked or consumed pairing grant"), 401
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(error="Concurrent exchange; retry same grant or issue replacement"),
            503,
        )


def authenticate(scope):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or len(header) != 50:
        return None
    slot = db.session.get(Office, 1)
    row = (
        db.session.get(Credential, slot.current_credential_id)
        if slot and slot.current_credential_id
        else None
    )
    if (
        not row
        or row.revoked_at
        or row.expires_at <= datetime.utcnow()
        or not valid_scopes(row.scopes)
        or scope not in row.scopes
    ):
        return None
    if (row.company_id, row.instance_id, row.office_id) != (
        current_app.config["GYRO_COMPANY_ID"],
        current_app.config["GYRO_INSTANCE_ID"],
        slot.office_id,
    ):
        return None
    if (
        request.headers.get("X-Company-ID"),
        request.headers.get("X-Instance-ID"),
        request.headers.get("X-Office-ID"),
    ) != (row.company_id, row.instance_id, row.office_id):
        return None
    return row if secrets.compare_digest(row.secret_hash, digest(header[7:])) else None


@bp.get("/api/v1/integration/status")
def status():
    row = authenticate("connection:read")
    if not row:
        return jsonify(error="Active scoped office bearer required"), 401
    return jsonify(
        schema_version=1,
        company_id=row.company_id,
        instance_id=row.instance_id,
        office_id=row.office_id,
        credential_id=row.id,
        scopes=row.scopes,
        expires_at=row.expires_at.isoformat() + "Z",
        status="connected",
        inventory_authority="retail-genie",
        business_sync_enabled=False,
    )


def transport_context():
    from sync_core import Transport, Inbox, Outbox

    row = authenticate("transport:exchange")
    if not row:
        return None, (
            jsonify(error="Explicit active transport permission required"),
            401,
        )
    if not all(
        inspect(db.engine).has_table(model.__tablename__) for model in [Inbox, Outbox]
    ):
        return None, (jsonify(error="Operator must initialize transport tables"), 503)
    return Transport("gyro", row.company_id, row.instance_id, row.office_id), None


@bp.post("/api/v1/sync/messages")
def sync_receive():
    from sync_core import decode, ProtocolError

    context, error = transport_context()
    if error:
        return error
    try:
        if not request.is_json:
            raise ProtocolError("JSON required")
        receipt = context.accept(decode(request.stream.read(131073)))
        db.session.commit()  # Durable receipt, NOT native approval or catalog application.
        return jsonify(receipt)
    except ProtocolError:
        db.session.rollback()
        return jsonify(error="Invalid/conflicting envelope"), 409


@bp.get("/api/v1/sync/pull")
def sync_pull():
    context, error = transport_context()
    if error:
        return error
    jobs = context.claim(limit=1, lease_seconds=300)
    db.session.commit()
    if not jobs:
        return jsonify(message=None)
    message_id, token, envelope = jobs[0]
    # Bound envelope + a small fixed wrapper; do not inflate UTF-8 payloads with ASCII escapes.
    return current_app.response_class(
        json.dumps(
            dict(
                message=dict(
                    message_id=message_id, lease_token=token, envelope=envelope
                )
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        mimetype="application/json",
    )


@bp.post("/api/v1/sync/ack")
def sync_ack():
    from sync_core import decode, ProtocolError

    context, error = transport_context()
    if error:
        return error
    try:
        if not request.is_json:
            raise ProtocolError("JSON required")
        data = decode(request.stream.read(131073))
        if type(data) is not dict or set(data) != {
            "message_id",
            "lease_token",
            "receipt",
        }:
            raise ProtocolError("Invalid receipt")
        context.acknowledge(data["message_id"], data["lease_token"], data["receipt"])
        db.session.commit()
        return jsonify(status="acknowledged")
    except ProtocolError:
        db.session.rollback()
        return jsonify(error="Invalid receipt or stale lease"), 409


@bp.get("/api/v1/catalog/snapshot/<store_id>")
def catalog_snapshot(store_id):
    from catalog_bridge import CatalogHead, CatalogApplication, projection

    context, error = transport_context()
    if error:
        return error
    if not all(
        inspect(db.engine).has_table(model.__tablename__)
        for model in [CatalogHead, CatalogApplication]
    ):
        return jsonify(error="Operator must initialize catalog projection tables"), 503
    result = projection(context, store_id)
    if result is None:
        return jsonify(error="No scoped store snapshot"), 404
    return jsonify(result)


@bp.route("/integrations/orders", methods=["GET", "POST"])
def orders_manage():
    from catalog_bridge import CatalogHead
    from field_orders import SubmittedOrder, enqueue_proposal
    from order_contract import OrderError
    from sync_core import Transport, ProtocolError

    if (
        not current_user.is_authenticated
        or not current_user.is_active
        or current_user.role != "admin"
    ):
        return jsonify(error="Active cloud administrator required"), 403
    if not all(
        inspect(db.engine).has_table(model.__tablename__)
        for model in [CatalogHead, SubmittedOrder]
    ):
        return jsonify(error="Operator must initialize catalog/order tables"), 503
    slot = db.session.get(Office, 1)
    if slot is None:
        return jsonify(error="Pair native office first"), 409
    context = Transport(
        "gyro",
        current_app.config["GYRO_COMPANY_ID"],
        current_app.config["GYRO_INSTANCE_ID"],
        slot.office_id,
    )
    if "hybrid_csrf" not in session:
        session["hybrid_csrf"] = secrets.token_urlsafe(32)
    message = None
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        if not supplied.isascii() or not secrets.compare_digest(
            supplied, session["hybrid_csrf"]
        ):
            return jsonify(error="CSRF validation failed"), 400
        try:
            payload = loads(request.form.get("proposal", ""))
            row = enqueue_proposal(context, payload, current_user.id)
            db.session.commit()
            message = (
                "Submitted "
                + row.id
                + ". Delivery only; native human approval is still required."
            )
        except (OrderError, ProtocolError, ValueError, IntegrityError):
            db.session.rollback()
            return (
                jsonify(
                    error="Proposal rejected. Check immutable business ID, current catalog, product, price and schema."
                ),
                409,
            )
    heads = (
        CatalogHead.query.filter_by(
            company_id=context.identity[0],
            instance_id=context.identity[1],
            office_id=context.identity[2],
        )
        .order_by(CatalogHead.store_id)
        .limit(20)
        .all()
    )
    return render_template(
        "field_order_submit.html",
        csrf=session["hybrid_csrf"],
        heads=heads,
        message=message,
    )


def register(app):
    app.register_blueprint(bp)

    @app.cli.command("init-field-pairing")
    def initialize():
        for model in [Office, Grant, Credential, Audit]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Additive pairing tables ready; no grants or business sync automatically enabled."
        )
