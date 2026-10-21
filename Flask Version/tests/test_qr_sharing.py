"""Desktop/tablet QR sharing for the current Retail Genie login URL."""

from retail_genie.device import is_mobile_phone


def test_device_detection_hides_qr_on_phones_but_not_tablets():
    assert is_mobile_phone("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
    assert is_mobile_phone("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36")
    assert not is_mobile_phone("Mozilla/5.0 (Linux; Android 14; SM-X700 Build/UP1A) AppleWebKit/537.36 Safari/537.36")
    assert not is_mobile_phone("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36")
    assert is_mobile_phone("Generic browser", mobile_hint="?1")


def test_login_page_shows_dynamic_lan_qr_on_desktop_and_tablet(app, monkeypatch):
    from retail_genie import share

    monkeypatch.setattr(share, "_primary_lan_ipv4", lambda: "192.168.50.24")
    client = app.test_client()
    desktop = client.get("/login", base_url="http://localhost:5000")
    assert desktop.status_code == 200
    assert b"Open on phone" in desktop.data
    assert b"http://192.168.50.24:5000/login" in desktop.data

    tablet = client.get(
        "/login",
        base_url="http://localhost:5000",
        headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Tablet) AppleWebKit/537.36 Safari/537.36"},
    )
    assert tablet.status_code == 200
    assert b"Open on phone" in tablet.data

    qr_response = client.get("/app-qr.svg", base_url="http://localhost:5000")
    assert qr_response.status_code == 200
    assert qr_response.mimetype == "image/svg+xml"
    assert qr_response.headers["Cache-Control"] == "no-store, max-age=0"
    assert b"<svg" in qr_response.data


def test_login_page_does_not_render_qr_for_mobile_user_agent(app, monkeypatch):
    from retail_genie import share

    monkeypatch.setattr(share, "_primary_lan_ipv4", lambda: "192.168.50.24")
    client = app.test_client()
    response = client.get(
        "/login",
        base_url="http://localhost:5000",
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
    )
    assert response.status_code == 200
    assert b"Open on phone" not in response.data
    assert b"app-qr.svg" not in response.data


def test_public_base_url_overrides_lan_ip_for_reverse_proxy(app, monkeypatch):
    from retail_genie import share

    monkeypatch.setattr(share, "_primary_lan_ipv4", lambda: "192.168.50.24")
    app.config["PUBLIC_BASE_URL"] = "https://retail.example.test"
    response = app.test_client().get("/login", base_url="http://localhost:5000")
    assert response.status_code == 200
    assert b"https://retail.example.test/login" in response.data
    app.config["PUBLIC_BASE_URL"] = None
