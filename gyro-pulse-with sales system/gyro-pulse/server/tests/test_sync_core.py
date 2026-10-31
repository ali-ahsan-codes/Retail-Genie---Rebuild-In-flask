"""SQLite durable transport tests; NOT live MySQL/TLS/mobile acceptance."""

from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from flask import Flask
from sync_core import (
    db,
    Inbox,
    Outbox,
    Transport,
    Conflict,
    ProtocolError,
    decode,
    MAX_ATTEMPTS,
    MAX_BYTES,
)


@pytest.fixture
def pair():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False
    )
    db.init_app(app)
    with app.app_context():
        for model in [Inbox, Outbox]:
            model.__table__.create(db.engine)
        ids = [str(uuid4()) for _ in range(3)]
        yield Transport("retail", *ids), Transport("gyro", *ids)
        db.session.remove()
        for model in [Inbox, Outbox]:
            model.__table__.drop(db.engine)


def fresh(row):
    db.session.expire_all()
    return db.session.get(type(row), row.id)


def test_lost_ack_retry_and_duplicate_delivery(pair):
    office, cloud = pair
    env = office.envelope("catalog.snapshot", {"items": []})
    row = office.enqueue(env)
    db.session.commit()
    now = datetime.utcnow() + timedelta(seconds=1)
    message, token, payload = office.claim(now=now)[0]
    db.session.commit()
    first = cloud.accept(payload)
    db.session.commit()  # receiver committed but response lost
    office.failed(message, token, now=now)
    db.session.commit()
    assert office.claim(now=now + timedelta(seconds=1)) == []
    message, new_token, payload = office.claim(now=now + timedelta(seconds=3))[0]
    db.session.commit()
    second = cloud.accept(payload)
    db.session.commit()
    assert second == first and Inbox.query.count() == 1
    office.acknowledge(message, new_token, second, now=now + timedelta(seconds=3))
    db.session.commit()
    assert fresh(row).state == "acknowledged" and fresh(row).attempts == 2
    assert office.claim(now=now + timedelta(days=1)) == []


def test_idempotent_enqueue_and_conflicting_reuse(pair):
    office, cloud = pair
    env = office.envelope("catalog.snapshot", {"items": []})
    first = office.enqueue(env)
    db.session.commit()
    assert office.enqueue(env).id == first.id
    with pytest.raises(Conflict):
        office.enqueue({**env, "payload": {"items": [1]}})
    assert Outbox.query.count() == 1
    cloud.accept(env)
    db.session.commit()
    with pytest.raises(Conflict):
        cloud.accept({**env, "payload": {"items": [1]}})
    assert Inbox.query.count() == 1


def test_enqueue_rollback_and_accept_rollback(pair):
    office, cloud = pair
    env = office.envelope("catalog.snapshot", {})
    # Explicit outer transaction: source changes and outbox can commit or roll back together.
    office.enqueue(env)
    db.session.rollback()
    assert Outbox.query.count() == 0
    db.session.rollback()
    cloud.accept(env)
    db.session.rollback()
    assert Inbox.query.count() == 0


def test_restart_and_stale_worker_fencing(pair):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()
    now = datetime.utcnow() + timedelta(seconds=1)
    mid, old, payload = office.claim(now=now, lease_seconds=10)[0]
    db.session.commit()
    db.session.remove()  # process/session restart; lease is persistent, not memory state
    assert office.claim(now=now + timedelta(seconds=9)) == []
    mid, current, payload = office.claim(now=now + timedelta(seconds=11))[0]
    db.session.commit()
    receipt = cloud.accept(payload)
    db.session.commit()
    with pytest.raises(Conflict):
        office.acknowledge(mid, old, receipt, now=now + timedelta(seconds=11))
    with pytest.raises(Conflict):
        office.failed(mid, old, now=now + timedelta(seconds=11))
    office.acknowledge(mid, current, receipt, now=now + timedelta(seconds=11))
    db.session.commit()
    assert db.session.get(Outbox, mid).state == "acknowledged"


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_id", str(uuid4())),
        ("instance_id", str(uuid4())),
        ("office_id", str(uuid4())),
        ("status", "applied"),
        ("envelope_sha256", "0" * 64),
        ("schema_version", True),
        ("recipient", "retail"),
    ],
)
def test_wrong_receipt_cannot_acknowledge(pair, field, value):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()
    mid, token, payload = office.claim()[0]
    db.session.commit()
    receipt = cloud.accept(payload)
    db.session.commit()
    with pytest.raises(ProtocolError):
        office.acknowledge(mid, token, {**receipt, field: value})
    assert fresh(row).state == "leased"


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_id", str(uuid4())),
        ("instance_id", str(uuid4())),
        ("office_id", str(uuid4())),
        ("schema_version", True),
        ("kind", "stock.adjustment"),
        ("recipient", "retail"),
        ("payload", []),
    ],
)
def test_wrong_envelope_no_receipt(pair, field, value):
    office, cloud = pair
    env = office.envelope("catalog.snapshot", {})
    with pytest.raises(ProtocolError):
        cloud.accept({**env, field: value})
    assert Inbox.query.count() == 0


