"""Durable transport primitives, schema v1. NOT an unauthenticated HTTP adapter.

Callers own transactions: enqueue alongside the source change; accept + commit BEFORE
returning a receipt. A receipt means durable RECEIVED, never business approval/applied.
No stock/order writers, automatic network worker, implicit schema creation, or credentials.
"""

import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import click
from sqlalchemy import and_, or_
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.exc import IntegrityError

from .extensions import db

MAX_BYTES = 131072
MAX_ATTEMPTS = 8
ENVELOPE_FIELDS = {
    "schema_version",
    "message_id",
    "company_id",
    "instance_id",
    "office_id",
    "sender",
    "recipient",
    "kind",
    "payload",
}
RECEIPT_FIELDS = {
    "schema_version",
    "message_id",
    "company_id",
    "instance_id",
    "office_id",
    "recipient",
    "envelope_sha256",
    "status",
}
ROUTES = {"retail": ("gyro", "catalog.snapshot"), "gyro": ("retail", "field.order")}


class ProtocolError(ValueError):
    """Malformed/cross-boundary envelope or receipt; never log payloads."""


class Conflict(ProtocolError):
    """Same message ID reused for different immutable bytes."""


def canonical(value):
    count = [0]

    def check(item, depth=0):
        count[0] += 1
        if depth > 24 or count[0] > 10000:
            raise ProtocolError("JSON complexity limit")
        if item is None or type(item) in (str, bool):
            return
        if type(item) is int and abs(item) <= 9007199254740991:
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child, depth + 1)
            return
        # Decimal amounts travel as strings. NaN, floating ambiguity and exotic types fail closed.
        raise ProtocolError("Unsupported JSON value")

    check(value)
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (ValueError, TypeError, UnicodeError):
        raise ProtocolError("Invalid JSON") from None
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeError:
        raise ProtocolError("Invalid Unicode") from None
    if size > MAX_BYTES:
        raise ProtocolError("Envelope size limit")
    return raw


def uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value or not UUID(value).int:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ProtocolError("Canonical UUID required") from None
    return value


def decode(raw):
    if not isinstance(raw, (bytes, str)) or len(raw) > MAX_BYTES:
        raise ProtocolError("Envelope size limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("Duplicate JSON key")
            result[key] = value
        return result

    def reject(_):
        raise ProtocolError("Nonfinite JSON")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError):
        raise ProtocolError("Invalid JSON") from None
    canonical(value)
    return value


