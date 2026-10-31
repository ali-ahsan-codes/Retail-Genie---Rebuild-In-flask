"""Immutable field-order proposal; delivery is never approval/payment."""

from decimal import Decimal
import re
from uuid import UUID
from .catalog_contract import text, price, CatalogError


class OrderError(ValueError):
    pass


def validate(payload):
    try:
        if (
            type(payload) is not dict
            or set(payload)
            != {
                "schema_version",
                "order_id",
                "store_id",
                "catalog_message_id",
                "customer_phone",
                "customer_name",
                "items",
            }
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
        ):
            raise ValueError()
        for key in ["order_id", "catalog_message_id"]:
            value = payload[key]
            if (
                type(value) is not str
                or str(UUID(value)) != value
                or not UUID(value).int
            ):
                raise ValueError()
        text(payload["store_id"], 64)
        phone = text(payload["customer_phone"], 64)
        if (
            not re.fullmatch(r"[+0-9 ()-]+", phone)
            or not 7 <= len(re.sub(r"\D", "", phone)) <= 15
        ):
            raise ValueError()
        text(payload["customer_name"], 160, nullable=True)
        lines = payload["items"]
        if type(lines) is not list or not 1 <= len(lines) <= 50:
            raise ValueError()
        ids = set()
        total = Decimal("0")
        for line in lines:
            if type(line) is not dict or set(line) != {
                "product_id",
                "quantity",
                "unit_price",
            }:
                raise ValueError()
            ident = text(line["product_id"], 64)
            if ident in ids:
                raise ValueError()
            ids.add(ident)
            if type(line["quantity"]) is not int or not 1 <= line["quantity"] <= 10000:
                raise ValueError()
            price(line["unit_price"])
            if line["unit_price"] is None or Decimal(line["unit_price"]) <= 0:
                raise ValueError()
            total += Decimal(line["unit_price"]) * line["quantity"]
        if total >= Decimal("100000000000"):
            raise ValueError()
        return payload
    except (ValueError, TypeError, KeyError, AttributeError, CatalogError):
        raise OrderError("Invalid immutable field-order contract") from None
