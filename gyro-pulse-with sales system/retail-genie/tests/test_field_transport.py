from test_field_integration import office, reply
from retail_genie import field_transport as worker
from retail_genie import field_integration as field
from retail_genie.sync_core import Transport, Inbox, Outbox, ProtocolError
from retail_genie.extensions import db
import pytest


@pytest.fixture
def connected(office, monkeypatch):
    app, row, bundle = office
    for model in [Inbox, Outbox]:
        model.__table__.create(db.engine)
    response = reply(bundle)
    monkeypatch.setattr(field, "exchange_http", lambda *args: response)
    field.enroll(row, bundle)
    yield app, row, bundle
    for model in [Inbox, Outbox]:
        model.__table__.drop(db.engine)


def test_worker_no_network_to_untrusted_origin(connected, monkeypatch):
    app, row, _ = connected
    app.config["FIELD_GYRO_ALLOWED_ORIGINS"] = "https://other.example.test"
    calls = []
    monkeypatch.setattr(worker, "cloud_request", lambda *args: calls.append(args))
    with pytest.raises(ProtocolError):
        worker.sync_once(row.company_id)
    assert not calls


def test_worker_requires_explicit_transport_and_no_write_on_metadata_status(
    connected, monkeypatch
):
    _, row, _ = connected

    def request(*args):
        return dict(
            schema_version=1,
            company_id=row.company_id,
            instance_id=row.instance_id,
            office_id=row.office_id,
            credential_id=row.credential_id,
            scopes=["connection:read"],
        )

    monkeypatch.setattr(worker, "cloud_request", request)
    with pytest.raises(ProtocolError):
        worker.sync_once(row.company_id)
    assert Inbox.query.count() == 0


def test_bidirectional_worker_roundtrip_with_fake_https(connected, monkeypatch):
    _, row, _ = connected
    ids = (row.company_id, row.instance_id, row.office_id)
    native = Transport("retail", *ids)
    cloud = Transport("gyro", *ids)
    native.enqueue(native.envelope("catalog.snapshot", {"items": []}))
    db.session.commit()
    order = cloud.envelope("field.order", {"lines": []})
    lease = "a0c997dd-51b3-4e66-99e0-241606cdb268"
    delivered = [False]
    acked = []
    paths = []

    def request(base, path, headers, payload=None):
        paths.append(path)
        assert base == "https://cloud.example.test"
        assert headers["Authorization"].startswith("Bearer ")
        if path.endswith("/status"):
            return dict(
                schema_version=1,
                company_id=ids[0],
                instance_id=ids[1],
                office_id=ids[2],
                credential_id=row.credential_id,
                scopes=["connection:read", "transport:exchange"],
            )
        if path.endswith("/messages"):
            receipt = cloud.accept(payload)
            db.session.commit()
            return receipt
        if path.endswith("/pull"):
            if delivered[0]:
                return {"message": None}
            delivered[0] = True
            return {
                "message": dict(
                    message_id=order["message_id"], lease_token=lease, envelope=order
                )
            }
        if path.endswith("/ack"):
            # Native receipt persisted before sending its ACK.
            assert db.session.get(Inbox, order["message_id"]) is not None
            acked.append(payload)
            return {"status": "acknowledged"}
        raise AssertionError("Unexpected path")

    monkeypatch.setattr(worker, "cloud_request", request)
    assert worker.sync_once(row.company_id) == {
        "acknowledged": 1,
        "retry_or_dead": 0,
        "received": 1,
    }
    assert len(acked) == 1 and acked[0]["receipt"]["status"] == "received"
    assert Outbox.query.one().state == "acknowledged"
