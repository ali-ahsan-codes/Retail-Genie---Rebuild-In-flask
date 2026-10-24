from __future__ import annotations

import pytest
from sqlalchemy import select, text

from retail_genie.extensions import db
from retail_genie.models import (
    AuditEvent,
    CatalogProduct,
    Company,
    ContainerMembership,
    InventoryBalance,
    InventoryMovement,
    Store,
    SubscriptionPlan,
    TenantContainer,
    TenantDataPolicy,
    TenantDataPolicyScope,
    TenantSubscription,
    User,
    UserStoreAssignment,
)
from retail_genie.tenancy.company_transfer import (
    CompanyTransferError,
    move_company_to_container,
    preview_company_transfer,
)
from retail_genie.tenancy.service import seed_tenant_data_policies


def _source_company(actor_id: str, *, with_member: bool = True):
    source = TenantContainer(
        id="source-b",
        name="Source B Container",
        slug="source-b",
        timezone="Asia/Muscat",
    )
    db.session.add(source)
    db.session.flush()
    seed_tenant_data_policies(source.id)
    company = Company(
        id="company-b",
        tenant_container_id=source.id,
        name="Company B",
        slug="company-b",
    )
    store = Store(
        id="store-b",
        tenant_container_id=source.id,
        company_id=company.id,
        code="B-MAIN",
        name="B Main Store",
    )
    db.session.add_all([company, store])
    db.session.flush()

    member = None
    if with_member:
        member = User(
            username="company-b-admin",
            company_id=company.id,
            role="company_admin",
            permissions=[],
            is_active=True,
        )
        member.set_password("A-long-test-password-4!")
        db.session.add(member)
        db.session.flush()
        db.session.add_all(
            [
                ContainerMembership(
                    tenant_container_id=source.id,
                    user_id=member.id,
                    company_id=company.id,
                    role="company_admin",
                    permissions=[],
                    is_default=True,
                    is_active=True,
                ),
                UserStoreAssignment(
                    tenant_container_id=source.id,
                    company_id=company.id,
                    user_id=member.id,
                    store_id=store.id,
                    assigned_by_id=actor_id,
                    is_active=True,
                ),
            ]
        )

    product = CatalogProduct(
        id="product-b",
        tenant_container_id=source.id,
        company_id=company.id,
        sku="B-SKU-1",
        name="Company B product",
        created_by_id=member.id if member else actor_id,
    )
    db.session.add(product)
    db.session.flush()
    db.session.add_all(
        [
            InventoryBalance(
                id="balance-b",
                tenant_container_id=source.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=12,
                updated_by_id=member.id if member else actor_id,
            ),
            InventoryMovement(
                id="movement-b",
                tenant_container_id=source.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                movement_type="opening",
                quantity_delta=12,
                reason="Opening stock",
                actor_user_id=member.id if member else actor_id,
                idempotency_key="company-b-opening",
            ),
            AuditEvent(
                tenant_container_id=source.id,
                company_id=company.id,
                store_id=store.id,
                actor_user_id=member.id if member else actor_id,
                action="inventory.opening_stock",
                entity_type="inventory_balance",
                entity_id="balance-b",
                reason="Opening stock audit row",
            ),
        ]
    )
    source_policy = db.session.execute(
        select(TenantDataPolicy).where(
            TenantDataPolicy.tenant_container_id == source.id,
            TenantDataPolicy.domain == "inventory",
        )
    ).scalar_one()
    source_policy.sharing_mode = "selected_units"
    db.session.add(
        TenantDataPolicyScope(
            tenant_container_id=source.id,
            policy_id=source_policy.id,
            company_id=company.id,
            store_id=None,
            is_allowed=True,
        )
    )
    db.session.flush()
    return source, company, store, member


def _platform_actor():
    actor = User(
        username="platform-transfer-admin",
        role="super_admin",
        permissions=[],
        is_active=True,
    )
    actor.set_password("A-long-test-password-4!")
    db.session.add(actor)
    db.session.flush()
    return actor


