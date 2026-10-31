"""Native office enrollment. No business writers, LAN discovery, retries or sync workers.
Trusted HTTPS destinations are deployment configuration, never pairing-bundle authority.
"""

import json
import os
import ssl
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import (
    Request,
    build_opener,
    HTTPSHandler,
    HTTPRedirectHandler,
    ProxyHandler,
)
from uuid import uuid4
import click
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .integration_contract import (
    uid,
    origin,
    SCOPES,
    BUNDLE_FIELDS,
    valid_scopes,
    loads,
)

bp = Blueprint("field_integration", __name__)
RESPONSE_FIELDS = {
    "schema_version",
    "company_id",
    "instance_id",
    "office_id",
    "credential_id",
    "access_token",
    "expires_at",
    "scopes",
}


class FieldConnection(db.Model):
    __tablename__ = "hybrid_field_connections"
    company_id = db.Column(db.String(64), primary_key=True)
    office_id = db.Column(db.String(36), nullable=False, unique=True)
    instance_id = db.Column(db.String(36))
    base_url = db.Column(db.String(300))
    credential_id = db.Column(db.String(36))
    credential_encrypted = db.Column(db.Text)
    expires_at = db.Column(db.String(40))
    scopes = db.Column(db.JSON)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class FieldIntegrationAudit(db.Model):
    __tablename__ = "hybrid_field_integration_audit"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.String(64), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    credential_id = db.Column(db.String(36))
    actor_id = db.Column(db.String(64))
    action = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def cipher():
    key = current_app.config.get("FIELD_INTEGRATION_KEY") or os.environ.get(
        "FIELD_INTEGRATION_KEY", ""
    )
    if not isinstance(key, str) or not key:
        raise ValueError("Dedicated encryption key required")
    return Fernet(key.encode("ascii"))


def trusted_origins():
    value = current_app.config.get("FIELD_GYRO_ALLOWED_ORIGINS") or os.environ.get(
        "FIELD_GYRO_ALLOWED_ORIGINS", ""
    )
    if not isinstance(value, str):
        raise ValueError("Configured HTTPS origin allowlist required")
    return {origin(item.strip()) for item in value.split(",") if item.strip()}


