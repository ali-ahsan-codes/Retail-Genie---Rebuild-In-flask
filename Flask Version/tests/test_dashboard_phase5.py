def _login(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def test_dashboard_exposes_only_role_permitted_workflows(client, create_user):
    create_user(
        "dashboard.cashier",
        role="cashier",
        permissions=["use_sales_pos", "sales.view"],
    )
    _login(client, "dashboard.cashier")

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Your daily work" in response.data
    assert b"Point of sale" in response.data
    assert b"Orders &amp; fulfillment" in response.data
    assert b"Companies &amp; stores" not in response.data
    assert b"Data policies" not in response.data
    assert b"Database backups" not in response.data
    assert b"<details class=\"nav-menu\">" in response.data


def test_navigation_links_match_role_and_granted_permissions(app, create_user):
    cases = [
        ("nav.manager", "manager", ["use_sales_pos", "sales.view", "manage_orders", "manage_settings", "manage_labels", "manage_users"], [b"Sales / POS", b"Settings", b"Accounts", b"Barcode / labels", b"Daily cashup", b"Removals"], [b"Companies</a>", b"Database backups"]),
        ("nav.express", "express", ["express_checkout"], [b"Express checkout"], [b"Sales / POS", b"Orders / fulfillment"]),
        ("nav.company", "company_admin", [], [b"Store access", b"Billing setup"], [b"Companies</a>", b"Data policies"]),
        ("nav.display", "display", [], [b"LCD display"], [b"Companies</a>", b"Database backups"]),
    ]
    for username, role, permissions, expected, absent in cases:
        create_user(username, role=role, permissions=permissions)
        client = app.test_client()
        _login(client, username)
        response = client.get("/dashboard")
        assert response.status_code == 200, username
        for label in expected:
            assert label in response.data, (username, label)
        for label in absent:
            assert label not in response.data, (username, label)


def test_platform_dashboard_has_administration_cards_and_shared_shell(app, create_user):
    create_user("dashboard.platform", role="super_admin")
    client = app.test_client()
    _login(client, "dashboard.platform")

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Platform administration" in response.data
    assert b"Companies &amp; stores" in response.data
    assert b"Data policies" in response.data
    assert b"Database backups" in response.data
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert b"workspace-card-grid" in css.data
    assert b"@media (max-width: 600px)" in css.data
