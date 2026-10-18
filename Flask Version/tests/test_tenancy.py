from retail_genie.auth.store_scope import accessible_store_ids, can_access_store, can_view_shared_bill
from retail_genie.extensions import db
from retail_genie.models import AuditEvent, BillingSeries, Company, ContainerMembership, INVOICE_CATEGORIES, Store, TenantContainer, TenantDataPolicy, User, UserStoreAssignment
from retail_genie.tenancy.service import seed_tenant_data_policies


def _sign_in(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def test_main_admin_creates_isolated_company_first_store_and_company_admin(app, client, create_user):
    create_user("main.admin", role="super_admin")
    _sign_in(client, "main.admin")

    response = client.post(
        "/admin/companies",
        data={
            "company_name": "North Retail Group",
            "slug": "north-retail",
            "timezone": "Asia/Muscat",
            "store_name": "Sohar Showroom",
            "store_code": "SOHAR",
            "admin_username": "north.admin",
            "admin_password": "A-temporary-company-password-1!",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"were created" in response.data
    with app.app_context():
        company = Company.query.filter_by(slug="north-retail").one()
        container = db.session.get(TenantContainer, company.tenant_container_id)
        store = Store.query.filter_by(company_id=company.id, code="SOHAR").one()
        admin = User.query.filter_by(username="north.admin").one()
        membership = ContainerMembership.query.filter_by(user_id=admin.id, tenant_container_id=container.id).one()
        assert container.id != company.id
        assert container.slug == "north-retail"
        assert membership.company_id == company.id
        assert membership.role == "company_admin"
        assert TenantDataPolicy.query.filter_by(tenant_container_id=container.id).count() == 12
        assert admin.role == "company_admin"
        assert admin.company_id == company.id
        assert admin.force_password_change is True
        assert admin.check_password("A-temporary-company-password-1!")
        events = AuditEvent.query.filter_by(company_id=company.id).all()
        assert {event.action for event in events} == {"company.created", "store.created", "company_admin.created"}
        assert store.company_id == admin.company_id
        series = BillingSeries.query.filter_by(company_id=company.id).all()
        assert {row.category for row in series} == set(INVOICE_CATEGORIES)
        assert {row.prefix for row in series} == {"CASH-", "BANK-", "BT-", "OTH-"}


def test_child_company_stays_in_parent_container_and_rejects_cross_container_parent(app, client, create_user):
    create_user("main.admin", role="super_admin")
    _sign_in(client, "main.admin")
    created = client.post(
        "/admin/companies",
        data={
            "company_name": "Parent Retail",
            "slug": "parent-retail",
            "timezone": "Asia/Muscat",
            "store_name": "Parent Store",
            "store_code": "PARENT",
            "admin_username": "parent.admin",
            "admin_password": "A-temporary-company-password-2!",
        },
    )
    assert created.status_code == 302
    with app.app_context():
        parent = Company.query.filter_by(slug="parent-retail").one()
        container_id = parent.tenant_container_id
        policy_count = TenantDataPolicy.query.filter_by(tenant_container_id=container_id).count()

    child_response = client.post(
        f"/admin/containers/{container_id}/companies/{parent.id}/new",
        data={
            "company_name": "Child Retail",
            "slug": "child-retail",
            "timezone": "Asia/Muscat",
            "store_name": "Child Store",
            "store_code": "CHILD",
            "admin_username": "child.admin",
            "admin_password": "A-temporary-company-password-3!",
        },
    )
    assert child_response.status_code == 302
    with app.app_context():
        child = Company.query.filter_by(tenant_container_id=container_id, slug="child-retail").one()
        child_store = Store.query.filter_by(company_id=child.id, code="CHILD").one()
        child_admin = User.query.filter_by(username="child.admin").one()
        membership = ContainerMembership.query.filter_by(tenant_container_id=container_id, user_id=child_admin.id).one()
        assert child.parent_company_id == parent.id
        assert child_store.tenant_container_id == container_id
        assert membership.company_id == child.id
        assert membership.role == "company_admin"
        assert TenantDataPolicy.query.filter_by(tenant_container_id=container_id).count() == policy_count
        assert BillingSeries.query.filter_by(tenant_container_id=container_id, company_id=child.id).count() == len(INVOICE_CATEGORIES)

        foreign_container = TenantContainer(id="unrelated-container", name="Unrelated", slug="unrelated")
        db.session.add(foreign_container)
        db.session.flush()
        seed_tenant_data_policies(foreign_container.id)
        foreign_parent = Company(
            id="unrelated-company",
            tenant_container_id=foreign_container.id,
            name="Unrelated Company",
            slug="unrelated-company",
        )
        db.session.add(foreign_parent)
        db.session.commit()
        foreign_parent_id = foreign_parent.id

    denied = client.get(f"/admin/containers/{container_id}/companies/{foreign_parent_id}/new")
    assert denied.status_code == 404


def test_company_admin_cannot_read_or_toggle_another_company_user(app, client, create_user):
    create_user("north.subadmin", role="company_admin")
    with app.app_context():
        foreign_container = TenantContainer(id="foreign-container", name="Foreign Tenant", slug="foreign-tenant")
        db.session.add(foreign_container)
        db.session.flush()
        seed_tenant_data_policies(foreign_container.id)
        foreign_company = Company(
            id="foreign-company",
            tenant_container_id=foreign_container.id,
            name="Foreign Company",
            slug="foreign-company",
        )
        db.session.add(foreign_company)
        db.session.flush()
        foreign_user = User(
            company_id=foreign_company.id,
            username="foreign.staff",
            role="cashier",
            permissions=[],
        )
        foreign_user.set_password("A-long-test-password-4!")
        db.session.add(foreign_user)
        db.session.flush()
        db.session.add(
            ContainerMembership(
                tenant_container_id=foreign_container.id,
                user_id=foreign_user.id,
                company_id=foreign_company.id,
                role="cashier",
                permissions=[],
                is_default=True,
                is_active=True,
            )
        )
        db.session.commit()
        foreign_user_id = foreign_user.id

    _sign_in(client, "north.subadmin")
    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert b"foreign.staff" not in listing.data

    changed = client.post(f"/admin/users/{foreign_user_id}/toggle-active")
    assert changed.status_code == 404
    with app.app_context():
        assert db.session.get(User, foreign_user_id).is_active is True


def test_manager_only_gets_assigned_store_and_super_admin_decides_shared_bill_access(app, client, create_user):
    manager_id = create_user("shop.manager", role="manager", permissions=["manage_users", "use_sales_pos"])
    with app.app_context():
        other_store = Store(id="test-store-two", tenant_container_id="test-container", company_id="test-company", code="B", name="Second Store")
        db.session.add(other_store)
        db.session.commit()

    with app.app_context():
        manager = db.session.get(User, manager_id)
        assert accessible_store_ids(manager) == {"test-store"}
        assert can_access_store(manager, "test-store") is True
        assert can_access_store(manager, "test-store-two") is False
        assert can_view_shared_bill(manager, "test-store") is False

    create_user("platform.admin", role="super_admin")
    _sign_in(client, "platform.admin")
    granted = client.post(
        "/admin/store-assignments",
        data={
            "company_id": "test-company",
            "user_id": manager_id,
            "store_id": "test-store",
            "can_view_shared_bills": "y",
        },
    )
    assert granted.status_code == 302
    with app.app_context():
        manager = db.session.get(User, manager_id)
        assignment = UserStoreAssignment.query.filter_by(user_id=manager_id, store_id="test-store").one()
        assert assignment.can_view_shared_bills is True
        assert can_view_shared_bill(manager, "test-store") is True
        assert can_view_shared_bill(manager, "test-store-two") is False
        assert AuditEvent.query.filter_by(action="store_assignment.updated", entity_id=assignment.id).count() == 1


def test_company_admin_cannot_grant_shared_bill_lookup_or_access_another_tenant_store(app, client, create_user):
    manager_id = create_user("assigned.manager", role="manager")
    create_user("company.subadmin", role="company_admin")
    with app.app_context():
        second_container = TenantContainer(id="second-container", name="Second Tenant", slug="second-tenant")
        db.session.add(second_container)
        db.session.flush()
        seed_tenant_data_policies(second_container.id)
        second_company = Company(
            id="second-company",
            tenant_container_id=second_container.id,
            name="Second Company",
            slug="second-company",
        )
        db.session.add(second_company)
        db.session.flush()
        second_company_id = second_company.id
        second_store = Store(id="second-store", tenant_container_id=second_container.id, company_id=second_company_id, code="SECOND", name="Second Company Store")
        db.session.add(second_store)
        db.session.commit()

    _sign_in(client, "company.subadmin")
    cross_tenant = client.get(f"/admin/companies/{second_company_id}/stores")
    assert cross_tenant.status_code == 404

    forbidden_grant = client.post(
        "/admin/store-assignments",
        data={
            "company_id": "test-company",
            "user_id": manager_id,
            "store_id": "test-store",
            "can_view_shared_bills": "y",
        },
    )
    assert forbidden_grant.status_code == 403
    with app.app_context():
        assignment = UserStoreAssignment.query.filter_by(user_id=manager_id, store_id="test-store").one()
        assert assignment.can_view_shared_bills is False


def test_inactive_company_rejects_company_users_at_login(client, create_user, app):
    create_user("tenant.user", role="cashier")
    with app.app_context():
        company = db.session.get(Company, "test-company")
        company.is_active = False
        db.session.commit()

    response = _sign_in(client, "tenant.user")
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data
    assert client.get("/api/v1/me").status_code == 401