def test_company_transfer_preserves_identity_history_memberships_and_archives_source(app):
    with app.app_context():
        actor = _platform_actor()
        source, company, store, member = _source_company(actor.id)
        db.session.commit()

        plan = preview_company_transfer(company.id, "test-container", "test-company")
        assert plan.can_move
        assert plan.source_will_archive is True
        assert plan.store_count == 1
        assert plan.member_count == 1
        assert plan.row_counts["catalog_products"] == 1
        assert plan.row_counts["inventory_movements"] == 1
        assert plan.row_counts["audit_events"] == 1

        result = move_company_to_container(
            company_id=company.id,
            destination_container_id="test-container",
            destination_parent_company_id="test-company",
            actor_user_id=actor.id,
            reason="Approved customer consolidation request.",
        )
        assert result["source_container_archived"] is True

        moved_company = db.session.get(Company, "company-b")
        moved_store = db.session.get(Store, "store-b")
        assert moved_company.tenant_container_id == "test-container"
        assert moved_company.parent_company_id == "test-company"
        assert moved_store.tenant_container_id == "test-container"
        assert moved_store.company_id == "company-b"

        balance = db.session.get(InventoryBalance, "balance-b")
        movement = db.session.get(InventoryMovement, "movement-b")
        assert balance.tenant_container_id == "test-container"
        assert balance.quantity_on_hand == 12
        assert movement.tenant_container_id == "test-container"
        assert movement.quantity_delta == 12

        membership = db.session.execute(
            select(ContainerMembership).where(ContainerMembership.user_id == member.id)
        ).scalar_one()
        assignment = db.session.execute(
            select(UserStoreAssignment).where(UserStoreAssignment.user_id == member.id)
        ).scalar_one()
        assert membership.tenant_container_id == "test-container"
        assert membership.company_id == "company-b"
        assert assignment.tenant_container_id == "test-container"
        assert assignment.store_id == "store-b"
        assert db.session.get(User, member.id).auth_version == 2

        source_scope = db.session.execute(
            select(TenantDataPolicyScope).where(TenantDataPolicyScope.company_id == company.id)
        ).scalar_one()
        target_inventory_policy = db.session.execute(
            select(TenantDataPolicy).where(
                TenantDataPolicy.tenant_container_id == "test-container",
                TenantDataPolicy.domain == "inventory",
            )
        ).scalar_one()
        assert source_scope.tenant_container_id == "test-container"
        assert source_scope.policy_id == target_inventory_policy.id

        assert db.session.get(TenantContainer, source.id).is_active is False
        assert db.session.get(Company, "test-company").tenant_container_id == "test-container"
        assert db.session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_container_id == "test-container",
                AuditEvent.action == "company.container_transferred",
            )
        ).scalar_one()
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_company_transfer_preflight_blocks_destination_membership_collision(app):
    with app.app_context():
        actor = _platform_actor()
        _, company, _, member = _source_company(actor.id)
        db.session.add(
            ContainerMembership(
                tenant_container_id="test-container",
                user_id=member.id,
                company_id="test-company",
                role="manager",
                permissions=[],
                is_default=False,
                is_active=True,
            )
        )
        db.session.commit()

        plan = preview_company_transfer(company.id, "test-container")
        assert not plan.can_move
        assert any("destination-container membership" in item for item in plan.blockers)
        with pytest.raises(CompanyTransferError, match="Transfer blocked"):
            move_company_to_container(
                company_id=company.id,
                destination_container_id="test-container",
                destination_parent_company_id=None,
                actor_user_id=actor.id,
                reason="Approved customer consolidation request.",
            )
        assert db.session.get(Company, company.id).tenant_container_id == "source-b"
        assert db.session.get(TenantContainer, "source-b").is_active is True


