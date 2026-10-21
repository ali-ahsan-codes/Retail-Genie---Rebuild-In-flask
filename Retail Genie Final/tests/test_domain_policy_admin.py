from retail_genie.auth.tenant_policy import can_access_data_domain
from retail_genie.extensions import db
from retail_genie.models import AuditEvent, Company, RealtimeEvent, Store, TenantContainer, TenantDataPolicy, TenantDataPolicyScope, User


def _login(client, username: str, password: str = "A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def test_main_admin_can_change_domain_scopes_and_policy_change_is_audited(app, create_user):
    main_admin_id = create_user("policy.main", role="super_admin")
    viewer_id = create_user("policy.viewer", role="manager", permissions=["product_catalog.view"])
    with app.app_context():
        sibling = Company(
            id="policy-sibling-company",
            tenant_container_id="test-container",
            parent_company_id="test-company",
            name="Sibling Company",
            slug="policy-sibling",
        )
        sibling_store = Store(
            id="policy-sibling-store",
            tenant_container_id="test-container",
            company_id=sibling.id,
            code="SIB",
            name="Sibling Store",
        )
        db.session.add_all([sibling, sibling_store])
        db.session.commit()

    admin_client = app.test_client()
    _login(admin_client, "policy.main")
    index = admin_client.get("/admin/domain-policies")
    assert index.status_code == 200
    assert b"Data-domain policies" in index.data
    listing = admin_client.get("/admin/containers/test-container/policies")
    assert listing.status_code == 200
    assert b"Product catalog" in listing.data

    saved = admin_client.post(
        "/admin/containers/test-container/policies/product_catalog",
        data={
            "is_enabled": "y",
            "sharing_mode": "selected_units",
            "allow_company_ids": ["test-company"],
            "deny_company_ids": ["policy-sibling-company"],
            "allow_store_ids": ["test-store"],
            "deny_store_ids": ["policy-sibling-store"],
        },
    )
    assert saved.status_code == 302
    assert saved.headers["Location"].endswith("/admin/containers/test-container/policies")
    history_page = admin_client.get("/admin/containers/test-container/policies/product_catalog")
    assert history_page.status_code == 200
    assert b"Recent policy changes" in history_page.data
    assert b"policy.main" in history_page.data
    assert b"View recorded values" in history_page.data

    with app.app_context():
        policy = TenantDataPolicy.query.filter_by(tenant_container_id="test-container", domain="product_catalog").one()
        scopes = TenantDataPolicyScope.query.filter_by(tenant_container_id="test-container", policy_id=policy.id).all()
        assert policy.is_enabled is True
        assert policy.sharing_mode == "selected_units"
        assert policy.policy_version == 2
        assert policy.changed_by_user_id == main_admin_id
        assert {(scope.company_id, scope.store_id, scope.is_allowed) for scope in scopes} == {
            ("test-company", None, True),
            ("policy-sibling-company", None, False),
            (None, "test-store", True),
            (None, "policy-sibling-store", False),
        }
        event = AuditEvent.query.filter_by(
            tenant_container_id="test-container",
            action="tenant_data_policy.updated",
            entity_id=policy.id,
        ).one()
        assert event.actor_user_id == main_admin_id
        assert event.company_id is None
        assert event.before_data["sharing_mode"] == "company"
        assert event.after_data["sharing_mode"] == "selected_units"
        access_event = RealtimeEvent.query.filter_by(
            tenant_container_id="test-container",
            domain="access",
            recipient_user_id=viewer_id,
            event_type="access.revoked",
        ).one()
        assert access_event.payload == {}
        viewer = db.session.get(User, viewer_id)
        assert can_access_data_domain(
            viewer,
            tenant_container_id="test-container",
            domain="product_catalog",
            action="view",
            company_id="test-company",
            store_id="test-store",
        ) is True
        assert can_access_data_domain(
            viewer,
            tenant_container_id="test-container",
            domain="product_catalog",
            action="view",
            company_id="policy-sibling-company",
            store_id="policy-sibling-store",
        ) is False


def test_only_main_admin_can_manage_domain_policies(client, create_user):
    create_user("tenant.policy.admin", role="company_admin")
    _login(client, "tenant.policy.admin")
    response = client.get("/admin/domain-policies")
    assert response.status_code == 403


def test_policy_form_rejects_scope_ids_from_another_container(app, create_user):
    create_user("scope.main", role="super_admin")
    with app.app_context():
        foreign_container = TenantContainer(
            id="external-policy-container",
            name="External Tenant",
            slug="external-policy-tenant",
        )
        db.session.add(foreign_container)
        db.session.flush()
        foreign_company = Company(
            id="external-policy-company",
            tenant_container_id=foreign_container.id,
            name="External Company",
            slug="external-policy-company",
        )
        db.session.add(foreign_company)
        db.session.commit()

    admin_client = app.test_client()
    _login(admin_client, "scope.main")
    response = admin_client.post(
        "/admin/containers/test-container/policies/product_catalog",
        data={
            "is_enabled": "y",
            "sharing_mode": "selected_units",
            "allow_company_ids": ["external-policy-company"],
        },
    )
    assert response.status_code == 200
    with app.app_context():
        policy = TenantDataPolicy.query.filter_by(tenant_container_id="test-container", domain="product_catalog").one()
        assert policy.sharing_mode == "company"
        assert TenantDataPolicyScope.query.filter_by(policy_id=policy.id).count() == 0
        assert AuditEvent.query.filter_by(action="tenant_data_policy.updated").count() == 0
