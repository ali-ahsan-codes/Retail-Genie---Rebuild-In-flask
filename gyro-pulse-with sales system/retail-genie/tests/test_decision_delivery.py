import hashlib
import pytest
from test_field_catalog import native
from test_field_orders import staged
from retail_genie.extensions import db
from retail_genie.field_orders import review
from retail_genie.field_mobile import (
    decision_record,
    publish_decisions,
    DecisionDelivery,
)
from retail_genie.field_integration import FieldConnection
from retail_genie.sync_core import canonical


@pytest.mark.parametrize("approve", [True, False])
def test_durable_decision_publication_after_review_and_retry(
    staged, monkeypatch, approve
):
    app, company, _, _, actor, _, _, proposal = staged
    with pytest.raises(ValueError):
        decision_record(company.id, proposal.id)
    with app.test_request_context():
        review(
            actor,
            company.id,
            proposal.id,
            approve=approve,
            reason=None if approve else "synthetic rejection",
        )
    record = decision_record(company.id, proposal.id)
    connection = db.session.get(FieldConnection, company.id)
    connection.base_url = "https://cloud.example.test"
    connection.credential_encrypted = "test encrypted stub"
    db.session.commit()
    import retail_genie.field_mobile as mobile

    class Cipher:
        def decrypt(self, value):
            return b"synthetic-office-token"

    monkeypatch.setattr(mobile, "cipher", lambda: Cipher())
    monkeypatch.setattr(
        mobile, "trusted_origins", lambda: {"https://cloud.example.test"}
    )
    calls = []

    def send(base, path, headers, payload):
        calls.append(payload)
        assert path == "/api/v1/devices/decisions" and payload == record
        return dict(
            schema_version=1,
            order_id=record["order_id"],
            record_sha256=hashlib.sha256(canonical(record).encode()).hexdigest(),
            status="decision_received",
        )

    monkeypatch.setattr(
        mobile,
        "cloud_request",
        lambda *args: (_ for _ in ()).throw(OSError("synthetic outage")),
    )
    with pytest.raises(OSError):
        publish_decisions(company.id)
    db.session.rollback()
    assert DecisionDelivery.query.count() == 1
    assert not DecisionDelivery.query.one().acknowledged
    monkeypatch.setattr(mobile, "cloud_request", send)
    assert publish_decisions(company.id)["decisions_acknowledged"] == 1
    assert (
        publish_decisions(company.id)["decisions_acknowledged"] == 0 and len(calls) == 1
    )
