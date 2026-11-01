import pytest
from test_field_catalog import native
from test_field_orders import staged
from retail_genie.extensions import db
from retail_genie.field_orders import review, FieldProposal
from retail_genie.field_audit import audit_company


def test_audit_accepts_linked_native_decision_and_detects_broken_restore(staged):
    app, company, _, _, actor, _, _, proposal = staged
    assert audit_company(company.id)["consistent"]
    with app.test_request_context():
        review(actor, company.id, proposal.id, approve=True)
    assert audit_company(company.id)["consistent"]
    row = FieldProposal.query.one()
    row.native_order_id = "missing-after-bad-restore"
    db.session.commit()
    report = audit_company(company.id)
    assert not report["consistent"] and not report["automatic_repair"]
    assert any(item["code"] == "missing_native_order" for item in report["issues"])
