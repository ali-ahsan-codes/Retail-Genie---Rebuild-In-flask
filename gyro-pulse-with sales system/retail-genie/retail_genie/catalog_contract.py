"""Strict full-store catalog projection contract. Prices retain native units (currency unknown).
Never interprets on-hand as reservations/available-to-promise or writes a stock ledger.
"""

import re
from datetime import datetime

MAX_ITEMS = 200
FIELDS = {
    "schema_version",
    "mode",
    "store",
    "sequence",
    "captured_at",
    "currency",
    "items",
}
ITEM_FIELDS = {
    "id",
    "sku",
    "barcode",
    "name",
    "category",
    "active",
    "price",
    "low_stock_price",
    "on_hand",
    "low_stock_threshold",
}


class CatalogError(ValueError):
    pass


def text(value, limit, nullable=False):
    if value is None and nullable:
        return value
    if (
        type(value) is not str
        or not 1 <= len(value) <= limit
        or any(ord(c) < 32 for c in value)
    ):
        raise CatalogError("Invalid text field")
    return value


def price(value):
    if value is not None and (
        type(value) is not str
        or not re.fullmatch(r"(?:0|[1-9][0-9]{0,10})\.[0-9]{3}", value)
    ):
        raise CatalogError("Invalid exact price")


def validate(payload):
    if (
        type(payload) is not dict
        or set(payload) != FIELDS
        or type(payload["schema_version"]) is not int
        or payload["schema_version"] != 1
        or payload["mode"] != "full"
    ):
        raise CatalogError("Unsupported catalog schema")
    if (
        type(payload["sequence"]) is not int
        or not 1 <= payload["sequence"] <= 9007199254740991
    ):
        raise CatalogError("Invalid sequence")
    store = payload["store"]
    if type(store) is not dict or set(store) != {"id", "code", "name"}:
        raise CatalogError("Invalid store")
    text(store["id"], 64)
    text(store["code"], 48)
    text(store["name"], 160)
    if payload["currency"] is not None:
        raise CatalogError("Currency mapping not established")
    stamp = payload["captured_at"]
    if type(stamp) is not str or len(stamp) > 40 or not stamp.endswith("Z"):
        raise CatalogError("Invalid UTC capture time")
    try:
        parsed = datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError:
        raise CatalogError("Invalid UTC capture time") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise CatalogError("Invalid UTC capture time")
    items = payload["items"]
    if type(items) is not list or len(items) > MAX_ITEMS:
        raise CatalogError("Full snapshot exceeds pilot limit")
    seen = set()
    for item in items:
        if type(item) is not dict or set(item) != ITEM_FIELDS:
            raise CatalogError("Invalid product schema")
        ident = text(item["id"], 64)
        if ident in seen:
            raise CatalogError("Duplicate native product ID")
        seen.add(ident)
        text(item["name"], 500)
        for key in ["sku", "barcode", "category"]:
            text(item[key], 128, nullable=True)
        if type(item["active"]) is not bool:
            raise CatalogError("Invalid active flag")
        price(item["price"])
        price(item["low_stock_price"])
        if (
            type(item["on_hand"]) is not int
            or not -2147483648 <= item["on_hand"] <= 2147483647
        ):
            raise CatalogError("Invalid native stock count")
        threshold = item["low_stock_threshold"]
        if threshold is not None and (
            type(threshold) is not int or not -2147483648 <= threshold <= 2147483647
        ):
            raise CatalogError("Invalid native threshold")
    return payload