def test_retry_limit_dead_letter_and_no_silent_requeue(pair):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()
    now = datetime.utcnow() + timedelta(seconds=1)
    for attempt in range(MAX_ATTEMPTS):
        mid, token, _ = office.claim(now=now)[0]
        db.session.commit()
        office.failed(mid, token, now=now)
        db.session.commit()
        now += timedelta(hours=2)
    assert fresh(row).state == "dead" and row.attempts == MAX_ATTEMPTS
    assert office.claim(now=now) == []


def test_crash_on_last_attempt_eventually_dead_letters(pair):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()
    now = datetime.utcnow() + timedelta(seconds=1)
    for _ in range(MAX_ATTEMPTS):
        assert len(office.claim(now=now, lease_seconds=1)) == 1
        db.session.commit()
        now += timedelta(seconds=2)
    assert office.claim(now=now) == []
    assert fresh(row).state == "dead"


def test_worker_commit_before_network_and_durable_receipt(pair):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()

    def send(env):
        assert fresh(row).state == "leased"
        receipt = cloud.accept(env)
        db.session.commit()
        return receipt

    assert office.deliver_batch(send) == {"acknowledged": 1, "retry_or_dead": 0}
    assert fresh(row).state == "acknowledged"


def test_worker_retry_and_invalid_receipt_quarantine(pair):
    office, cloud = pair
    row = office.enqueue(office.envelope("catalog.snapshot", {}))
    db.session.commit()

    def offline(env):
        raise TimeoutError("not persisted or logged")

    assert office.deliver_batch(offline)["retry_or_dead"] == 1
    assert fresh(row).state == "pending" and row.error_code == "delivery_error"
    row.available_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert office.deliver_batch(lambda _: {"status": "approved"})["retry_or_dead"] == 1
    assert fresh(row).state == "dead" and row.error_code == "protocol_rejected"


def test_native_order_direction_and_identity_isolation(pair):
    office, cloud = pair
    env = cloud.envelope("field.order", {"lines": []})
    cloud.enqueue(env)
    db.session.commit()
    receipt = office.accept(env)
    db.session.commit()
    assert receipt["status"] == "received"
    foreign = Transport("retail", str(uuid4()), str(uuid4()), str(uuid4()))
    assert foreign.claim() == []
    with pytest.raises(ProtocolError):
        foreign.accept(env)
    with pytest.raises(ProtocolError):
        cloud.envelope("catalog.snapshot", {})


@pytest.mark.parametrize("value", [float("nan"), 1.2, 2**54, {"a": "x" * MAX_BYTES}])
def test_unsafe_or_large_payload_rejected(pair, value):
    office, _ = pair
    with pytest.raises(ProtocolError):
        office.envelope("catalog.snapshot", {"value": value})


def test_duplicate_json_and_worker_bounds(pair):
    office, _ = pair
    with pytest.raises(ProtocolError):
        decode('{"a":1,"a":2}')
    with pytest.raises(ProtocolError):
        office.claim(limit=101)
    with pytest.raises(ProtocolError):
        office.claim(lease_seconds=0)
