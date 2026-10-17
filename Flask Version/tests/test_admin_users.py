from retail_genie.extensions import db
from retail_genie.models import User


def _sign_in(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def test_first_admin_is_created_interactively_without_a_default_password(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin", "--username", "first.admin"],
        input="A-valid-and-long-password-2!\nA-valid-and-long-password-2!\n",
    )

    assert result.exit_code == 0
    assert "Administrator 'first.admin' created." in result.output
    with app.app_context():
        account = User.query.filter_by(username="first.admin", role="admin").one()
        assert account.check_password("A-valid-and-long-password-2!") is True
        assert account.force_password_change is False


def test_accounts_page_requires_manage_users_permission(client, create_user):
    create_user("sales.staff", role="salesperson")
    _sign_in(client, "sales.staff")

    response = client.get("/admin/users")

    assert response.status_code == 403


def test_admin_can_create_account_with_hashed_temporary_password(app, create_user):
    client = app.test_client()
    create_user("admin1", role="admin")
    _sign_in(client, "admin1")

    response = client.post(
        "/admin/users",
        data={
            "username": "Cashier.New",
            "role": "cashier",
            "password": "A-temporary-password-9!",
            "permissions": ["upload_cloud"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        account = User.query.filter_by(username="cashier.new").one()
        assert account.is_active is True
        assert account.force_password_change is True
        assert account.password_hash != "A-temporary-password-9!"
        assert account.check_password("A-temporary-password-9!") is True
        assert "upload_cloud" in account.permissions


def test_manager_cannot_grant_permissions_they_do_not_hold(app, create_user):
    client = app.test_client()
    create_user("manager1", role="manager", permissions=["manage_users"])
    _sign_in(client, "manager1")

    response = client.post(
        "/admin/users",
        data={
            "username": "cashier.new",
            "role": "cashier",
            "password": "A-temporary-password-9!",
            "permissions": ["manage_products"],
        },
    )

    assert response.status_code == 200
    with app.app_context():
        assert User.query.filter_by(username="cashier.new").first() is None


def test_deactivating_account_invalidates_existing_session(app, create_user):
    admin_client = app.test_client()
    staff_client = app.test_client()
    create_user("admin1", role="admin")
    staff_id = create_user("store.staff", role="storekeeper")

    _sign_in(admin_client, "admin1")
    _sign_in(staff_client, "store.staff")
    assert staff_client.get("/api/v1/me").status_code == 200

    changed = admin_client.post(f"/admin/users/{staff_id}/toggle-active")
    after_deactivation = staff_client.get("/api/v1/me")

    assert changed.status_code == 302
    assert after_deactivation.status_code == 401

    with app.app_context():
        staff = db.session.get(User, staff_id)
        assert staff.is_active is False
        assert staff.auth_version == 2


def test_operator_can_reset_imported_password_interactively(app, create_user):
    create_user("import.admin", role="admin", force_password_change=True)
    runner = app.test_cli_runner()
    new_temporary_password = "A-new-imported-admin-password-8!"

    result = runner.invoke(
        args=["reset-imported-password", "--username", "import.admin"],
        input=f"{new_temporary_password}\n{new_temporary_password}\n",
    )

    assert result.exit_code == 0
    assert new_temporary_password not in result.output
    with app.app_context():
        account = User.query.filter_by(username="import.admin").one()
        assert account.check_password(new_temporary_password) is True
        assert account.force_password_change is True
        assert account.auth_version == 2
