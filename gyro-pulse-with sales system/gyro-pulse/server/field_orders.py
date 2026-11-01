"""Cloud-admin-vouched immutable proposals; no legacy order or stock writes.
Device/agent authorization is intentionally NOT provided by this operator pilot.
"""

import hashlib
from datetime import datetime
import click
from models import db
from catalog_bridge import CatalogHead
from order_contract import validate, OrderError
from sync_core import Outbox, canonical


class SubmittedOrder(db.Model):
    __tablename__ = "hybrid_submitted_orders"
    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    payload_sha256 = db.Column(db.String(64), nullable=False)
    message_id = db.Column(db.String(36), nullable=False, unique=True)
    submitted_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def enqueue_proposal(context, payload, actor_id):
    if context.side != "gyro":
        raise OrderError("Cloud proposal required")
    validate(payload)
    raw = canonical(payload)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    old = db.session.get(SubmittedOrder, payload["order_id"])
    if old:
        if (
            old.company_id,
            old.instance_id,
            old.office_id,
        ) != context.identity or old.payload_sha256 != sha:
            raise OrderError("Business order ID reused with different data")
        return old
    head = (
        CatalogHead.query.filter_by(
            company_id=context.identity[0],
            instance_id=context.identity[1],
            office_id=context.identity[2],
            store_id=payload["store_id"],
        )
        .with_for_update()
        .first()
    )
    if head is None or head.message_id != payload["catalog_message_id"]:
        raise OrderError("Refresh current store catalog before submitting")
    products = {p["id"]: p for p in head.payload["items"]}
    for line in payload["items"]:
        product = products.get(line["product_id"])
        if (
            not product
            or not product["active"]
            or product["price"] != line["unit_price"]
        ):
            raise OrderError("Product/price not in current native snapshot")
    envelope = context.envelope("field.order", payload)
    message = context.enqueue(envelope)
    row = SubmittedOrder(
        id=payload["order_id"],
        company_id=context.identity[0],
        instance_id=context.identity[1],
        office_id=context.identity[2],
        payload=payload,
        payload_sha256=sha,
        message_id=message.id,
        submitted_by=actor_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def register(app):
    @app.cli.command("init-field-orders")
    def initialize():
        SubmittedOrder.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Proposal table ready. No native sale, payment or stock entry created."
        )
