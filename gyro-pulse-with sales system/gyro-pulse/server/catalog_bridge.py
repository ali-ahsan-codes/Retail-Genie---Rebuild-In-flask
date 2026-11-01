"""Read-only native catalog projection. No legacy Product/stock ledger writes."""

import json
from datetime import datetime
import click
from flask import current_app
from models import db
from sync_core import Inbox, Transport, decode, ProtocolError
from catalog_contract import validate, CatalogError


class CatalogHead(db.Model):
    __tablename__ = "hybrid_catalog_heads"
    company_id = db.Column(db.String(36), primary_key=True)
    store_id = db.Column(db.String(64), primary_key=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    sequence = db.Column(db.BigInteger, nullable=False)
    message_id = db.Column(db.String(36), nullable=False)
    envelope_sha256 = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    applied_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class CatalogApplication(db.Model):
    __tablename__ = "hybrid_catalog_applications"
    message_id = db.Column(db.String(36), primary_key=True)
    status = db.Column(db.String(20), nullable=False)
    processed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def apply_message(transport, message_id):
    """Trusted operator only, caller transaction; receipt remains 'received'."""
    if transport.side != "gyro":
        raise CatalogError("Gyro projection only")
    row = transport.scoped(Inbox).filter_by(id=message_id).first()
    if row is None:
        raise CatalogError("Scoped inbox message required")
    envelope = decode(row.envelope)
    _, sha = transport.validate(envelope, True)
    if sha != row.envelope_sha256 or envelope["kind"] != "catalog.snapshot":
        raise CatalogError("Corrupt or wrong message kind")
    payload = validate(envelope["payload"])
    old_application = db.session.get(CatalogApplication, message_id)
    if old_application:
        return old_application.status
    key = dict(company_id=transport.identity[0], store_id=payload["store"]["id"])
    head = (
        CatalogHead.query.filter_by(**key).with_for_update().populate_existing().first()
    )
    status = "applied"
    if head:
        if (head.instance_id, head.office_id) != transport.identity[1:]:
            raise CatalogError("Projection identity conflict")
        if payload["sequence"] < head.sequence:
            status = "stale"
        elif payload["sequence"] == head.sequence:
            if head.envelope_sha256 != sha:
                raise CatalogError("Sequence reused for different snapshot")
            status = "applied"
        else:
            old = head.sequence
            changed = CatalogHead.query.filter_by(**key, sequence=old).update(
                dict(
                    sequence=payload["sequence"],
                    message_id=message_id,
                    envelope_sha256=sha,
                    payload=payload,
                    applied_at=datetime.utcnow(),
                ),
                synchronize_session="fetch",
            )
            if changed != 1:
                raise CatalogError("Concurrent application; retry transaction")
    else:
        db.session.add(
            CatalogHead(
                **key,
                instance_id=transport.identity[1],
                office_id=transport.identity[2],
                sequence=payload["sequence"],
                message_id=message_id,
                envelope_sha256=sha,
                payload=payload
            )
        )
        db.session.flush()  # concurrent first insert safely aborts one caller transaction
    db.session.add(CatalogApplication(message_id=message_id, status=status))
    db.session.flush()
    return status


def projection(transport, store_id):
    head = CatalogHead.query.filter_by(
        company_id=transport.identity[0],
        instance_id=transport.identity[1],
        office_id=transport.identity[2],
        store_id=store_id,
    ).first()
    if head is None:
        return None
    return dict(
        read_only=True,
        inventory_authority="retail-genie",
        message_id=head.message_id,
        envelope_sha256=head.envelope_sha256,
        payload=json.loads(json.dumps(head.payload)),
    )


def register(app):
    @app.cli.command("init-catalog-projection")
    def initialize():
        for model in [CatalogHead, CatalogApplication]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Read-only catalog projection tables ready. No stock ledger created."
        )

    @app.cli.command("catalog-apply")
    @click.option("--message-id", required=True)
    def apply(message_id):
        from dedicated import binding_matches
        from integration_api import Office

        try:
            if current_app.config[
                "GYRO_DEPLOYMENT_MODE"
            ] != "dedicated" or not binding_matches(current_app):
                raise CatalogError("Matching dedicated binding required")
            slot = db.session.get(Office, 1)
            if slot is None:
                raise CatalogError("Office binding required")
            context = Transport(
                "gyro",
                current_app.config["GYRO_COMPANY_ID"],
                current_app.config["GYRO_INSTANCE_ID"],
                slot.office_id,
            )
            result = apply_message(context, message_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Catalog application failed; existing projection and inbox retained. Check identity, schema and sequence."
            ) from None
        click.echo(
            "Catalog message "
            + result
            + ". Transport receipt still means received, not applied."
        )
