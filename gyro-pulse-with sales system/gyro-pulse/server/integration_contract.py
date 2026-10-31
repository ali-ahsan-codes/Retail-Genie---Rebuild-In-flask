"""Versioned pairing contract: metadata by default; transport requires separate admin approval."""

import ipaddress
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

SCOPES = ["connection:read"]
BUNDLE_FIELDS = {
    "schema_version",
    "company_id",
    "instance_id",
    "office_id",
    "base_url",
    "grant_id",
    "pairing_code",
    "expires_at",
    "scopes",
}


def uid(value):
    if not isinstance(value, str):
        raise ValueError("canonical_uuid_required")
    parsed = UUID(value)
    if str(parsed) != value or not parsed.int:
        raise ValueError("canonical_uuid_required")
    return value


def origin(value):
    if (
        not isinstance(value, str)
        or len(value) > 300
        or any(ord(c) <= 32 for c in value)
        or "?" in value
        or "#" in value
    ):
        raise ValueError("https_origin_required")
    p = urlsplit(value)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username is not None
        or p.password is not None
        or p.path not in {"", "/"}
        or (p.port is not None and not 1 <= p.port <= 65535)
    ):
        raise ValueError("https_origin_required")
    if "%" in p.hostname:
        raise ValueError("invalid_hostname")
    try:
        ipaddress.ip_address(p.hostname)
    except ValueError:
        if len(p.hostname) > 253 or not all(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", part)
            for part in p.hostname.split(".")
        ):
            raise ValueError("invalid_hostname")
    return value.rstrip("/")


def valid_scopes(value):
    return isinstance(value, list) and value in (
        SCOPES,
        SCOPES + ["transport:exchange"],
    )


def loads(raw, limit=16384):
    if not isinstance(raw, (bytes, str)) or len(raw) > limit:
        raise ValueError("invalid_size")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("nonfinite_json")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (RecursionError, UnicodeError):
        raise ValueError("invalid_json") from None
