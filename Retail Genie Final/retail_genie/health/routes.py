"""Unauthenticated liveness and database-readiness probes."""

from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def liveness():
    return jsonify(status="ok"), 200


@health_bp.get("/readyz")
def readiness():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(status="unavailable", database="unavailable"), 503
    return jsonify(status="ready", database="ok"), 200
