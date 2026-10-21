def test_health_endpoints_are_available_without_login(client):
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json == {"database": "ok", "status": "ready"}


def test_security_headers_are_set(client):
    response = client.get("/healthz")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
