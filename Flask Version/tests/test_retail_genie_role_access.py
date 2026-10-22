from __future__ import annotations

import re

from retail_genie.extensions import db
from retail_genie.models import User
from retail_genie.models.user import PERMISSIONS, ROLES, ROLE_PERMISSION_LIMITS

PASSWORD = "A-long-test-password-4!"
ADMIN_ROLES = {"super_admin", "company_admin", "admin"}


def _sign_in(client, username: str) -> None:
    response = client.post("/login", data={"username": username, "password": PASSWORD})
    assert response.status_code == 302, (username, response.status_code, response.headers.get("Location"))


def test_every_role_permission_ceiling_with_empty_and_full_grants(app, create_user):
    """Check every defined permission against each role's allowlist and account grants."""
    assertions = 0
    for role in ROLES:
        full_id = create_user(f"role.full.{role}", role=role, permissions=list(PERMISSIONS))
        bare_id = create_user(f"role.bare.{role}", role=role, permissions=[])
        with app.app_context():
            full = db.session.get(User, full_id)
            bare = db.session.get(User, bare_id)
            for permission in PERMISSIONS:
                expected_full = role in ADMIN_ROLES or permission in ROLE_PERMISSION_LIMITS.get(role, frozenset())
                expected_bare = role in ADMIN_ROLES
                assert full.has_permission(permission) is expected_full, (role, permission, "full grants")
                assert bare.has_permission(permission) is expected_bare, (role, permission, "no grants")
                assertions += 2
    assert assertions == len(ROLES) * len(PERMISSIONS) * 2


def test_every_rendered_dashboard_function_link_is_accessible_to_its_role(app, create_user):
    """A menu/card must not advertise a page that returns 401/403 for that account."""
    for role in ROLES:
        username = f"nav.{role}.user"
        create_user(username, role=role, permissions=sorted(ROLE_PERMISSION_LIMITS.get(role, ())))
        client = app.test_client()
        _sign_in(client, username)
        if role == "super_admin":
            selected = client.post("/account/tenant", data={"tenant_container_id": "test-container"})
            assert selected.status_code == 302
        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200, (role, "dashboard", dashboard.status_code)
        links = set(re.findall(r'href="([^"]+)"', dashboard.get_data(as_text=True)))
        for href in sorted(links):
            if not href.startswith("/") or href.startswith("/static/"):
                continue
            response = client.get(href, follow_redirects=False)
            assert response.status_code not in {401, 403}, (role, href, response.status_code)


def test_each_role_can_render_its_primary_function_page(app, create_user):
    """Exercise a role-specific module page using a fresh isolated account per role."""
    pages = {
        "super_admin": "/settings?company_id=test-company",
        "company_admin": "/admin/users",
        "admin": "/admin/users",
        "manager": "/settings",
        "salesperson": "/pos",
        "storekeeper": "/catalog/products",
        "cashier": "/pos",
        "logistics": "/catalog/products",
        "auditor": "/audits",
        "display": "/lcd-display",
        "express": "/express",
    }
    assert set(pages) == set(ROLES)
    for role, path in pages.items():
        username = f"function.{role}.user"
        create_user(username, role=role, permissions=sorted(ROLE_PERMISSION_LIMITS.get(role, ())))
        client = app.test_client()
        _sign_in(client, username)
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, (role, path, response.status_code, response.headers.get("Location"))


def test_super_admin_can_open_settings_company_picker_and_selected_company(client, create_user):
    create_user("settings.platform", role="super_admin")
    _sign_in(client, "settings.platform")

    picker = client.get("/settings")
    assert picker.status_code == 200
    assert b"Select a company" in picker.data
    assert b"settings-company" in picker.data

    selected = client.get("/settings?company_id=test-company")
    assert selected.status_code == 200
    assert b"Tax rates" in selected.data


def test_manager_with_manage_settings_permission_can_open_company_settings(client, create_user):
    create_user("settings.manager", role="manager", permissions=["manage_settings"])
    _sign_in(client, "settings.manager")

    response = client.get("/settings")

    assert response.status_code == 200
    assert b"Company settings" in response.data
    assert b"Tax rates" in response.data


def test_purchase_order_cancel_api_resolves_service_and_returns_not_found(client, create_user):
    create_user(
        "scm.cancel.manager",
        role="manager",
        permissions=["manage_suppliers", "create_pos", "approve_pos", "receive_stock", "manage_logistics"],
    )
    _sign_in(client, "scm.cancel.manager")

    response = client.post(
        "/api/v1/purchase-orders/no-such-purchase-order/cancel",
        json={"company_id": "test-company", "reason": "audit route smoke"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"
