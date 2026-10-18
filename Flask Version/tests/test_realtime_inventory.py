from retail_genie.extensions import db, socketio
from retail_genie.models import ContainerMembership, RealtimeEvent


CATALOG_PERMISSIONS = [
    "product_catalog.view",
    "product_catalog.add",
    "product_catalog.edit",
    "inventory.view",
    "inventory.add",
    "inventory.edit",
]


def _login(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _create_product(client):
    response = client.post(
        "/api/v1/products",
        json={"company_id": "test-company", "store_id": "test-store", "name": "Live item", "sku": "LIVE-1"},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["product"]


def _subscribe(app, flask_client, store_id="test-store"):
    socket_client = socketio.test_client(app, namespace="/retail", flask_test_client=flask_client)
    assert socket_client.is_connected("/retail")
    response = socket_client.emit(
        "subscribe_store",
        {"store_id": store_id},
        namespace="/retail",
        callback=True,
    )
    return socket_client, response


def test_store_subscription_receives_only_committed_inventory_events_and_replay(app, client, create_user):
    static_client = app.test_client()
    assert static_client.get("/static/vendor/socket.io.min.js").status_code == 200
    assert static_client.get("/static/js/catalog-realtime.js").status_code == 200
    create_user("live.inventory", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "live.inventory")
    product = _create_product(client)
    socket_client, acknowledgement = _subscribe(app, client)
    assert acknowledgement["ok"] is True
    assert acknowledgement["cursor"] == 0

    response = client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 4, "reason": "Live event test"},
    )
    assert response.status_code == 201, response.get_json()
    event_id = response.get_json()["event"]["id"]

    received = socket_client.get_received("/retail")
    assert len(received) == 1
    assert received[0]["name"] == "inventory.updated"
    assert received[0]["args"][0]["id"] == event_id
    assert received[0]["args"][0]["data"]["quantity_on_hand"] == 4

    replay = client.get(
        "/api/v1/realtime/events",
        query_string={"store_id": "test-store", "after_id": 0},
    )
    assert replay.status_code == 200
    assert replay.headers["Cache-Control"] == "private, no-store"
    assert replay.get_json()["next_cursor"] == event_id
    assert [event["id"] for event in replay.get_json()["events"]] == [event_id]

    with app.app_context():
        stored = db.session.get(RealtimeEvent, event_id)
        assert stored is not None
        assert stored.tenant_container_id == "test-container"
        assert stored.store_id == "test-store"
        assert stored.payload["quantity_on_hand"] == 4
    socket_client.disconnect(namespace="/retail")


def test_logout_revokes_and_disconnects_the_authenticated_socket(app, client, create_user):
    create_user("live.logout", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(client, "live.logout")
    socket_client, acknowledgement = _subscribe(app, client)
    assert acknowledgement["ok"] is True

    response = client.post("/logout")
    assert response.status_code == 302
    assert not socket_client.is_connected("/retail")


def test_socket_subscription_checks_store_and_inventory_policy(client, create_user, app):
    create_user(
        "live.no-inventory",
        role="manager",
        permissions=["product_catalog.view", "inventory.add"],
    )
    _login(client, "live.no-inventory")
    socket_client, acknowledgement = _subscribe(app, client)
    assert acknowledgement == {"ok": False, "error": "permission_denied"}
    socket_client.disconnect(namespace="/retail")

    unassigned_client = app.test_client()
    create_user("live.unassigned", role="manager", permissions=CATALOG_PERMISSIONS)
    _login(unassigned_client, "live.unassigned")
    with app.app_context():
        from retail_genie.models import Store

        db.session.add(
            Store(
                id="live-unassigned-store",
                tenant_container_id="test-container",
                company_id="test-company",
                code="LIVE2",
                name="Unassigned live store",
            )
        )
        db.session.commit()
    unassigned_socket, unassigned_ack = _subscribe(app, unassigned_client, "live-unassigned-store")
    assert unassigned_ack == {"ok": False, "error": "store_forbidden"}
    unassigned_socket.disconnect(namespace="/retail")


def test_socket_rechecks_permissions_before_each_event_and_revokes_subscription(app, create_user):
    first_user_id = create_user("live.first", role="manager", permissions=CATALOG_PERMISSIONS)
    create_user("live.writer", role="manager", permissions=CATALOG_PERMISSIONS)
    first_client = app.test_client()
    writer_client = app.test_client()
    _login(first_client, "live.first")
    _login(writer_client, "live.writer")
    product = _create_product(writer_client)
    socket_client, acknowledgement = _subscribe(app, first_client)
    assert acknowledgement["ok"] is True

    first_change = writer_client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 2, "reason": "Before permission revoke"},
    )
    assert first_change.status_code == 201
    assert len(socket_client.get_received("/retail")) == 1

    with app.app_context():
        membership = ContainerMembership.query.filter_by(user_id=first_user_id, tenant_container_id="test-container").one()
        membership.permissions = [permission for permission in membership.permissions if permission != "inventory.view"]
        db.session.commit()

    second_change = writer_client.post(
        f"/api/v1/products/{product['id']}/inventory",
        json={"store_id": "test-store", "quantity_delta": 1, "reason": "After permission revoke"},
    )
    assert second_change.status_code == 201
    assert socket_client.get_received("/retail") == []

    replay = first_client.get(
        "/api/v1/realtime/events",
        query_string={"store_id": "test-store", "after_id": 0},
    )
    assert replay.status_code == 403
    socket_client.disconnect(namespace="/retail")