def exchange_http(base, bundle):
    # Ignore proxy environment and redirects: credentials must reach this exact TLS origin only.
    opener = build_opener(
        ProxyHandler({}),
        NoRedirect(),
        HTTPSHandler(context=ssl.create_default_context()),
    )
    req = Request(
        base + "/api/v1/pairing/exchange",
        data=json.dumps(bundle).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with opener.open(req, timeout=10) as response:
        if (
            response.status != 200
            or response.headers.get_content_type() != "application/json"
        ):
            raise ValueError("Invalid exchange response")
        return loads(response.read(16385))


def enroll(connection, bundle, actor_id=None):
    encryption = (
        cipher()
    )  # fail BEFORE sending a consumable grant if local key is unavailable
    if (
        not isinstance(bundle, dict)
        or set(bundle) != BUNDLE_FIELDS
        or type(bundle["schema_version"]) is not int
        or bundle["schema_version"] != 1
        or bundle["scopes"] != SCOPES
    ):
        raise ValueError("Unsupported pairing contract")
    for name in ["company_id", "instance_id", "office_id", "grant_id"]:
        uid(bundle[name])
    base = origin(bundle["base_url"])
    if base not in trusted_origins():
        raise ValueError("Cloud origin not explicitly trusted")
    if (bundle["company_id"], bundle["office_id"]) != (
        connection.company_id,
        connection.office_id,
    ):
        raise ValueError("Company or office mismatch")
    if connection.instance_id and (connection.instance_id, connection.base_url) != (
        bundle["instance_id"],
        base,
    ):
        raise ValueError("Existing cloud binding cannot be reassigned")
    raw = bundle["pairing_code"]
    if not isinstance(raw, str) or len(raw) != 43 or not raw.isascii():
        raise ValueError("Invalid grant")
    company_id = connection.company_id
    office_id = connection.office_id
    db.session.commit()  # release read transaction; no DB lock while waiting on network
    response = exchange_http(base, bundle)
    if (
        not isinstance(response, dict)
        or set(response) != RESPONSE_FIELDS
        or type(response["schema_version"]) is not int
        or response["schema_version"] != 1
        or response["scopes"] != SCOPES
    ):
        raise ValueError("Invalid credential response")
    if (response["company_id"], response["instance_id"], response["office_id"]) != (
        company_id,
        bundle["instance_id"],
        office_id,
    ):
        raise ValueError("Credential identity mismatch")
    uid(response["credential_id"])
    token = response["access_token"]
    if not isinstance(token, str) or len(token) != 43 or not token.isascii():
        raise ValueError("Invalid credential response")
    expiry = response["expires_at"]
    if not isinstance(expiry, str) or not expiry.endswith("Z"):
        raise ValueError("Invalid credential expiry")
    parsed = datetime.fromisoformat(expiry[:-1] + "+00:00")
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("Expired credential")
    locked = (
        FieldConnection.query.filter_by(company_id=company_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if (
        not locked
        or locked.office_id != office_id
        or (
            locked.instance_id
            and (locked.instance_id, locked.base_url) != (response["instance_id"], base)
        )
    ):
        raise ValueError("Office binding changed during enrollment")
    locked.instance_id = response["instance_id"]
    locked.base_url = base
    locked.credential_id = response["credential_id"]
    locked.credential_encrypted = encryption.encrypt(token.encode()).decode()
    locked.expires_at = expiry
    locked.scopes = list(SCOPES)
    db.session.add(
        FieldIntegrationAudit(
            company_id=company_id,
            office_id=office_id,
            credential_id=locked.credential_id,
            actor_id=actor_id,
            action="credential_stored",
        )
    )
    db.session.commit()


@bp.route("/settings/field-integration", methods=["GET", "POST"])
@login_required
def manage():
    # Reuse native tenant selection and company-admin permission, not cloud role/device keys.
    from .settings.routes import _require_company_admin, _resolve_company

    _require_company_admin()
    company, _ = _resolve_company()
    if company is None:
        return jsonify(error="Select an authorized company first"), 403
    if not all(
        inspect(db.engine).has_table(model.__tablename__)
        for model in [FieldConnection, FieldIntegrationAudit]
    ):
        return jsonify(error="Operator must initialize office pairing tables"), 503
    row = db.session.get(FieldConnection, company.id)
    message = None
    if request.method == "POST":
        try:
            uid(company.id)
            if request.form.get("action") == "initialize":
                if not row:
                    row = FieldConnection(company_id=company.id, office_id=str(uuid4()))
                    db.session.add(row)
                    db.session.add(
                        FieldIntegrationAudit(
                            company_id=company.id,
                            office_id=row.office_id,
                            actor_id=str(current_user.id),
                            action="office_initialized",
                        )
                    )
                    db.session.commit()
                message = "Stable office identity ready; share identifiers privately with your cloud administrator."
            elif request.form.get("action") == "pair" and row:
                bundle = loads(request.form.get("bundle", ""))
                enroll(row, bundle, actor_id=str(current_user.id))
                message = (
                    "Credential encrypted locally. Business sync remains disabled."
                )
            else:
                raise ValueError("Initialize office first")
        except (
            ValueError,
            TypeError,
            KeyError,
            InvalidToken,
            UnicodeError,
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            HTTPException,
            IntegrityError,
        ):
            db.session.rollback()
            # No exception/body logging: transport error strings can embed secret response material.
            return (
                jsonify(
                    error="Pairing failed. Check company/office, configured HTTPS origin, encryption key and grant. If exchange already consumed it, issue a replacement."
                ),
                400,
            )
    row = db.session.get(FieldConnection, company.id)
    return render_template(
        "field_integration.html", company=company, connection=row, message=message
    )


def register(app):
    app.register_blueprint(bp)

    @app.cli.command("init-field-integration")
    def initialize():
        for model in [FieldConnection, FieldIntegrationAudit]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Additive office-connection table ready. No credentials or sync workers created."
        )
