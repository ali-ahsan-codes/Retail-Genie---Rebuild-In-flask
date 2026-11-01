"""Explicit native full-store export. Reads native inventory; never adjusts stock."""

from datetime import datetime, timezone
from decimal import Decimal
import click
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .models.catalog import CatalogProduct, InventoryBalance
from .models.tenancy import Company, Store
from .field_integration import FieldConnection
from .sync_core import Transport, ProtocolError, canonical
from .catalog_contract import validate, CatalogError, MAX_ITEMS


class CatalogStream(db.Model):
    __tablename__ = "hybrid_catalog_streams"
    company_id = db.Column(db.String(64), primary_key=True)
    store_id = db.Column(db.String(64), primary_key=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    sequence = db.Column(db.BigInteger, nullable=False, default=0)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def exact_price(value):
    if value is None:
        return None
    dec = Decimal(value)
    if not dec.is_finite() or dec < 0 or dec != dec.quantize(Decimal("0.001")):
        raise CatalogError("Invalid native price")
    return format(dec, ".3f")


def enqueue_snapshot(company_id, store_id):
    """Caller commits stream sequence + immutable outbox together; no network here."""
    # Ensure SQLite pilot reads are one real transaction too (legacy driver SELECTs
    # otherwise do not BEGIN). MySQL uses the deployment's repeatable-read transaction.
    sql_connection = db.session.connection()
    if (
        sql_connection.dialect.name == "sqlite"
        and not sql_connection.connection.driver_connection.in_transaction
    ):
        sql_connection.exec_driver_sql("BEGIN")
    company = db.session.get(Company, company_id)
    if not company or not company.is_active:
        raise CatalogError("Active native company required")
    connection = db.session.get(FieldConnection, company_id)
    if not connection or not connection.instance_id:
        raise CatalogError("Pair this native company first")
    transport = Transport(
        "retail", company.id, connection.instance_id, connection.office_id
    )
    store = Store.query.filter_by(
        id=store_id,
        company_id=company.id,
        tenant_container_id=company.tenant_container_id,
        is_active=True,
    ).first()
    if store is None:
        raise CatalogError("Authorized active store required")
    # Serialize exporters using a persistent per-store counter, never wall-clock ordering.
    key = dict(company_id=company.id, store_id=store.id)
    stream = (
        CatalogStream.query.filter_by(**key)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if stream is None:
        stream = CatalogStream(
            **key,
            instance_id=connection.instance_id,
            office_id=connection.office_id,
            sequence=0
        )
        db.session.add(stream)
        db.session.flush()  # unique-key race: whole caller transaction retries
    if (stream.instance_id, stream.office_id) != (
        connection.instance_id,
        connection.office_id,
    ):
        raise CatalogError("Catalog stream identity cannot be reassigned")
    old = stream.sequence
    products = (
        CatalogProduct.query.filter_by(
            company_id=company.id, tenant_container_id=company.tenant_container_id
        )
        .order_by(CatalogProduct.id)
        .limit(MAX_ITEMS + 1)
        .all()
    )
    if len(products) > MAX_ITEMS:
        raise CatalogError("Pilot limit exceeded; snapshot not truncated")
    balances = (
        InventoryBalance.query.filter_by(
            company_id=company.id,
            tenant_container_id=company.tenant_container_id,
            store_id=store.id,
        )
        .limit(MAX_ITEMS + 1)
        .all()
    )
    ids = {p.id for p in products}
    if len(balances) > MAX_ITEMS or any(
        b.product_owner_company_id != company.id or b.product_id not in ids
        for b in balances
    ):
        raise CatalogError("Shared/foreign inventory requires explicit mapping")
    by_product = {b.product_id: b for b in balances}
    if len(by_product) != len(balances):
        raise CatalogError("Duplicate native balance mapping")
    items = []
    for product in products:
        balance = by_product.get(product.id)
        items.append(
            dict(
                id=product.id,
                sku=product.sku,
                barcode=product.barcode,
                name=product.name,
                category=product.category,
                active=bool(product.is_active),
                price=exact_price(product.price),
                low_stock_price=exact_price(product.low_stock_price),
                on_hand=balance.quantity_on_hand if balance else 0,
                low_stock_threshold=balance.low_stock_threshold if balance else None,
            )
        )
    payload = dict(
        schema_version=1,
        mode="full",
        sequence=old + 1,
        store=dict(id=store.id, code=store.code, name=store.name),
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        currency=None,
        items=items,
    )
    validate(payload)
    envelope = transport.envelope("catalog.snapshot", payload)
    canonical(envelope)
    changed = CatalogStream.query.filter_by(**key, sequence=old).update(
        {"sequence": old + 1}, synchronize_session="fetch"
    )
    if changed != 1:
        raise CatalogError("Concurrent snapshot; retry full transaction")
    return transport.enqueue(envelope)


def register(app):
    @app.cli.command("init-field-catalog")
    def initialize():
        CatalogStream.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Native catalog stream table ready. No stock modified or exported automatically."
        )

    @app.cli.command("field-catalog-export")
    @click.option("--company-id", required=True)
    @click.option("--store-id", required=True)
    def export(company_id, store_id):
        try:
            row = enqueue_snapshot(company_id, store_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Catalog export rejected; check scope, pairing, pilot limits and explicit schema setup. No partial export committed."
            ) from None
        click.echo(
            "Queued immutable catalog message "
            + row.id
            + "; run field-sync-once to deliver."
        )
