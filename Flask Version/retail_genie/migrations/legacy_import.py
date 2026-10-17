"""Read-only SQLite to MySQL importer with preflight, idempotency, and rollback.

The importer is deliberately insert-only. Existing rows are never overwritten:
identical source IDs are skipped, while conflicting rows abort the entire target
transaction. Legacy account passwords are reset to unknown random values by
default; the optional ``hash`` policy preserves a vetted legacy password only
as an Argon2 hash and still forces a change at next sign-in.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, insert, select, update
from sqlalchemy.types import JSON as JSONType

from ..extensions import db
from ..models import PERMISSIONS, ROLE_PERMISSION_LIMITS, ROLES, User, legacy_tables
from ..models.user import is_valid_username, normalize_username, utc_now

IMPORT_ORDER = (
    "users",
    "attendance_settings",
    "commission_settings",
    "global_discount_settings",
    "invoice_number_settings",
    "tax_settings",
    "products",
    "suppliers",
    "conversations",
    "attendance_logs",
    "break_logs",
    "audits",
    "purchase_orders",
    "quotations",
    "orders",
    "demand_notices",
    "audit_items",
    "audit_item_counts",
    "audit_images",
    "po_items",
    "po_attachments",
    "quotation_items",
    "supplier_products",
    "supplier_attachments",
    "messages",
    "message_recipients",
    "attachments",
)


class LegacyImportError(RuntimeError):
    """The source cannot be safely reconciled with the target schema."""


@dataclass
class ImportReport:
    source_counts: dict[str, int] = field(default_factory=dict)
    inserted_counts: dict[str, int] = field(default_factory=dict)
    skipped_counts: dict[str, int] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    user_passwords_reset: int = 0
    user_passwords_hashed: int = 0
    dry_run: bool = True


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _snake_case(identifier: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", identifier).lower()


def _open_sqlite_snapshot(path: str | Path) -> sqlite3.Connection:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise LegacyImportError("The SQLite source file does not exist or is not a regular file.")
    uri = source.as_uri() + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.Error as exc:
        raise LegacyImportError("The SQLite source could not be opened read-only.") from exc


def _validate_source_schema(connection: sqlite3.Connection) -> dict[str, list[str]]:
    actual_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    expected_tables = set(legacy_tables) | {"users"}
    if set(IMPORT_ORDER) != expected_tables:
        raise LegacyImportError("The importer table order does not cover the complete reviewed schema.")
    if actual_tables != expected_tables:
        missing = sorted(expected_tables - actual_tables)
        extra = sorted(actual_tables - expected_tables)
        details = []
        if missing:
            details.append(f"missing tables: {', '.join(missing)}")
        if extra:
            details.append(f"unmapped tables: {', '.join(extra)}")
        raise LegacyImportError("SQLite schema does not match the reviewed 27-table map (" + "; ".join(details) + ").")

    actual_columns: dict[str, list[str]] = {}
    for table_name in sorted(expected_tables):
        pragma = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
        names = [row[1] for row in pragma]
        actual_columns[table_name] = names
        if table_name == "users":
            expected = {"id", "username", "password", "role", "permissions", "activeBreakId", "auto_enter_after_scan"}
        else:
            expected = {_snake_case(name) for name in names}
            target = set(legacy_tables[table_name].c.keys())
            if expected != target:
                raise LegacyImportError(f"Reviewed column map mismatch for SQLite table '{table_name}'.")
            continue
        if set(names) != expected:
            raise LegacyImportError("The legacy users table has columns that do not match the reviewed import map.")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise LegacyImportError(
            f"SQLite source has {len(foreign_key_errors)} foreign-key violation(s); fix or reconcile them before importing."
        )
    return actual_columns


def _parse_json(value: Any, *, table: str, column: str, row_id: str) -> Any:
    if value is None:
        return None
    if not isinstance(value, (str, bytes, bytearray)):
        return value
    try:
        raw = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value
        return json.loads(
            raw,
            parse_constant=lambda _constant: (_ for _ in ()).throw(ValueError("non-standard JSON number")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise LegacyImportError(
            f"SQLite row {table}:{row_id} has invalid JSON in column '{column}'."
        ) from exc


def _parse_datetime(value: Any, *, table: str, column: str, row_id: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        seconds = float(value)
        if abs(seconds) >= 100_000_000_000:
            seconds /= 1000
        try:
            parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise LegacyImportError(
                f"SQLite row {table}:{row_id} has an invalid timestamp in column '{column}'."
            ) from exc
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw)
                parsed = datetime(parsed_date.year, parsed_date.month, parsed_date.day)
            except ValueError as exc:
                raise LegacyImportError(
                    f"SQLite row {table}:{row_id} has an invalid timestamp in column '{column}'."
                ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _convert_value(value: Any, column, *, table: str, row_id: str) -> Any:
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, JSONType):
        return _parse_json(value, table=table, column=column.name, row_id=row_id)
    if isinstance(column_type, Boolean):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0", ""}:
                return False
        if value in (0, 1, False, True):
            return bool(value)
        raise LegacyImportError(f"SQLite row {table}:{row_id} has an invalid boolean in column '{column.name}'.")
    if isinstance(column_type, DateTime):
        return _parse_datetime(value, table=table, column=column.name, row_id=row_id)
    if isinstance(column_type, Date):
        return _parse_datetime(value, table=table, column=column.name, row_id=row_id).date()
    if isinstance(column_type, Numeric):
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise InvalidOperation
            scale = int(column_type.scale or 0)
            precision = int(column_type.precision or 38)
            quantum = Decimal(1).scaleb(-scale)
            normalized = number.quantize(quantum, rounding=ROUND_HALF_EVEN)
            if normalized != number:
                float_storage_tolerance = Decimal("0.00000001")
                if not isinstance(value, float) or abs(normalized - number) > float_storage_tolerance:
                    raise LegacyImportError(
                        f"SQLite row {table}:{row_id} has excess decimal precision in column '{column.name}'."
                    )
            if abs(normalized) >= Decimal(10) ** (precision - scale):
                raise LegacyImportError(
                    f"SQLite row {table}:{row_id} exceeds the target range in column '{column.name}'."
                )
            return normalized
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise LegacyImportError(f"SQLite row {table}:{row_id} has an invalid number in column '{column.name}'.") from exc
    if isinstance(column_type, Integer):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number != number.to_integral_value():
                raise InvalidOperation
            return int(number)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise LegacyImportError(f"SQLite row {table}:{row_id} has an invalid integer in column '{column.name}'.") from exc
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LegacyImportError(f"SQLite row {table}:{row_id} has invalid UTF-8 in column '{column.name}'.") from exc
    declared_length = getattr(column_type, "length", None)
    if isinstance(column_type, String) and declared_length and declared_length > 0 and len(str(value)) > declared_length:
        raise LegacyImportError(f"SQLite row {table}:{row_id} exceeds the target length for column '{column.name}'.")
    if isinstance(column_type, (String, Text)):
        return str(value)
    return value


def _user_values(row: sqlite3.Row, *, password_policy: str, dry_run: bool, hasher: PasswordHasher) -> dict[str, Any]:
    row_id = str(row["id"])
    username = normalize_username(str(row["username"] or ""))
    if not is_valid_username(username):
        raise LegacyImportError(f"Legacy user row {row_id} has an invalid username; no account data was imported.")

    role = str(row["role"] or "")
    if role not in ROLES:
        raise LegacyImportError(f"Legacy user row {row_id} has an unsupported role.")
    permissions = _parse_json(row["permissions"], table="users", column="permissions", row_id=row_id)
    if permissions is None:
        permissions = []
    if not isinstance(permissions, list) or any(not isinstance(item, str) for item in permissions):
        raise LegacyImportError(f"Legacy user row {row_id} has an invalid permission list.")
    permission_set = set(permissions)
    if not permission_set.issubset(set(PERMISSIONS)):
        raise LegacyImportError(f"Legacy user row {row_id} contains an unmapped permission.")
    if not permission_set.issubset(ROLE_PERMISSION_LIMITS[role]):
        raise LegacyImportError(f"Legacy user row {row_id} grants permissions outside its role limit.")

    legacy_password = row["password"]
    if password_policy == "hash" and legacy_password not in (None, ""):
        password_material = str(legacy_password)
    else:
        password_material = secrets.token_urlsafe(48)
    password_hash = "dry-run-not-stored" if dry_run else hasher.hash(password_material)
    now = utc_now()
    return {
        "id": row_id,
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "permissions": sorted(permission_set),
        "is_active": True,
        "force_password_change": True,
        "auth_version": 1,
        "active_break_id": str(row["activeBreakId"]) if row["activeBreakId"] is not None else None,
        "auto_enter_after_scan": bool(row["auto_enter_after_scan"]),
        "created_at": now,
        "updated_at": now,
    }


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: _normalize_for_compare(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_for_compare(item) for item in value]
    return value


def _same_existing_row(table_name: str, existing, incoming: dict[str, Any]) -> bool:
    if table_name == "users":
        stable_fields = (
            "id",
            "username",
            "role",
            "permissions",
            "active_break_id",
            "auto_enter_after_scan",
        )
    else:
        stable_fields = tuple(incoming)
    return all(
        _normalize_for_compare(existing[field]) == _normalize_for_compare(incoming[field])
        for field in stable_fields
    )


def _decimal_sum(values: list[Any]) -> Decimal:
    total = Decimal(0)
    for value in values:
        if value is None:
            continue
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise LegacyImportError("A migrated financial total contains an invalid number.") from exc
        if not number.is_finite():
            raise LegacyImportError("A migrated financial total contains a non-finite number.")
        total += number
    return total


def _format_omr(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN), "f")


def _payment_total(rows: list[dict[str, Any]], table_name: str) -> tuple[Decimal, int]:
    amounts: list[Any] = []
    payment_count = 0
    for row in rows:
        payments = row.get("payments")
        if payments is None:
            continue
        if not isinstance(payments, list):
            raise LegacyImportError(f"{table_name}.payments must be a JSON array for reconciliation.")
        for payment in payments:
            if not isinstance(payment, dict) or payment.get("amount") is None:
                raise LegacyImportError(f"{table_name}.payments contains a record without a numeric amount.")
            amounts.append(payment["amount"])
            payment_count += 1
    return _decimal_sum(amounts), payment_count


def _financial_reconciliation(rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    orders = rows_by_table.get("orders", [])
    demand_notices = rows_by_table.get("demand_notices", [])
    products = rows_by_table.get("products", [])
    counters = rows_by_table.get("invoice_number_settings", [])
    order_payments, order_payment_count = _payment_total(orders, "orders")
    notice_payments, notice_payment_count = _payment_total(demand_notices, "demand_notices")
    return {
        "orders": {
            "rows": len(orders),
            "subtotal_omr": _format_omr(_decimal_sum([row.get("subtotal") for row in orders])),
            "discount_omr": _format_omr(_decimal_sum([row.get("discount_amount") for row in orders])),
            "total_omr": _format_omr(_decimal_sum([row.get("total_amount") for row in orders])),
        },
        "payments": {
            "order_rows": order_payment_count,
            "order_total_omr": _format_omr(order_payments),
            "demand_notice_rows": notice_payment_count,
            "demand_notice_total_omr": _format_omr(notice_payments),
            "combined_total_omr": _format_omr(order_payments + notice_payments),
        },
        "stock": {
            "product_rows": len(products),
            "quantity_total": sum(int(row.get("quantity_in_stock") or 0) for row in products),
        },
        "invoice_counters": {
            "rows": len(counters),
            "next_number_total": sum(int(row.get("next_number") or 0) for row in counters),
        },
    }


def _target_rows_for_ids(connection, table, source_rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not source_rows:
        return []
    result: list[dict[str, Any]] = []
    ids = [row["id"] for row in source_rows]
    columns = [table.c[field] for field in fields]
    for offset in range(0, len(ids), 500):
        chunk = ids[offset : offset + 500]
        rows = connection.execute(select(*columns).where(table.c.id.in_(chunk))).mappings().all()
        result.extend(dict(row) for row in rows)
    if len(result) != len(source_rows):
        raise LegacyImportError(f"Target row counts do not reconcile for table '{table.name}'.")
    return result


def _validate_target_payloads(connection, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
    for table_name, source_rows in rows_by_table.items():
        table = User.__table__ if table_name == "users" else legacy_tables[table_name]
        fields = tuple(table.c.keys())
        target_rows = _target_rows_for_ids(connection, table, source_rows, fields)
        by_id = {row["id"]: row for row in target_rows}
        for source_row in source_rows:
            target_row = by_id.get(source_row["id"])
            if target_row is None or not _same_existing_row(table_name, target_row, source_row):
                raise LegacyImportError(
                    f"Imported payload does not reconcile for table '{table_name}'; transaction rolled back."
                )


def _validate_target_foreign_keys(connection, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
    for table_name, source_rows in rows_by_table.items():
        child_table = User.__table__ if table_name == "users" else legacy_tables[table_name]
        for constraint in child_table.foreign_key_constraints:
            for element in constraint.elements:
                child_name = element.parent.name
                referenced_column = element.column
                values = {
                    row[child_name]
                    for row in source_rows
                    if row.get(child_name) is not None
                }
                if not values:
                    continue
                found: set[Any] = set()
                values_list = list(values)
                for offset in range(0, len(values_list), 500):
                    chunk = values_list[offset : offset + 500]
                    found.update(
                        connection.execute(
                            select(referenced_column).where(referenced_column.in_(chunk))
                        ).scalars()
                    )
                if values - found:
                    raise LegacyImportError(
                        f"Target foreign-key reconciliation failed for '{table_name}.{child_name}'."
                    )


def _target_reconciliation(connection, rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    target_rows: dict[str, list[dict[str, Any]]] = {}
    specifications = {
        "orders": ("id", "subtotal", "discount_amount", "total_amount", "payments"),
        "demand_notices": ("id", "payments"),
        "products": ("id", "quantity_in_stock"),
        "invoice_number_settings": ("id", "next_number"),
    }
    for table_name, fields in specifications.items():
        target_rows[table_name] = _target_rows_for_ids(
            connection,
            legacy_tables[table_name],
            rows_by_table[table_name],
            fields,
        )
    return _financial_reconciliation(target_rows)


def import_sqlite_database(
    source_path: str | Path,
    *,
    apply: bool = False,
    password_policy: str = "reset",
    allow_non_mysql_target: bool = False,
) -> ImportReport:
    """Preflight and optionally apply the reviewed 27-table SQLite import.

    ``allow_non_mysql_target`` exists for isolated SQLite unit tests only. The
    Flask CLI never enables it; real imports must target MySQL/MariaDB.
    """
    if password_policy not in {"reset", "hash"}:
        raise LegacyImportError("Password policy must be either 'reset' or 'hash'.")

    source = _open_sqlite_snapshot(source_path)
    hasher = PasswordHasher()
    try:
        source_columns = _validate_source_schema(source)
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        report = ImportReport(dry_run=not apply)
        normalized_usernames: set[str] = set()

        for table_name in IMPORT_ORDER:
            target = User.__table__ if table_name == "users" else legacy_tables[table_name]
            if table_name == "users":
                query_columns = source_columns[table_name]
            else:
                query_columns = source_columns[table_name]
            query = (
                f"SELECT {', '.join(_quote_identifier(name) for name in query_columns)} "
                f"FROM {_quote_identifier(table_name)}"
            )
            source_rows = source.execute(query).fetchall()
            report.source_counts[table_name] = len(source_rows)
            converted_rows: list[dict[str, Any]] = []

            for source_row in source_rows:
                row_id = str(source_row["id"])
                if table_name == "users":
                    if password_policy == "hash" and source_row["password"] not in (None, ""):
                        report.user_passwords_hashed += 1
                    else:
                        report.user_passwords_reset += 1
                    converted = _user_values(
                        source_row,
                        password_policy=password_policy,
                        dry_run=not apply,
                        hasher=hasher,
                    )
                    username = converted["username"]
                    if username in normalized_usernames:
                        raise LegacyImportError("Legacy source contains duplicate normalized usernames.")
                    normalized_usernames.add(username)
                else:
                    converted = {}
                    source_to_target = {_snake_case(name): name for name in source_columns[table_name]}
                    for target_name, column in target.c.items():
                        source_name = source_to_target.get(target_name)
                        if source_name is None:
                            raise LegacyImportError(f"No reviewed source column mapping exists for {table_name}.{target_name}.")
                        value = source_row[source_name]
                        converted[target_name] = _convert_value(
                            value,
                            column,
                            table=table_name,
                            row_id=row_id,
                        )
                    if converted.get("id") in (None, ""):
                        raise LegacyImportError(f"SQLite row in table '{table_name}' is missing its ID.")
                converted_rows.append(converted)

            rows_by_table[table_name] = converted_rows
            report.inserted_counts[table_name] = 0
            report.skipped_counts[table_name] = 0

        source_reconciliation = _financial_reconciliation(rows_by_table)
        report.reconciliation = source_reconciliation
        if not apply:
            return report

        dialect = db.engine.dialect.name
        if dialect not in {"mysql", "mariadb"} and not allow_non_mysql_target:
            raise LegacyImportError("Applying this importer requires a MySQL or MariaDB target database.")

        deferred_order_links: list[tuple[str, str]] = []
        with db.engine.begin() as connection:
            for table_name in IMPORT_ORDER:
                target = User.__table__ if table_name == "users" else legacy_tables[table_name]
                rows = rows_by_table[table_name]
                for incoming in rows:
                    incoming_for_compare = incoming
                    insert_values = dict(incoming)
                    if table_name == "orders" and incoming.get("linked_demand_notice_id") is not None:
                        deferred_order_links.append((incoming["id"], incoming["linked_demand_notice_id"]))
                        insert_values["linked_demand_notice_id"] = None

                    existing = connection.execute(
                        select(target).where(target.c.id == incoming["id"])
                    ).mappings().first()
                    if existing is not None:
                        if not _same_existing_row(table_name, existing, incoming_for_compare):
                            raise LegacyImportError(
                                f"Target row conflict at {table_name}:{incoming['id']}; transaction rolled back without overwriting it."
                            )
                        report.skipped_counts[table_name] += 1
                        continue

                    connection.execute(insert(target).values(**insert_values))
                    report.inserted_counts[table_name] += 1

            for order_id, demand_notice_id in deferred_order_links:
                connection.execute(
                    update(legacy_tables["orders"])
                    .where(legacy_tables["orders"].c.id == order_id)
                    .values(linked_demand_notice_id=demand_notice_id)
                )

            _validate_target_payloads(connection, rows_by_table)
            _validate_target_foreign_keys(connection, rows_by_table)
            target_reconciliation = _target_reconciliation(connection, rows_by_table)
            if target_reconciliation != source_reconciliation:
                raise LegacyImportError("Financial, stock, payment, or document-counter totals do not reconcile; transaction rolled back.")
            report.reconciliation = target_reconciliation

        return report
    except sqlite3.Error as exc:
        raise LegacyImportError("The SQLite source could not be read or validated.") from exc
    finally:
        source.close()
