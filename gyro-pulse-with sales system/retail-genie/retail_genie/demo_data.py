"""Explicit opt-in demo records for a fresh local Retail Genie database."""

from decimal import Decimal

from .extensions import db
from .models import (
    BillingSeries,
    CatalogProduct,
    Company,
    InventoryBalance,
    InventoryMovement,
    OrderNumberSeries,
    Store,
    TenantContainer,
)
from .tenancy.service import seed_tenant_data_policies

DEMO_CONTAINER_SLUG = "demo-retail"
DEMO_PRODUCTS = (
    ("DEMO-001", "Omani Dates 500 g", "Groceries", "2.500", 30, 5),
    ("DEMO-002", "Bottled Water 1.5 L", "Beverages", "0.250", 60, 12),
    ("DEMO-003", "Basmati Rice 5 kg", "Groceries", "4.500", 18, 4),
    ("DEMO-004", "Arabic Coffee 250 g", "Beverages", "3.750", 14, 3),
    ("DEMO-005", "Dish Soap 750 ml", "Household", "1.250", 20, 5),
)


def seed_demo_records() -> bool:
    """Create one demo tenant, store, products and opening stock exactly once.

    Returns ``False`` without writes if this seed container already exists. The
    caller must restrict use to a fresh local database and require explicit
    confirmation before invoking this function.
    """
    if TenantContainer.query.filter_by(slug=DEMO_CONTAINER_SLUG).first() is not None:
        return False

    container = TenantContainer(
        name="Retail Genie Demo",
        slug=DEMO_CONTAINER_SLUG,
        timezone="Asia/Muscat",
    )
    db.session.add(container)
    db.session.flush()
    seed_tenant_data_policies(container.id)

    company = Company(
        tenant_container_id=container.id,
        name="Demo Retail LLC",
        slug=DEMO_CONTAINER_SLUG,
        timezone=container.timezone,
    )
    db.session.add(company)
    db.session.flush()

    prefixes = {"cash": "CASH-", "bank": "BANK-", "bank_transfer": "BT-", "other": "OTH-"}
    db.session.add_all(
        [
            BillingSeries(
                tenant_container_id=container.id,
                company_id=company.id,
                category=category,
                prefix=prefix,
                next_number=1,
            )
            for category, prefix in prefixes.items()
        ]
    )
    db.session.add(
        OrderNumberSeries(
            tenant_container_id=container.id,
            company_id=company.id,
            prefix="DEMO-ORD-",
            next_number=1,
        )
    )

    store = Store(
        tenant_container_id=container.id,
        company_id=company.id,
        code="DEMO-01",
        name="Muscat Demo Store",
    )
    db.session.add(store)
    db.session.flush()

    for sku, name, category, price, quantity, threshold in DEMO_PRODUCTS:
        product = CatalogProduct(
            tenant_container_id=container.id,
            company_id=company.id,
            sku=sku,
            name=name,
            category=category,
            price=Decimal(price),
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(
            InventoryBalance(
                tenant_container_id=container.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=quantity,
                low_stock_threshold=threshold,
            )
        )
        db.session.add(
            InventoryMovement(
                tenant_container_id=container.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                movement_type="opening",
                quantity_delta=quantity,
                reason="Demo-only opening stock",
            )
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True