class Outbox(db.Model):
    __tablename__ = "hybrid_sync_outbox"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False, index=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    envelope = db.Column(db.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    envelope_sha256 = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(20), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    lease_until = db.Column(db.DateTime, index=True)
    lease_token = db.Column(db.String(36))
    receipt = db.Column(db.JSON)
    error_code = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Inbox(db.Model):
    __tablename__ = "hybrid_sync_inbox"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False, index=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    envelope = db.Column(db.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    envelope_sha256 = db.Column(db.String(64), nullable=False)
    receipt = db.Column(db.JSON, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # No 'approved'/'posted' column: delivery cannot silently mean native acceptance.
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Transport:
    def __init__(self, side, company_id, instance_id, office_id):
        if side not in ROUTES:
            raise ProtocolError("Unknown deployment side")
        self.side = side
        self.identity = tuple(
            uuid(item) for item in (company_id, instance_id, office_id)
        )

    def scoped(self, model):
        return model.query.filter_by(
            company_id=self.identity[0],
            instance_id=self.identity[1],
            office_id=self.identity[2],
        )

    def validate(self, envelope, incoming):
        if (
            type(envelope) is not dict
            or set(envelope) != ENVELOPE_FIELDS
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != 1
        ):
            raise ProtocolError("Unsupported envelope schema")
        uuid(envelope["message_id"])
        identity = tuple(
            uuid(envelope[key]) for key in ("company_id", "instance_id", "office_id")
        )
        if identity != self.identity:
            raise ProtocolError("Identity mismatch")
        sender = envelope["sender"]
        if (
            type(sender) is not str
            or sender not in ROUTES
            or (envelope["recipient"], envelope["kind"]) != ROUTES[sender]
        ):
            raise ProtocolError("Direction/kind mismatch")
        if (envelope["recipient"] if incoming else sender) != self.side:
            raise ProtocolError("Wrong deployment side")
        if type(envelope["payload"]) is not dict:
            raise ProtocolError("Object payload required")
        raw = canonical(envelope)
        return raw, hashlib.sha256(raw.encode()).hexdigest()

    def envelope(self, kind, payload, message_id=None):
        target, allowed = ROUTES[self.side]
        if kind != allowed:
            raise ProtocolError("Direction/kind mismatch")
        result = dict(
            schema_version=1,
            message_id=message_id or str(uuid4()),
            company_id=self.identity[0],
            instance_id=self.identity[1],
            office_id=self.identity[2],
            sender=self.side,
            recipient=target,
            kind=kind,
            payload=payload,
        )
        self.validate(result, False)
        return result

    def _persist(self, model, envelope, **values):
        raw, sha = self.validate(envelope, model is Inbox)
        row = model(
            id=envelope["message_id"],
            company_id=self.identity[0],
            instance_id=self.identity[1],
            office_id=self.identity[2],
            envelope=raw,
            envelope_sha256=sha,
            **values
        )
        # Python's legacy sqlite driver does not BEGIN for SELECT/SAVEPOINT. Establish
        # the outer transaction explicitly or RELEASE SAVEPOINT could accidentally commit.
        connection = db.session.connection()
        if (
            connection.dialect.name == "sqlite"
            and not connection.connection.driver_connection.in_transaction
        ):
            connection.exec_driver_sql("BEGIN")
        old = db.session.get(model, envelope["message_id"])
        if old is not None:
            if (
                (old.company_id, old.instance_id, old.office_id) != self.identity
                or old.envelope_sha256 != sha
                or old.envelope != raw
            ):
                raise Conflict("Message identity conflict")
            return old, False
        # Savepoint preserves unrelated caller writes on an idempotent unique-key collision.
        try:
            with db.session.begin_nested():
                db.session.add(row)
                db.session.flush()
            return row, True
        except IntegrityError:
            old = (
                self.scoped(model)
                .filter_by(id=envelope["message_id"])
                .populate_existing()
                .first()
            )
            if old is None or old.envelope_sha256 != sha or old.envelope != raw:
                raise Conflict("Message identity conflict") from None
            return old, False

    def enqueue(self, envelope):
        """No commit: caller can atomically save source data and outbox row."""
        row, _ = self._persist(Outbox, envelope)
        return row

    def accept(self, envelope):
        """No commit: authenticated adapter must COMMIT before sending this receipt."""
        _, sha = self.validate(envelope, True)
        receipt = dict(
            schema_version=1,
            message_id=envelope["message_id"],
            company_id=self.identity[0],
            instance_id=self.identity[1],
            office_id=self.identity[2],
            recipient=self.side,
            envelope_sha256=sha,
            status="received",
        )
        row, _ = self._persist(Inbox, envelope, receipt=receipt)
        return dict(row.receipt)

    def claim(self, limit=10, now=None, lease_seconds=60):
        """Claim using locks + conditional update. COMMIT leases before any network call."""
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(lease_seconds) is not int
            or not 1 <= lease_seconds <= 300
        ):
            raise ProtocolError("Invalid worker bounds")
        now = now or datetime.utcnow()
        expired = and_(Outbox.state == "leased", Outbox.lease_until <= now)
        self.scoped(Outbox).filter(expired, Outbox.attempts >= MAX_ATTEMPTS).update(
            dict(
                state="dead",
                error_code="attempt_limit",
                lease_token=None,
                lease_until=None,
            ),
            synchronize_session=False,
        )
        eligible = or_(
            and_(Outbox.state == "pending", Outbox.available_at <= now), expired
        )
        rows = (
            self.scoped(Outbox)
            .filter(eligible, Outbox.attempts < MAX_ATTEMPTS)
            .order_by(Outbox.created_at, Outbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .populate_existing()
            .all()
        )
        result = []
        for row in rows:
            token = str(uuid4())
            changed = (
                self.scoped(Outbox)
                .filter(Outbox.id == row.id, eligible, Outbox.attempts < MAX_ATTEMPTS)
                .update(
                    dict(
                        state="leased",
                        lease_token=token,
                        lease_until=now + timedelta(seconds=lease_seconds),
                        attempts=Outbox.attempts + 1,
                        error_code=None,
                    ),
                    synchronize_session=False,
                )
            )
            if changed == 1:
                result.append((row.id, token, decode(row.envelope)))
        return result

    def _lease(self, message_id, token, now):
        row = (
            self.scoped(Outbox)
            .filter_by(id=uuid(message_id), state="leased", lease_token=uuid(token))
            .with_for_update()
            .populate_existing()
            .first()
        )
        if row is None or row.lease_until <= now:
            raise Conflict("Lease is no longer current")
        return row

    def acknowledge(self, message_id, token, receipt, now=None):
        now = now or datetime.utcnow()
        row = self._lease(message_id, token, now)
        expected = dict(
            schema_version=1,
            message_id=row.id,
            company_id=self.identity[0],
            instance_id=self.identity[1],
            office_id=self.identity[2],
            recipient=ROUTES[self.side][0],
            envelope_sha256=row.envelope_sha256,
            status="received",
        )
        if (
            type(receipt) is not dict
            or set(receipt) != RECEIPT_FIELDS
            or type(receipt.get("schema_version")) is not int
            or receipt != expected
        ):
            raise ProtocolError("Receipt does not match immutable message")
        self._finish(
            row,
            token,
            now,
            dict(
                state="acknowledged",
                receipt=dict(receipt),
                lease_token=None,
                lease_until=None,
            ),
        )

    def _finish(self, row, token, now, values):
        changed = (
            self.scoped(Outbox)
            .filter(
                Outbox.id == row.id,
                Outbox.state == "leased",
                Outbox.lease_token == token,
                Outbox.lease_until > now,
            )
            .update(values, synchronize_session="fetch")
        )
        if changed != 1:
            raise Conflict("Lease is no longer current")

    def failed(self, message_id, token, *, permanent=False, now=None):
        now = now or datetime.utcnow()
        row = self._lease(message_id, token, now)
        self._finish(
            row,
            token,
            now,
            dict(
                state=(
                    "dead" if permanent or row.attempts >= MAX_ATTEMPTS else "pending"
                ),
                error_code="protocol_rejected" if permanent else "delivery_error",
                available_at=now + timedelta(seconds=min(3600, 2**row.attempts)),
                lease_token=None,
                lease_until=None,
            ),
        )

    def deliver_batch(self, sender, limit=10):
        """Opt-in worker, no scheduler. sender must enforce scoped auth/TLS externally.
        Network I/O occurs only after lease commit. Unhandled crashes recover on lease expiry.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ProtocolError("Invalid worker bounds")
        counts = {"acknowledged": 0, "retry_or_dead": 0}
        for _ in range(limit):
            # Just-in-time leases: queued jobs do not expire waiting on earlier network calls.
            jobs = self.claim(limit=1)
            db.session.commit()
            if not jobs:
                break
            message_id, token, envelope = jobs[0]
            try:
                receipt = sender(envelope)
                self.acknowledge(message_id, token, receipt)
                db.session.commit()
                counts["acknowledged"] += 1
            except (OSError, TimeoutError):
                db.session.rollback()
                try:
                    self.failed(message_id, token)
                    db.session.commit()
                except Conflict:
                    db.session.rollback()
                counts["retry_or_dead"] += 1
            except ProtocolError:
                db.session.rollback()
                try:
                    self.failed(message_id, token, permanent=True)
                    db.session.commit()
                except Conflict:
                    db.session.rollback()
                counts["retry_or_dead"] += 1
        return counts


def register(app):
    @app.cli.command("init-sync-transport")
    def initialize():
        for model in [Inbox, Outbox]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Additive durable transport tables ready. No HTTP permissions, workers or business writers enabled."
        )