def test_cross_company_product_dependency_blocks_transfer(app):
    with app.app_context():
        actor = _platform_actor()
        source, company, store, _ = _source_company(actor.id, with_member=False)
        other_company = Company(
            id="company-a-in-source",
            tenant_container_id=source.id,
            name="Company A in Source",
            slug="company-a-in-source",
        )
        db.session.add(other_company)
        db.session.flush()
        other_product = CatalogProduct(
            id="product-a-in-source",
            tenant_container_id=source.id,
            company_id=other_company.id,
            sku="A-SKU-1",
            name="Company A product",
            created_by_id=actor.id,
        )
        db.session.add(other_product)
        db.session.flush()
        db.session.add(
            InventoryBalance(
                id="balance-cross-company-product",
                tenant_container_id=source.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=other_company.id,
                product_id=other_product.id,
                quantity_on_hand=1,
            )
        )
        db.session.commit()

        plan = preview_company_transfer(company.id, "test-container")
        assert not plan.can_move
        assert any("products owned by another company" in item for item in plan.blockers)


def test_last_company_move_requires_source_subscription_to_be_stopped(app):
    with app.app_context():
        actor = _platform_actor()
        source, company, _, _ = _source_company(actor.id, with_member=False)
        plan = SubscriptionPlan(
            id="source-active-plan",
            code="source-active-plan",
            name="Active source plan",
            monthly_price=1,
        )
        db.session.add(plan)
        db.session.flush()
        db.session.add(
            TenantSubscription(
                id="source-active-subscription",
                tenant_container_id=source.id,
                plan_id=plan.id,
                status="active",
            )
        )
        db.session.commit()

        preview = preview_company_transfer(company.id, "test-container")
        assert not preview.can_move
        assert any("cancel or suspend" in item for item in preview.blockers)


def test_company_with_children_is_not_moved_as_a_partial_subtree(app):
    with app.app_context():
        actor = _platform_actor()
        source, company, _, _ = _source_company(actor.id, with_member=False)
        child = Company(
            id="company-b-child",
            tenant_container_id=source.id,
            parent_company_id=company.id,
            name="Company B Child",
            slug="company-b-child",
        )
        db.session.add(child)
        db.session.commit()

        plan = preview_company_transfer(company.id, "test-container")
        assert not plan.can_move
        assert any("child companies" in item for item in plan.blockers)


def test_super_admin_container_and_guide_pages_render(client, app):
    with app.app_context():
        actor = _platform_actor()
        _source_company(actor.id)
        db.session.add(
            TenantContainer(
                id="empty-container",
                name="Empty Container",
                slug="empty-container",
                timezone="Asia/Muscat",
            )
        )
        db.session.commit()

    login_response = client.post(
        "/login",
        data={"username": "platform-transfer-admin", "password": "A-long-test-password-4!"},
    )
    assert login_response.status_code == 302

    containers_response = client.get("/admin/containers")
    guide_response = client.get("/admin/company-container-guide")
    transfer_response = client.get(
        "/admin/companies/company-b/move?destination_container_id=test-container&destination_parent_company_id=test-company"
    )
    assert containers_response.status_code == 200
    assert b"Tenant containers" in containers_response.data
    assert guide_response.status_code == 200
    assert b"Move a company without merging it" in guide_response.data
    assert transfer_response.status_code == 200
    assert b"READ-ONLY IMPACT REPORT" in transfer_response.data

    post_response = client.post(
        "/admin/companies/company-b/move",
        data={
            "destination_container_id": "test-container",
            "destination_parent_company_id": "test-company",
            "reason": "Approved consolidation through the admin workflow.",
            "confirmation": "MOVE company-b",
            "policies_reviewed": "yes",
        },
    )
    assert post_response.status_code == 302
    assert post_response.headers["Location"].endswith("/admin/containers")
    archive_response = client.post("/admin/containers/empty-container/archive")
    assert archive_response.status_code == 302
    with app.app_context():
        assert db.session.get(Company, "company-b").tenant_container_id == "test-container"
        assert db.session.get(TenantContainer, "empty-container").is_active is False
