from datetime import datetime, timedelta, timezone

from retail_genie.extensions import db, socketio
from retail_genie.models import RealtimeEvent
from retail_genie.realtime.service import initialize_realtime_registry, realtime_dispatch_once


def _login(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _subscribe(app, client):
    socket_client = socketio.test_client(app, namespace="/retail", flask_test_client=client)
    acknowledgement = socket_client.emit("subscribe_store", {"store_id": "test-store"}, namespace="/retail", callback=True)
    assert acknowledgement["ok"] is True
    return socket_client


def _event(*, domain, event_type, created_at=None):
    return RealtimeEvent(
        tenant_container_id="test-container",
        company_id="test-company",
        store_id="test-store",
        domain=domain,
        event_type=event_type,
        payload={"status": "changed"},
        created_at=created_at or datetime.now(timezone.utc),
    )


def test_replay_includes_authorized_sales_and_inventory_domains(app, client, create_user):
    create_user(
        "replay.both-domains",
        role="manager",
        permissions=["inventory.view", "sales.view"],
    )
    _login(client, "replay.both-domains")
    with app.app_context():
        db.session.add_all([
            _event(domain="inventory", event_type="inventory.updated"),
            _event(domain="sales", event_type="sales.payment_recorded"),
        ])
        db.session.commit()

    response = client.get("/api/v1/realtime/events", query_string={"store_id": "test-store", "after_id": 0})
    assert response.status_code == 200
    events = response.get_json()["events"]
    assert [event["type"] for event in events] == ["inventory.updated", "sales.payment_recorded"]
    assert [event["domain"] for event in events] == ["inventory", "sales"]


def test_sales_domain_subscription_receives_sales_events(app, client, create_user):
    from retail_genie.realtime.service import publish_realtime_event

    create_user("sales.realtime", role="manager", permissions=["sales.view"])
    _login(client, "sales.realtime")
    stores_response = client.get("/api/v1/realtime/stores")
    assert stores_response.status_code == 200
    assert stores_response.get_json()["stores"] == ["test-store"]
    orders_page = client.get("/admin/orders")
    assert orders_page.status_code == 200
    assert b"js/sales-realtime.js" in orders_page.data
    socket_client = _subscribe(app, client)
    with app.app_context():
        event = _event(domain="sales", event_type="sales.order_changed")
        db.session.add(event)
        db.session.commit()
        assert publish_realtime_event(event.id) is True
        event_id = event.id

    received = socket_client.get_received("/retail")
    assert len(received) == 1
    assert received[0]["name"] == "sales.order_changed"
    assert received[0]["args"][0]["domain"] == "sales"
    assert received[0]["args"][0]["id"] == event_id
    socket_client.disconnect(namespace="/retail")


def test_replay_cursor_expiry_uses_per_domain_retention_floor(app, client, create_user):
    create_user(
        "replay.expired",
        role="manager",
        permissions=["inventory.view", "sales.view"],
    )
    _login(client, "replay.expired")
    old = datetime.now(timezone.utc) - timedelta(days=45)
    with app.app_context():
        db.session.add_all([
            _event(domain="inventory", event_type="inventory.updated", created_at=old),
            _event(domain="inventory", event_type="inventory.updated", created_at=old + timedelta(seconds=1)),
            _event(domain="sales", event_type="sales.order_changed", created_at=old),
            _event(domain="sales", event_type="sales.payment_recorded", created_at=old + timedelta(seconds=1)),
        ])
        db.session.commit()
        from retail_genie.realtime.service import prune_realtime_events

        assert prune_realtime_events(retention_days=30) == 2
        floors = db.session.query(RealtimeEvent.cursor_floor).filter(RealtimeEvent.cursor_floor.is_not(None)).all()
        assert len(floors) == 2

    response = client.get("/api/v1/realtime/events", query_string={"store_id": "test-store", "after_id": 0})
    assert response.status_code == 410
    assert response.get_json()["error"] == "cursor_expired"
    assert response.get_json()["minimum_cursor"] > 0


def test_dispatcher_overlap_finds_late_commit_behind_cursor(app, client, create_user):
    create_user("realtime.late-commit", role="manager", permissions=["inventory.view"])
    _login(client, "realtime.late-commit")
    socket_client = _subscribe(app, client)
    registry = app.extensions["retail_genie_realtime_subscriptions"]
    registry["cursor"] = 10
    registry["startup_cursor"] = 0
    with app.app_context():
        late_event = _event(domain="inventory", event_type="inventory.updated")
        late_event.id = 9
        db.session.add(late_event)
        db.session.commit()
        event_id = late_event.id

    assert realtime_dispatch_once(app) == 1
    received = socket_client.get_received("/retail")
    assert [item["args"][0]["id"] for item in received] == [event_id]
    socket_client.disconnect(namespace="/retail")


def test_access_revocation_outbox_reaches_recipient_after_scope_is_removed(app, client, create_user, monkeypatch):
    from retail_genie.realtime.service import publish_realtime_event, stage_access_revocation

    monkeypatch.setattr(socketio.server, "disconnect", lambda *_args, **_kwargs: None)
    create_user("access.revoked", role="manager", permissions=["inventory.view"])
    _login(client, "access.revoked")
    socket_client = _subscribe(app, client)
    with app.app_context():
        from retail_genie.models import User

        user = User.query.filter_by(username="access.revoked").one()
        event_id = stage_access_revocation(
            user_id=user.id,
            tenant_container_id="test-container",
            company_id="test-company",
            store_id="test-store",
            actor_user_id=user.id,
        )
        db.session.commit()
        assert publish_realtime_event(event_id) is True

    received = socket_client.get_received("/retail")
    assert len(received) == 1
    assert received[0]["name"] == "access.revoked"
    assert received[0]["args"][0]["data"] == {}
    assert not app.extensions["retail_genie_realtime_subscriptions"]["entries"]
    socket_client.disconnect(namespace="/retail")


def test_polling_dispatcher_fans_out_committed_rows_to_independent_worker_registries(app, create_user):
    permissions = ["inventory.view", "inventory.add", "inventory.edit"]
    create_user("worker.one", role="manager", permissions=permissions)
    create_user("worker.two", role="manager", permissions=permissions)
    client_one = app.test_client()
    _login(client_one, "worker.one")
    first_socket = _subscribe(app, client_one)
    registry_one = app.extensions["retail_genie_realtime_subscriptions"]

    initialize_realtime_registry(app)
    client_two = app.test_client()
    _login(client_two, "worker.two")
    second_socket = _subscribe(app, client_two)
    registry_two = app.extensions["retail_genie_realtime_subscriptions"]

    with app.app_context():
        event = _event(domain="inventory", event_type="inventory.updated")
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    app.extensions["retail_genie_realtime_subscriptions"] = registry_one
    assert realtime_dispatch_once(app) == 1
    first_received = first_socket.get_received("/retail")
    assert [item["args"][0]["id"] for item in first_received] == [event_id]

    app.extensions["retail_genie_realtime_subscriptions"] = registry_two
    assert realtime_dispatch_once(app) == 1
    second_received = second_socket.get_received("/retail")
    assert [item["args"][0]["id"] for item in second_received] == [event_id]

    first_socket.disconnect(namespace="/retail")
    second_socket.disconnect(namespace="/retail")
