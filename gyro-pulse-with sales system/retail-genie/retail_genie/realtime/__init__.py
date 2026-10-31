"""Permission-scoped Socket.IO delivery and durable event replay."""

from flask import Blueprint

realtime_bp = Blueprint("realtime", __name__)

from . import handlers as _handlers  # noqa: E402,F401
from . import routes as _routes  # noqa: E402,F401
