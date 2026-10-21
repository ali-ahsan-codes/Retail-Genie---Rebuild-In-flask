from retail_genie.extensions import db
from retail_genie.models import CatalogProduct, Company


def test_label_printing_requires_label_permission_and_only_lists_company_products(app, client, create_user):
    create_user("labels.manager", role="manager", permissions=["manage_labels", "product_catalog.view", "sales.view"])
    with app.app_context():
        company = db.session.get(Company, "test-company")
        product = CatalogProduct(tenant_container_id=company.tenant_container_id, company_id=company.id, name="Label tea", sku="TEA-39", barcode="TEA-39", price="1.500", is_active=True)
        db.session.add(product)
        db.session.commit()
    client.post("/login", data={"username": "labels.manager", "password": "A-long-test-password-4!"})
    page = client.get("/admin/label-printing")
    assert page.status_code == 200
    assert b"Print selected labels" in page.data
    products = client.get("/api/v1/labels/products?q=TEA")
    assert products.status_code == 200
    assert products.get_json()["products"][0]["barcode"] == "TEA-39"


def test_category_admin_renames_and_deletes_company_categories_with_audit(app, client, create_user):
    from retail_genie.models import AuditEvent, ProductCategory

    create_user("categories.manager", role="manager", permissions=["manage_products"])
    with app.app_context():
        company = db.session.get(Company, "test-company")
        product = CatalogProduct(tenant_container_id=company.tenant_container_id, company_id=company.id, name="Category tea", sku="CAT-TEA", category="Tea", price="1.000", is_active=True)
        db.session.add(product)
        db.session.commit()
        product_id = product.id
    client.post("/login", data={"username": "categories.manager", "password": "A-long-test-password-4!"})
    page = client.get("/admin/product-categories")
    assert page.status_code == 200 and b"Tea" in page.data
    created = client.post("/api/v1/catalog/categories", json={"name": "Tea", "company_id": "test-company"})
    assert created.status_code == 201, created.get_json()
    category_id = created.get_json()["category"]["id"]
    renamed = client.patch(f"/api/v1/catalog/categories/{category_id}", json={"name": "Hot drinks", "company_id": "test-company"})
    assert renamed.status_code == 200, renamed.get_json()
    with app.app_context():
        assert db.session.get(CatalogProduct, product_id).category == "Hot drinks"
        assert db.session.get(ProductCategory, category_id).name == "Hot drinks"
    deleted = client.delete(f"/api/v1/catalog/categories/{category_id}", json={"company_id": "test-company"})
    assert deleted.status_code == 200, deleted.get_json()
    with app.app_context():
        assert db.session.get(CatalogProduct, product_id).category is None
        assert AuditEvent.query.filter(AuditEvent.action.in_(["catalog.category_created", "catalog.category_renamed", "catalog.category_deleted"])).count() == 3
    foreign = client.get("/api/v1/catalog/categories?company_id=other-company")
    assert foreign.status_code in {403, 404}
