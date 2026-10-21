def test_login_and_current_account_never_expose_password_material(client, create_user):
    create_user("Manager.One", role="manager", permissions=["manage_users"])

    response = client.post(
        "/login",
        data={"username": "MANAGER.ONE", "password": "A-long-test-password-4!"},
        follow_redirects=False,
    )
    profile = client.get("/api/v1/me")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert profile.status_code == 200
    assert profile.json["username"] == "manager.one"
    assert profile.json["role"] == "manager"
    assert profile.json["created_at"].endswith("Z")
    assert "password" not in profile.json
    assert "password_hash" not in profile.json


def test_authenticated_cookie_has_required_flags(app, create_user, monkeypatch):
    monkeypatch.setitem(app.config, "SESSION_COOKIE_SECURE", True)
    create_user("secure.staff")

    response = app.test_client().post(
        "/login",
        data={"username": "secure.staff", "password": "A-long-test-password-4!"},
    )
    set_cookie = response.headers.get("Set-Cookie", "")

    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_invalid_credentials_use_a_generic_message(client, create_user):
    create_user("cashier1")

    response = client.post(
        "/login",
        data={"username": "does-not-exist", "password": "wrong-password-value"},
    )

    assert response.status_code == 200
    assert b"Invalid username or password." in response.data
    assert b"User not found" not in response.data


def test_inactive_account_cannot_sign_in(client, create_user):
    create_user("inactive.user", is_active=False)

    response = client.post(
        "/login",
        data={"username": "inactive.user", "password": "A-long-test-password-4!"},
    )

    assert response.status_code == 200
    assert b"Invalid username or password." in response.data
    assert client.get("/api/v1/me").status_code == 401


def test_client_supplied_user_id_does_not_authenticate(client, create_user):
    user_id = create_user("not.authenticated")

    response = client.get("/api/v1/me", headers={"X-User-ID": user_id})

    assert response.status_code == 401
    assert response.json == {"error": "authentication_required"}


def test_login_requires_csrf_token_when_csrf_is_enabled(app):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = app.test_client().post(
            "/login",
            data={"username": "somebody", "password": "A-long-test-password-4!"},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = False

    assert response.status_code == 400
    assert b"CSRF" in response.data


def test_login_csrf_token_validates_with_configured_time_limit(app, create_user):
    from html.parser import HTMLParser

    class CsrfInputParser(HTMLParser):
        token = None

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "input" and values.get("name") == "csrf_token":
                self.token = values.get("value")

    create_user("csrf.valid")
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    try:
        form_response = client.get("/login")
        parser = CsrfInputParser()
        parser.feed(form_response.get_data(as_text=True))
        assert parser.token
        response = client.post(
            "/login",
            data={"username": "csrf.valid", "password": "A-long-test-password-4!", "csrf_token": parser.token},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = False

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_password_change_revokes_other_sessions(app, create_user):
    first_client = app.test_client()
    second_client = app.test_client()
    create_user("password.user")
    credentials = {"username": "password.user", "password": "A-long-test-password-4!"}
    first_client.post("/login", data=credentials)
    second_client.post("/login", data=credentials)

    changed = first_client.post(
        "/account/password",
        data={
            "current_password": "A-long-test-password-4!",
            "new_password": "A-new-and-long-password-8!",
            "confirm_password": "A-new-and-long-password-8!",
        },
    )

    assert changed.status_code == 302
    assert first_client.get("/api/v1/me").status_code == 200
    assert second_client.get("/api/v1/me").status_code == 401


def test_temporary_password_forces_password_update(app, create_user):
    client = app.test_client()
    create_user("new.staff", force_password_change=True)

    response = client.post(
        "/login",
        data={"username": "new.staff", "password": "A-long-test-password-4!"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/password")
    dashboard = client.get("/dashboard", follow_redirects=False)
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"].endswith("/account/password")
