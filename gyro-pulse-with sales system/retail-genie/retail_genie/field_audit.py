"""Read-only restore/linked-decision consistency audit. Never repairs or posts sales."""

import json
import click
from .extensions import db
from .field_orders import FieldProposal, FieldReviewAudit
from .models import SalesOrder


def audit_company(company_id):
    issues = []
    rows = FieldProposal.query.filter_by(company_id=company_id).all()
    for row in rows:
        audits = FieldReviewAudit.query.filter_by(
            company_id=company_id, proposal_id=row.id
        ).all()
        if row.state == "approved":
            order = (
                db.session.get(SalesOrder, row.native_order_id)
                if row.native_order_id
                else None
            )
            if order is None:
                issues.append(dict(proposal_id=row.id, code="missing_native_order"))
            elif (order.company_id, order.origin_store_id) != (
                row.company_id,
                row.store_id,
            ):
                issues.append(dict(proposal_id=row.id, code="native_scope_mismatch"))
            if (
                len(audits) != 1
                or audits[0].action != "approved"
                or audits[0].native_order_id != row.native_order_id
            ):
                issues.append(dict(proposal_id=row.id, code="approval_audit_mismatch"))
        elif row.state == "rejected":
            if (
                row.native_order_id
                or len(audits) != 1
                or audits[0].action != "rejected"
            ):
                issues.append(dict(proposal_id=row.id, code="rejection_audit_mismatch"))
        elif row.state == "pending":
            if row.native_order_id or audits:
                issues.append(
                    dict(proposal_id=row.id, code="pending_has_posting_or_decision")
                )
        else:
            issues.append(dict(proposal_id=row.id, code="invalid_state"))
    return dict(
        schema_version=1,
        company_id=company_id,
        proposals_checked=len(rows),
        consistent=not issues,
        issues=issues,
        automatic_repair=False,
        production_accepted=False,
    )


def register(app):
    @app.cli.command("field-order-audit")
    @click.option("--company-id", required=True)
    def audit(company_id):
        result = audit_company(company_id)
        click.echo(json.dumps(result, sort_keys=True))
        if not result["consistent"]:
            raise click.ClickException(
                "Linked proposal/native decision consistency failed. Do not replay/repair automatically."
            )
