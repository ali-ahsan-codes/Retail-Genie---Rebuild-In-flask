"""Build a same-LAN login URL for QR sharing without external services."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from flask import current_app, request, url_for


def _primary_lan_ipv4() -> str | None:
    """Ask the OS which local IPv4 route it would use for outbound traffic.

    UDP connect selects an interface and does not send an application packet.
    The reserved documentation address below is used only for route selection.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        address = probe.getsockname()[0]
        parsed = ipaddress.ip_address(address)
        if parsed.version == 4 and not parsed.is_loopback and not parsed.is_unspecified:
            return str(parsed)
    except (OSError, ValueError):
        return None
    finally:
        probe.close()
    return None


def app_login_url() -> str | None:
    """Return a safe login URL, honoring an operator-set public base URL first."""
    login_path = url_for("auth.login")
    configured = (current_app.config.get("PUBLIC_BASE_URL") or "").strip()
    if configured:
        parsed = urlsplit(configured)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        return f"{configured.rstrip('/')}{login_path}"

    host_url = urlsplit(request.host_url)
    hostname = host_url.hostname
    if not hostname:
        return None
    # Use the active LAN interface rather than trusting an arbitrary Host
    # header. The local runner's bound port is available from the WSGI environ;
    # reverse proxies/DNS deployments should set PUBLIC_BASE_URL explicitly.
    lan_ip = _primary_lan_ipv4()
    if not lan_ip:
        return None
    port = int(request.environ.get("SERVER_PORT") or current_app.config.get("FLASK_PORT", 5000))
    default_port = 443 if host_url.scheme == "https" else 80
    authority = lan_ip if port == default_port else f"{lan_ip}:{port}"
    return urlunsplit((host_url.scheme or "http", authority, login_path, "", ""))
