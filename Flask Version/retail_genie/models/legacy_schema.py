"""Typed MySQL tables preserving the checked-in SQLite migration source.

The legacy UI historically stores several nested structures as JSON text and
uses camelCase column names. Target columns are snake_case; the importer keeps
an explicit source-to-target mapping in ``legacy_import.py``. These tables are
intended as a loss-minimizing landing schema for the later business-module
migration, not as the final normalized operational model.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.mysql import LONGTEXT

from ..extensions import db

_METADATA = db.metadata
_TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
_LONG_TEXT = Text().with_variant(LONGTEXT(), "mysql", "mariadb")


def _column(
    name: str,
    type_,
    *,
    nullable: bool = True,
    foreign_key: str | None = None,
    foreign_key_name: str | None = None,
    use_alter: bool = False,
) -> Column:
    args = [name, type_]
    if foreign_key:
        args.append(ForeignKey(foreign_key, name=foreign_key_name, use_alter=use_alter))
    return Column(*args, nullable=nullable)


def _table(name: str, *columns: Column) -> Table:
    return Table(name, _METADATA, *columns, **_TABLE_OPTIONS)


def _id() -> Column:
    return Column("id", String(64), primary_key=True, nullable=False)


def _fk(
    name: str,
    target: str,
    *,
    nullable: bool = True,
    use_alter: bool = False,
    constraint_name: str | None = None,
) -> Column:
    # Let MySQL generate table-local names for ordinary constraints. The two
    # cyclic order/demand constraints have explicit unique names for migration.
    if use_alter and constraint_name is None:
        constraint_name = f"fk_orders_{name}"
    return _column(
        name,
        String(64),
        nullable=nullable,
        foreign_key=target,
        foreign_key_name=constraint_name,
        use_alter=use_alter,
    )


legacy_tables: dict[str, Table] = {}


def _register(table: Table) -> None:
    legacy_tables[table.name] = table


# ``users`` is the current security model. Its password column is Argon2-only;
# see legacy_import.py for the one-way password transformation.
_register(
    _table(
        "attachments",
        _id(),
        _fk("message_id", "messages.id"),
        _column("file_path", Text()),
        _column("original_name", String(255)),
        _column("mime_type", String(160)),
    )
)
_register(
    _table(
        "attendance_logs",
        _id(),
        _fk("user_id", "users.id"),
        _column("timestamp", DateTime(timezone=True)),
        _column("method", String(64)),
        _column("selfie_data_uri", _LONG_TEXT),
        _column("selfie_image_path", Text()),
    )
)
_register(
    _table(
        "attendance_settings",
        _id(),
        _column("mandatory_attendance_time", String(64)),
        _column("is_mandatory_attendance_active", Boolean),
        _column("max_concurrent_breaks", Integer),
    )
)
_register(
    _table(
        "audit_images",
        _id(),
        _fk("count_event_id", "audit_item_counts.id"),
        _column("image_path", Text()),
        _column("created_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "audit_item_counts",
        _id(),
        _fk("audit_item_id", "audit_items.id"),
        _column("count", Integer),
        _column("notes", Text()),
        _column("created_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "audit_items",
        _id(),
        _fk("audit_id", "audits.id"),
        _fk("product_id", "products.id"),
        _column("product_name", Text()),
        _column("product_sku", String(128)),
        _column("current_stock", Integer),
        _column("final_audited_qty", Integer),
        _column("notes", Text()),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "audits",
        _id(),
        _column("title", Text()),
        _fk("admin_id", "users.id"),
        _fk("auditor_id", "users.id"),
        _column("store_location", String(255)),
        _column("status", String(48)),
        _column("started_at", DateTime(timezone=True)),
        _column("completed_at", DateTime(timezone=True)),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
        _column("auditor_selfie_path", Text()),
    )
)
_register(
    _table(
        "break_logs",
        _id(),
        _fk("user_id", "users.id"),
        _column("start_time", DateTime(timezone=True)),
        _column("end_time", DateTime(timezone=True)),
        _column("duration_ms", BigInteger),
    )
)
_register(
    _table(
        "commission_settings",
        _id(),
        _column("sales_target", Numeric(14, 3)),
        _column("commission_interval", Numeric(14, 3)),
        _column("commission_percentage", Numeric(12, 8)),
        _column("is_active", Boolean),
    )
)
_register(
    _table(
        "conversations",
        _id(),
        _column("subject", Text()),
        _column("created_at", DateTime(timezone=True)),
        _fk("creator_id", "users.id"),
    )
)
_register(
    _table(
        "demand_notices",
        _id(),
        _fk("salesperson_id", "users.id"),
        _column("salesperson_name", Text()),
        _column("customer_contact_number", String(96)),
        _fk("product_id", "products.id"),
        _column("product_name", Text()),
        _column("product_sku", String(128)),
        _column("quantity_requested", Integer),
        _column("quantity_fulfilled", Integer),
        _column("agreed_price", Numeric(14, 3)),
        _column("expected_availability_date", DateTime(timezone=True)),
        _column("status", String(48)),
        _column("is_new_product", Boolean),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
        _column("notes", Text()),
        _column("payments", JSON),
        _fk(
            "linked_order_id",
            "orders.id",
            constraint_name="fk_demand_notices_linked_order_id",
        ),
    )
)
_register(
    _table(
        "global_discount_settings",
        _id(),
        _column("percentage", Numeric(12, 8)),
        _column("start_date", DateTime(timezone=True)),
        _column("end_date", DateTime(timezone=True)),
        _column("is_active", Boolean),
        _column("description", Text()),
    )
)
_register(
    _table(
        "invoice_number_settings",
        _id(),
        _column("next_number", BigInteger),
    )
)
_register(
    _table(
        "message_recipients",
        _id(),
        _fk("message_id", "messages.id"),
        _fk("recipient_id", "users.id"),
        _column("recipient_type", String(48)),
        _column("read_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "messages",
        _id(),
        _fk("conversation_id", "conversations.id"),
        _fk("sender_id", "users.id"),
        _column("content", _LONG_TEXT),
        _column("sent_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "orders",
        _id(),
        _fk("primary_salesperson_id", "users.id"),
        _column("primary_salesperson_name", Text()),
        _fk("secondary_salesperson_id", "users.id"),
        _column("secondary_salesperson_name", Text()),
        _column("primary_salesperson_commission", Numeric(14, 3)),
        _column("secondary_salesperson_commission", Numeric(14, 3)),
        _column("items", JSON),
        _column("subtotal", Numeric(14, 3)),
        _column("discount_amount", Numeric(14, 3)),
        _column("applied_discount_percentage", Numeric(12, 8)),
        _column("applied_global_discount_percentage", Numeric(12, 8)),
        _column("taxes", JSON),
        _column("total_amount", Numeric(14, 3)),
        _column("status", String(48)),
        _column("delivery_status", String(48)),
        _column("customer_name", Text()),
        _column("customer_phone", String(96)),
        _column("delivery_address", Text()),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
        _column("payments", JSON),
        _column("storekeeper_notes", Text()),
        _column("cashier_notes", Text()),
        _column("reminder_date", DateTime(timezone=True)),
        _column("reminder_notes", Text()),
        _column("return_transactions", JSON),
        # The legacy relationship is cyclic with demand_notices.linked_order_id.
        # MySQL creates this one constraint after both tables exist.
        _fk("linked_demand_notice_id", "demand_notices.id", use_alter=True),
    )
)
_register(
    _table(
        "po_attachments",
        _id(),
        _fk("po_id", "purchase_orders.id"),
        _column("file_path", Text()),
        _column("original_name", String(255)),
        _column("notes", Text()),
        _column("uploaded_at", DateTime(timezone=True)),
        _fk("uploaded_by_id", "users.id"),
        _column("type", String(48)),
    )
)
_register(
    _table(
        "po_items",
        _id(),
        _fk("po_id", "purchase_orders.id"),
        _fk("product_id", "products.id"),
        _column("quantity_ordered", Integer),
        _column("quantity_received", Integer),
        _column("notes", Text()),
        _column("updated_at", DateTime(timezone=True)),
    )
)
_register(
    _table(
        "products",
        _id(),
        _column("name", Text()),
        _column("price", Numeric(14, 3)),
        _column("quantity_in_stock", Integer),
        _column("sku", String(128)),
        _column("expiry_date", DateTime(timezone=True)),
        _column("image_url", _LONG_TEXT),
        _column("category", String(128)),
        _column("is_demand_notice_product", Boolean),
        _column("low_stock_threshold", Integer),
        _column("low_stock_price", Numeric(14, 3)),
    )
)
_register(
    _table(
        "purchase_orders",
        _id(),
        _fk("supplier_id", "suppliers.id"),
        _column("status", String(48)),
        _column("total_amount", Numeric(14, 3)),
        _column("advance_paid", Numeric(14, 3)),
        _column("deadline", DateTime(timezone=True)),
        _column("expected_delivery", DateTime(timezone=True)),
        _column("invoice_path", Text()),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
        _column("transportation_details", Text()),
    )
)
_register(
    _table(
        "quotation_items",
        _id(),
        _fk("quotation_id", "quotations.id"),
        _fk("product_id", "products.id"),
        _column("product_name", Text()),
        _column("product_sku", String(128)),
        _column("price", Numeric(14, 3)),
        _column("quantity", Integer),
        _column("is_external", Boolean),
        _column("converted", Boolean),
    )
)
_register(
    _table(
        "quotations",
        _id(),
        _fk("salesperson_id", "users.id"),
        _column("customer_name", Text()),
        _column("customer_phone", String(96)),
        _column("customer_email", String(254)),
        _column("customer_address", Text()),
        _column("preparation_days", Integer),
        _column("valid_until", DateTime(timezone=True)),
        _column("status", String(48)),
        _column("created_at", DateTime(timezone=True)),
        _column("updated_at", DateTime(timezone=True)),
        _column("total_amount", Numeric(14, 3)),
        _column("notes", Text()),
    )
)
_register(
    _table(
        "supplier_attachments",
        _id(),
        _fk("supplier_id", "suppliers.id"),
        _column("file_path", Text()),
        _column("original_name", String(255)),
        _column("uploaded_at", DateTime(timezone=True)),
        _fk("uploaded_by_id", "users.id"),
    )
)
_register(
    _table(
        "supplier_products",
        _id(),
        _fk("supplier_id", "suppliers.id"),
        _fk("product_id", "products.id"),
        _column("unit_price", Numeric(14, 3)),
        _column("document_path", Text()),
    )
)
_register(
    _table(
        "suppliers",
        _id(),
        _column("name", Text()),
        _column("contact_email", String(254)),
        _column("phone", String(96)),
        _column("lead_time", Integer),
        _column("notes", Text()),
    )
)
_register(
    _table(
        "tax_settings",
        _id(),
        _column("name", String(128)),
        _column("rate", Numeric(12, 8)),
        _column("enabled", Boolean),
    )
)
