"""Explicit one-shot cloud sync. No scheduler/LAN fallback or business writes."""

import json
import ssl
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler
import click
from .extensions import db
from .field_integration import FieldConnection, cipher, trusted_origins, NoRedirect
from .integration_contract import origin, valid_scopes, uid, loads
from .sync_core import Transport, ProtocolError, decode, MAX_BYTES


def cloud_request(base, path, headers, payload=None):
    # Caller supplies one of the literal paths below, never a bundle/user-controlled URL.
    if path not in {
        "/api/v1/integration/status",
        "/api/v1/sync/messages",
        "/api/v1/sync/pull",
        "/api/v1/sync/ack",
    }:
        raise ProtocolError("Unknown cloud route")
    opener = build_opener(
        ProxyHandler({}),
        NoRedirect(),
        HTTPSHandler(context=ssl.create_default_context()),
    )
    data = (
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if payload is not None
        else None
    )
    if data is not None and len(data) > MAX_BYTES:
        raise ProtocolError("Request size limit")
    req = Request(
        base + path,
        data=data,
        headers={
            **headers,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    with opener.open(req, timeout=10) as response:
        if (
            response.status != 200
            or response.headers.get_content_type() != "application/json"
        ):
            raise ProtocolError("Invalid cloud response")
        # Pull response wraps the bounded envelope in fixed-size ID/lease metadata.
        try:
            return loads(response.read(MAX_BYTES + 1025), limit=MAX_BYTES + 1024)
        except ValueError:
            raise ProtocolError("Invalid bounded cloud JSON") from None


def sync_once(company_id, limit=10):
    uid(company_id)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProtocolError("Invalid batch limit")
    row = db.session.get(FieldConnection, company_id)
    if not row or not row.credential_encrypted or not row.instance_id:
        raise ProtocolError("Pair office first")
    base = origin(row.base_url)
    if base not in trusted_origins():
        raise ProtocolError("Cloud no longer explicitly trusted")
    context = Transport("retail", row.company_id, row.instance_id, row.office_id)
    credential_id = row.credential_id
    token = cipher().decrypt(row.credential_encrypted.encode()).decode("ascii")
    if len(token) != 43 or not token.isascii():
        raise ProtocolError("Invalid stored bearer")
    headers = {
        "Authorization": "Bearer " + token,
        "X-Company-ID": row.company_id,
        "X-Instance-ID": row.instance_id,
        "X-Office-ID": row.office_id,
    }
    db.session.commit()  # release native read transaction before TLS/network
    status = cloud_request(base, "/api/v1/integration/status", headers)
    if (
        type(status) is not dict
        or type(status.get("schema_version")) is not int
        or status["schema_version"] != 1
        or (
            status.get("company_id"),
            status.get("instance_id"),
            status.get("office_id"),
        )
        != context.identity
        or status.get("credential_id") != credential_id
        or not valid_scopes(status.get("scopes"))
        or "transport:exchange" not in status["scopes"]
    ):
        raise ProtocolError("Cloud transport permission/identity mismatch")
    counts = context.deliver_batch(
        lambda envelope: cloud_request(
            base, "/api/v1/sync/messages", headers, envelope
        ),
        limit=limit,
    )
    counts["received"] = 0
    for _ in range(limit):
        response = cloud_request(base, "/api/v1/sync/pull", headers)
        if type(response) is not dict or set(response) != {"message"}:
            raise ProtocolError("Invalid pull response")
        job = response["message"]
        if job is None:
            break
        if type(job) is not dict or set(job) != {
            "message_id",
            "lease_token",
            "envelope",
        }:
            raise ProtocolError("Invalid pull response")
        uid(job["message_id"])
        uid(job["lease_token"])
        if (
            type(job["envelope"]) is not dict
            or job["envelope"].get("message_id") != job["message_id"]
        ):
            raise ProtocolError("Pull identity mismatch")
        try:
            receipt = context.accept(job["envelope"])
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        # Lost ACK is safe: receiver has committed and returns identical receipt on redelivery.
        ack = cloud_request(
            base,
            "/api/v1/sync/ack",
            headers,
            dict(
                message_id=job["message_id"],
                lease_token=job["lease_token"],
                receipt=receipt,
            ),
        )
        if ack != {"status": "acknowledged"}:
            raise ProtocolError("Cloud acknowledgement failed")
        counts["received"] += 1
    return counts


def register(app):
    @app.cli.command("field-sync-once")
    @click.option("--company-id", required=True)
    @click.option("--limit", default=10, type=click.IntRange(1, 100))
    def run(company_id, limit):
        # Only nonsecret counts/errors reach console. Requires trusted local operator access.
        try:
            counts = sync_once(company_id, limit)
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Transfer failed; durable queues retained. Check scoped grant/TLS/config and retry."
            ) from None
        click.echo(json.dumps(counts, sort_keys=True))
