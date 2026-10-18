import pytest
from sqlalchemy.exc import IntegrityError

from retail_genie.auth.tenant_context import current_membership, current_tenant_container_id
from retail_genie.auth.tenant_policy import can_access_data_domain
from retail_genie.extensions import db
from retail_genie.models import (
    Company,
    ContainerMembership,
    Store,
    TenantContainer,
    TenantDataPolicy,
    TenantDataPolicyScope,
    User,
)
from retail_genie.tenancy.service import seed_tenant_data_policies


def _login(client, username: str, password: str = "A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def _new_container(container_id: str, company_id: str, *, slug: str | None = None):
    container = TenantContainer(
        id=container_id,
        name=f"Tenant {container_id}",
        slug=slug or container_id,
        timezone="Asia/Muscat",
    )
    db.session.add(container)
    db.session.flush()
    seed_tenant_data_policies(container.id)
    company = Company(
        id=company_id,
        tenant_container_id=container.id,
        name=f"Company {company_id}",
        slug=company_id,
    )
    db.session.add(company)
    db.session.flush()
    return container, company


def test_container_is_the_boundary_and_company_policy_is_restrictive_by_default(app, create_user):
    user_id = create_user("policy.manager", role="manager", permissions=["manage_products"])
    viewer_id = create_user("catalog.viewer", role="manager", permissions=["product_catalog.view"])
    with app.app_context():
        own_company = db.session.get(Company, "test-company")
        tenant_id = own_company.tenant_container_id
        sibling = Company(
            id="sibling-company",
            tenant_container_id=tenant_id,
            parent_company_id=own_company.id,
            name="Sibling Company",
            slug="sibling-company",
        )
        foreign_container, foreign_company = _new_container("outside-container", "outside-company")
        db.session.add(sibling)
        db.session.flush()
        user = db.session.get(User, user_id)
        product_policy = TenantDataPolicy.query.filter_by(tenant_container_id=tenant_id, domain="product_catalog").one()
        outside_policy = TenantDataPolicy.query.filter_by(tenant_container_id=foreign_container.id, domain="product_catalog").one()

        assert can_access_data_domain(
            user,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            company_id=own_company.id,
        ) is True
        assert can_access_data_domain(
            user,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            company_id=sibling.id,
        ) is False

        viewer = db.session.get(User, viewer_id)
        assert can_access_data_domain(
            viewer,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            action="view",
            company_id=own_company.id,
        ) is True
        for action in ("add", "edit", "delete"):
            assert can_access_data_domain(
                viewer,
                tenant_container_id=tenant_id,
                domain="product_catalog",
                action=action,
                company_id=own_company.id,
            ) is False

        product_policy.sharing_mode = "container"
        assert can_access_data_domain(
            user,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            company_id=sibling.id,
        ) is True

        outside_policy.sharing_mode = "container"
        assert can_access_data_domain(
            user,
            tenant_container_id=foreign_container.id,
            domain="product_catalog",
            company_id=foreign_company.id,
        ) is False

        product_policy.sharing_mode = "selected_units"
        scope = TenantDataPolicyScope(
            tenant_container_id=tenant_id,
            policy_id=product_policy.id,
            company_id=sibling.id,
            is_allowed=True,
        )
        db.session.add(scope)
        db.session.flush()
        assert can_access_data_domain(
            user,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            company_id=sibling.id,
        ) is True
        scope.is_allowed = False
        assert can_access_data_domain(
            user,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            company_id=sibling.id,
        ) is False


def test_same_user_can_select_only_an_active_membership_container(client, create_user, app):
    user_id = create_user("multi.tenant.user", role="cashier")
    with app.app_context():
        second_container, second_company = _new_container("second-user-container", "second-user-company")
        db.session.add(
            ContainerMembership(
                tenant_container_id=second_container.id,
                user_id=user_id,
                company_id=second_company.id,
                role="manager",
                permissions=["manage_users"],
                is_default=True,
                is_active=True,
            )
        )
        db.session.commit()

    response = _login(client, "multi.tenant.user")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/tenant")
    assert client.get("/api/v1/me").status_code == 302

    selected = client.post("/account/tenant", data={"tenant_container_id": "second-user-container"})
    assert selected.status_code == 302
    profile = client.get("/api/v1/me")
    assert profile.status_code == 200
    assert profile.get_json()["tenant_container_id"] == "second-user-container"
    assert profile.get_json()["role"] == "manager"

    denied = client.post("/account/tenant", data={"tenant_container_id": "outside-container"})
    assert denied.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_id)
        assert current_tenant_container_id(user) is None
        assert current_membership(user) is None


def test_database_foreign_keys_reject_a_company_store_from_another_container(app):
    with app.app_context():
        foreign_container, foreign_company = _new_container("fk-container", "fk-company")
        db.session.flush()
        invalid_store = Store(
            id="cross-container-store",
            tenant_container_id="test-container",
            company_id=foreign_company.id,
            code="BAD",
            name="Should be rejected",
        )
        db.session.add(invalid_store)
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        store_fks = {tuple(fk.column_keys) for fk in Store.__table__.foreign_key_constraints}
        assert ("tenant_container_id", "company_id") in store_fks
        assert ("tenant_container_id",) in store_fks
