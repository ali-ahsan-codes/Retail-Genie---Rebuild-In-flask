import pytest

from retail_genie.models import User


@pytest.mark.parametrize("role", ["admin", "manager", "salesperson", "storekeeper", "cashier", "logistics", "auditor", "display", "express"])
def test_supported_legacy_roles(role):
    user = User(username=f"user.{role}", role=role, permissions=[])
    assert user.role == role


def test_only_admin_bypasses_explicit_permission_checks():
    admin = User(username="admin1", role="admin", permissions=[])
    manager = User(username="manager1", role="manager", permissions=["manage_users"])
    cashier = User(username="cashier1", role="cashier", permissions=[])

    assert admin.has_permission("manage_users") is True
    assert manager.has_permission("manage_users") is True
    assert manager.has_permission("manage_products") is False
    assert cashier.has_permission("manage_users") is False
