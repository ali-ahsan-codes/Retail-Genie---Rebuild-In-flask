"""Native field-order staging and explicit human review.
Native POS remains sole writer. Its before-commit callback atomically stores the business-ID
mapping and review audit with the native order/stock changes. No integration stock writer.
"""

import hashlib
from datetime import datetime
from decimal import Decimal
import click
from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .field_integration import FieldConnection
from .models import CatalogProduct, Company, Store
from .order_contract import validate, OrderError
from .sync_core import Inbox, Transport, decode, canonical
from .sales import service as sales

bp = Blueprint("field_orders", __name__)


class FieldProposal(db.Model):
    __tablename__ = "hybrid_field_proposals"
    company_id = db.Column(db.String(36), primary_key=True)
    id = db.Column(db.String(36), primary_key=True)
    instance_id = db.Column(db.String(36), nullable=False)
    office_id = db.Column(db.String(36), nullable=False)
    store_id = db.Column(db.String(64), nullable=False)
    message_id = db.Column(db.String(36), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    payload_sha256 = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(20), nullable=False, default="pending")
    native_order_id = db.Column(db.String(64), unique=True)
    reviewed_by = db.Column(db.String(64))
    review_reason = db.Column(db.String(500))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    @property
    def quoted_total(self):
        return format(
            sum(
                (
                    Decimal(line["unit_price"]) * line["quantity"]
                    for line in self.payload["items"]
                ),
                Decimal("0"),
            ),
            ".3f",
        )


class FieldReviewAudit(db.Model):
    __tablename__ = "hybrid_field_review_audit"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    proposal_id = db.Column(db.String(36), nullable=False)
    actor_id = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    native_order_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def context_for(company_id):
    connection = db.session.get(FieldConnection, company_id)
    if not connection or not connection.instance_id:
        raise OrderError("Matching paired company required")
    return Transport("retail", company_id, connection.instance_id, connection.office_id)


def stage_message(company_id, message_id):
    context = context_for(company_id)
    row = context.scoped(Inbox).filter_by(id=message_id).first()
    if row is None:
        raise OrderError("Scoped inbox item required")
    envelope = decode(row.envelope)
    _, sha = context.validate(envelope, True)
    if sha != row.envelope_sha256 or envelope["kind"] != "field.order":
        raise OrderError("Corrupt/wrong inbox item")
    payload = validate(envelope["payload"])
    company = db.session.get(Company, company_id)
    store = (
        Store.query.filter_by(
            id=payload["store_id"],
            company_id=company_id,
            tenant_container_id=company.tenant_container_id,
            is_active=True,
        ).first()
        if company and company.is_active
        else None
    )
    if store is None:
        raise OrderError("Active native company/store required")
    payload_hash = hashlib.sha256(canonical(payload).encode()).hexdigest()
    old = db.session.get(FieldProposal, (company_id, payload["order_id"]))
    if old:
        if (old.instance_id, old.office_id) != context.identity[
            1:
        ] or old.payload_sha256 != payload_hash:
            raise OrderError("Conflicting business order ID")
        return old
    proposal = FieldProposal(
        company_id=company_id,
        id=payload["order_id"],
        instance_id=context.identity[1],
        office_id=context.identity[2],
        store_id=store.id,
        message_id=message_id,
        payload=payload,
        payload_sha256=payload_hash,
    )
    db.session.add(proposal)
    db.session.flush()
    return proposal


def authorize(actor, proposal):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or not actor.has_permission("approve_pos")
    ):
        raise sales.SalesRuleError(
            "Explicit active native approver required", 403, "permission_denied"
        )
    company = sales._company_for_actor(actor, proposal.company_id)
    store = sales._require_assigned_store(actor, proposal.store_id, company.id)
    sales._require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="view",
        company_id=company.id,
        store_id=store.id,
    )
    context = context_for(company.id)
    if (proposal.instance_id, proposal.office_id) != context.identity[1:]:
        raise OrderError("Proposal office binding mismatch")
    return company, store


def review(actor, company_id, proposal_id, *, approve, reason=None):
    if type(approve) is not bool:
        raise OrderError("Explicit decision required")
    proposal = (
        FieldProposal.query.filter_by(company_id=company_id, id=proposal_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if proposal is None:
        raise OrderError("No scoped proposal")
    company, store = authorize(actor, proposal)
    payload = validate(proposal.payload)
    if (
        hashlib.sha256(canonical(payload).encode()).hexdigest()
        != proposal.payload_sha256
        or payload["order_id"] != proposal.id
        or payload["store_id"] != proposal.store_id
    ):
        raise OrderError("Immutable proposal mismatch")
    if proposal.state != "pending":
        if approve and proposal.state == "approved":
            return proposal.native_order_id
        if not approve and proposal.state == "rejected":
            return None
        raise OrderError("Decision is final; resubmit a new business order ID")
    if not approve:
        if type(reason) is not str or not 1 <= len(reason.strip()) <= 500:
            raise OrderError("Bounded rejection reason required")
        _decision(proposal, actor, "rejected", None, reason.strip())
        db.session.commit()
        return None
    # Lock native products and compare exact price; no cloud price override or automatic repricing.
    total = Decimal("0")
    for line in payload["items"]:
        # Refresh a preloaded identity-map entry while locking the company-owned product.
        current = (
            CatalogProduct.query.filter_by(
                id=line["product_id"],
                company_id=company.id,
                tenant_container_id=company.tenant_container_id,
            )
            .with_for_update()
            .populate_existing()
            .first()
        )
        if current is None:
            raise OrderError("Company-owned native product required")
        product, quantity, price = sales._validated_catalog_line(
            actor,
            company,
            store,
            {"product_id": line["product_id"], "quantity": line["quantity"]},
        )
        if product.company_id != company.id or price != Decimal(line["unit_price"]):
            raise OrderError(
                "Native catalog changed; reject/refresh and submit a new proposal"
            )
        total += price * quantity

    def link_before_commit(order):
        # Native taxes/global discounts are NEVER overridden to fit the field quote.
        if Decimal(order.total_amount) != total:
            raise OrderError(
                "Native total differs from proposal; use native POS review instead"
            )
        _decision(proposal, actor, "approved", order.id, None)

    order = sales.create_order(
        actor,
        company_id=company.id,
        store_id=store.id,
        customer_phone=payload["customer_phone"],
        customer_name=payload["customer_name"],
        items=[
            {"product_id": line["product_id"], "quantity": line["quantity"]}
            for line in payload["items"]
        ],
        before_commit=link_before_commit,
    )
    return order.id


def _decision(proposal, actor, state, native_id, reason):
    changed = FieldProposal.query.filter_by(
        company_id=proposal.company_id,
        id=proposal.id,
        state="pending",
        payload_sha256=proposal.payload_sha256,
    ).update(
        dict(
            state=state,
            native_order_id=native_id,
            reviewed_by=actor.id,
            review_reason=reason,
            reviewed_at=datetime.utcnow(),
        ),
        synchronize_session="fetch",
    )
    if changed != 1:
        raise OrderError("Concurrent review; reload decision")
    db.session.add(
        FieldReviewAudit(
            company_id=proposal.company_id,
            proposal_id=proposal.id,
            actor_id=actor.id,
            action=state,
            native_order_id=native_id,
        )
    )
    db.session.flush()


@bp.after_request
def private_review(response):
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        }
    )
    return response


@bp.route("/settings/field-orders", methods=["GET", "POST"])
@login_required
def manage():
    from .settings.routes import _resolve_company

    company, _ = _resolve_company()
    if (
        company is None
        or not current_user.is_active
        or not current_user.has_permission("approve_pos")
    ):
        abort(403)
    if not all(
        inspect(db.engine).has_table(model.__tablename__)
        for model in [FieldProposal, FieldReviewAudit]
    ):
        return jsonify(error="Operator must initialize native field orders"), 503
    if request.method == "POST":
        decision = request.form.get("decision")
        if decision not in {"approve", "reject"}:
            return jsonify(error="Explicit decision required"), 400
        if decision == "approve" and request.form.get("confirm_native_prices") != "yes":
            return jsonify(error="Confirm native price/units review first"), 400
        try:
            review(
                current_user,
                company.id,
                request.form.get("proposal_id", ""),
                approve=decision == "approve",
                reason=request.form.get("reason"),
            )
        except (OrderError, sales.SalesRuleError, IntegrityError) as error:
            db.session.rollback()
            return jsonify(
                error="Review rejected; reload proposal/native price, stock, total and permissions. No partial posting committed."
            ), getattr(error, "status_code", 409)
    rows = (
        FieldProposal.query.filter_by(company_id=company.id)
        .order_by(FieldProposal.created_at.desc())
        .limit(200)
        .all()
    )
    visible = []
    for row in rows:
        try:
            authorize(current_user, row)
        except (sales.SalesRuleError, OrderError):
            continue
        visible.append(row)
    return render_template("field_orders.html", company=company, proposals=visible)


def register(app):
    app.register_blueprint(bp)

    @app.cli.command("init-field-orders")
    def initialize():
        for model in [FieldProposal, FieldReviewAudit]:
            model.__table__.create(db.engine, checkfirst=True)
        click.echo(
            "Native proposal/review tables ready; no automatic approval or posting."
        )

    @app.cli.command("field-order-stage")
    @click.option("--company-id", required=True)
    @click.option("--message-id", required=True)
    def stage(company_id, message_id):
        try:
            proposal = stage_message(company_id, message_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException(
                "Staging rejected. Inbox preserved; check scope, contract and business ID."
            ) from None
        click.echo(
            "Proposal "
            + proposal.id
            + " staged for explicit human review. No stock deducted."
        )
