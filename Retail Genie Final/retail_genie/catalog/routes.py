"""Server-rendered catalog screen and authenticated JSON product APIs."""

import csv
import io

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..auth.store_scope import accessible_store_ids, can_access_store
from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import AuditEvent, CatalogProduct, Company, DemandNotice, InventoryMovement, ProductCategory, Quotation, RealtimeEvent, SalesOrder, Store
from ..realtime.service import publish_realtime_event
from . import catalog_bp
from .forms import InventoryAdjustmentForm, ProductForm
from .service import (
    CatalogRuleError,
    accessible_stores,
    adjust_inventory,
    archive_product,
    create_product,
    import_products_csv,
    list_products,
    product_dict,
    transfer_inventory,
    update_product,
)


def _payload() -> dict:
    value = request.get_json(silent=True)
    if value is None:
        value = request.form.to_dict(flat=True)
    return value if isinstance(value, dict) else {}


def _error_response(error: CatalogRuleError):
    db.session.rollback()
    return jsonify(error=error.code, message=str(error)), error.status_code


def _inventory_error_response(error: CatalogRuleError):
    db.session.rollback()
    flash(str(error), "error")
    return redirect(url_for("catalog.products_page", store_id=request.form.get("store_id", "")))


def _row_dict(row: dict) -> dict:
    product = row["product"]
    value = product_dict(product)
    value["stock_quantity"] = row["stock_quantity"]
    value["low_stock_threshold"] = row["low_stock_threshold"]
    value["is_low_stock"] = row["is_low_stock"]
    return value


def _read_csv_upload() -> str:
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise CatalogRuleError("Choose a CSV file to import.")
    raw = upload.stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise CatalogRuleError("CSV files are limited to 2 MB.", 413, "csv_too_large")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CatalogRuleError("CSV must be encoded as UTF-8.") from None


def _spreadsheet_safe_text(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _perform_transfer(product_id: str, data: dict):
    result = transfer_inventory(
        current_user,
        product_id=product_id,
        source_store_id=str(data.get("source_store_id", "")),
        destination_store_id=str(data.get("destination_store_id", "")),
        quantity=data.get("quantity"),
        reason=data.get("reason", ""),
    )
    source_balance, destination_balance, source_move, destination_move, events = result
    db.session.commit()
    for event in events:
        publish_realtime_event(event.id)
    return result


def _category_company(company_id: str | None = None):
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        abort(403)
    if current_user.is_super_admin:
        company_id = company_id or request.args.get("company_id") or _payload().get("company_id")
    else:
        membership = current_membership(current_user, tenant_container_id=tenant_id)
        if membership is None or not membership.company_id:
            abort(403)
        if company_id and company_id != membership.company_id:
            abort(404)
        company_id = membership.company_id
    company = db.session.execute(select(Company).where(
        Company.id == company_id,
        Company.tenant_container_id == tenant_id,
        Company.is_active.is_(True),
    )).scalar_one_or_none() if company_id else None
    if company is None:
        abort(404)
    return company


def _category_access(company: Company, action: str) -> bool:
    return can_access_data_domain(
        current_user,
        tenant_container_id=company.tenant_container_id,
        domain="product_catalog",
        action=action,
        company_id=company.id,
    )


def _category_rows(company: Company):
    rows = db.session.execute(select(ProductCategory).where(
        ProductCategory.tenant_container_id == company.tenant_container_id,
        ProductCategory.company_id == company.id,
    ).order_by(ProductCategory.name.asc())).scalars().all()
    registered_names = {row.name.casefold() for row in rows}
    product_counts = dict(db.session.execute(select(CatalogProduct.category, func.count(CatalogProduct.id)).where(
        CatalogProduct.tenant_container_id == company.tenant_container_id,
        CatalogProduct.company_id == company.id,
        CatalogProduct.category.is_not(None),
        CatalogProduct.category != "",
    ).group_by(CatalogProduct.category)).all())
    product_names = sorted(product_counts, key=str.casefold)
    result = [{"id": row.id, "name": row.name, "registered": True, "product_count": product_counts.get(row.name, 0)} for row in rows]
    result.extend({"id": None, "name": name, "registered": False, "product_count": product_counts.get(name, 0)} for name in product_names if name.casefold() not in registered_names)
    return result


def _super_admin_company_picker(*, title: str, description: str, endpoint: str):
    """Ask platform administrators to pick a company before opening company-scoped catalog tools."""
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        return redirect(url_for("auth.select_tenant"))
    companies = db.session.execute(
        select(Company)
        .where(Company.tenant_container_id == tenant_id, Company.is_active.is_(True))
        .order_by(Company.name.asc())
    ).scalars().all()
    return render_template(
        "catalog/company_picker.html",
        title=title,
        description=description,
        endpoint_url=url_for(endpoint),
        companies=companies,
    )


@catalog_bp.get("/admin/product-categories")
@login_required
def categories_page():
    if current_user.is_super_admin and not request.args.get("company_id"):
        return _super_admin_company_picker(
            title="Choose a company for categories",
            description="Category management is scoped to one company. Choose the company whose catalog you want to review.",
            endpoint="catalog.categories_page",
        )
    company = _category_company()
    if not _category_access(company, "view"):
        abort(403)
    return render_template("catalog/categories.html", company=company, categories=_category_rows(company), can_edit=_category_access(company, "edit"))


@catalog_bp.get("/api/v1/catalog/categories")
@login_required
def list_categories_api():
    company = _category_company(request.args.get("company_id"))
    if not _category_access(company, "view"):
        return jsonify(error="permission_denied", message="Catalog view access is required."), 403
    return jsonify(categories=_category_rows(company)), 200


@catalog_bp.post("/api/v1/catalog/categories")
@login_required
def create_category_api():
    data = _payload()
    company = _category_company(data.get("company_id"))
    if not _category_access(company, "add"):
        return jsonify(error="permission_denied", message="Catalog category creation is not permitted."), 403
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
        return jsonify(error="invalid_category", message="Category name must contain 1-128 characters."), 400
    name = name.strip()
    existing = db.session.execute(select(ProductCategory).where(
        ProductCategory.tenant_container_id == company.tenant_container_id,
        ProductCategory.company_id == company.id,
        func.lower(ProductCategory.name) == name.casefold(),
    )).scalar_one_or_none()
    if existing:
        return jsonify(error="category_exists", message="That category is already registered."), 409
    category = ProductCategory(tenant_container_id=company.tenant_container_id, company_id=company.id, name=name, created_by_id=current_user.id)
    db.session.add(category)
    db.session.flush()
    db.session.add(AuditEvent(tenant_container_id=company.tenant_container_id, company_id=company.id, actor_user_id=current_user.id, action="catalog.category_created", entity_type="ProductCategory", entity_id=category.id, after_data={"name": name}))
    db.session.commit()
    return jsonify(category={"id": category.id, "name": category.name, "registered": True}), 201


@catalog_bp.patch("/api/v1/catalog/categories/<string:category_id>")
@login_required
def rename_category_api(category_id: str):
    data = _payload()
    company = _category_company(data.get("company_id"))
    if not _category_access(company, "edit"):
        return jsonify(error="permission_denied", message="Catalog category editing is not permitted."), 403
    category = db.session.execute(select(ProductCategory).where(ProductCategory.id == category_id, ProductCategory.tenant_container_id == company.tenant_container_id, ProductCategory.company_id == company.id).with_for_update()).scalar_one_or_none()
    if category is None:
        return jsonify(error="not_found", message="Category not found."), 404
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
        return jsonify(error="invalid_category", message="Category name must contain 1-128 characters."), 400
    name = name.strip()
    duplicate = db.session.execute(select(ProductCategory.id).where(ProductCategory.tenant_container_id == company.tenant_container_id, ProductCategory.company_id == company.id, func.lower(ProductCategory.name) == name.casefold(), ProductCategory.id != category.id)).scalar_one_or_none()
    if duplicate:
        return jsonify(error="category_exists", message="That category is already registered."), 409
    before = category.name
    affected = db.session.execute(select(func.count(CatalogProduct.id)).where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.category == before)).scalar_one()
    db.session.execute(CatalogProduct.__table__.update().where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.category == before).values(category=name))
    category.name = name
    db.session.add(AuditEvent(tenant_container_id=company.tenant_container_id, company_id=company.id, actor_user_id=current_user.id, action="catalog.category_renamed", entity_type="ProductCategory", entity_id=category.id, before_data={"name": before}, after_data={"name": name, "products_updated": affected}))
    db.session.commit()
    return jsonify(category={"id": category.id, "name": category.name, "registered": True}, products_updated=affected), 200


@catalog_bp.delete("/api/v1/catalog/categories/<string:category_id>")
@login_required
def delete_category_api(category_id: str):
    data = _payload()
    company = _category_company(data.get("company_id"))
    if not _category_access(company, "delete"):
        return jsonify(error="permission_denied", message="Catalog category deletion is not permitted."), 403
    category = db.session.execute(select(ProductCategory).where(ProductCategory.id == category_id, ProductCategory.tenant_container_id == company.tenant_container_id, ProductCategory.company_id == company.id).with_for_update()).scalar_one_or_none()
    if category is None:
        return jsonify(error="not_found", message="Category not found."), 404
    name = category.name
    affected = db.session.execute(select(func.count(CatalogProduct.id)).where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.category == name)).scalar_one()
    db.session.execute(CatalogProduct.__table__.update().where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.category == name).values(category=None))
    db.session.add(AuditEvent(tenant_container_id=company.tenant_container_id, company_id=company.id, actor_user_id=current_user.id, action="catalog.category_deleted", entity_type="ProductCategory", entity_id=category.id, before_data={"name": name}, after_data={"products_uncategorized": affected}))
    db.session.delete(category)
    db.session.commit()
    return jsonify(deleted=True, products_uncategorized=affected), 200


def _label_company():
    if not (current_user.is_admin or current_user.has_permission("manage_labels")):
        abort(403)
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        abort(403)
    if current_user.is_super_admin:
        company_id = request.args.get("company_id")
    else:
        membership = current_membership(current_user, tenant_container_id=tenant_id)
        if membership is None or not membership.company_id:
            abort(403)
        company_id = membership.company_id
        if request.args.get("company_id") and request.args.get("company_id") != company_id:
            abort(404)
    company = db.session.execute(select(Company).where(Company.id == company_id, Company.tenant_container_id == tenant_id, Company.is_active.is_(True))).scalar_one_or_none() if company_id else None
    if company is None:
        abort(404)
    stores = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=tenant_id)
    return company, stores


@catalog_bp.get("/admin/label-printing")
@login_required
def label_printing_page():
    if current_user.is_super_admin and not request.args.get("company_id"):
        return _super_admin_company_picker(
            title="Choose a company for label printing",
            description="Product and document labels are scoped to one company. Choose a company to search its products and documents.",
            endpoint="catalog.label_printing_page",
        )
    company, _stores = _label_company()
    return render_template("catalog/labels.html", company=company)


@catalog_bp.get("/api/v1/labels/products")
@login_required
def label_products_api():
    company, stores = _label_company()
    if not (current_user.is_admin or any(can_access_data_domain(current_user, tenant_container_id=company.tenant_container_id, domain="product_catalog", action="view", company_id=company.id, store_id=store_id) for store_id in stores)):
        return jsonify(error="permission_denied", message="Catalog view access is required."), 403
    term = (request.args.get("q") or "").strip()[:80]
    statement = select(CatalogProduct).where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.is_active.is_(True))
    if term:
        statement = statement.where(CatalogProduct.name.ilike(f"%{term}%") | CatalogProduct.sku.ilike(f"%{term}%") | CatalogProduct.barcode.ilike(f"%{term}%"))
    products = db.session.execute(statement.order_by(CatalogProduct.name.asc()).limit(50)).scalars()
    return jsonify(products=[{"id":p.id,"name":p.name,"sku":p.sku,"barcode":p.barcode,"price":str(p.price) if p.price is not None else None} for p in products]), 200


@catalog_bp.get("/api/v1/labels/documents")
@login_required
def label_documents_api():
    company, stores = _label_company()
    if not (current_user.is_admin or any(can_access_data_domain(current_user, tenant_container_id=company.tenant_container_id, domain="sales", action="view", company_id=company.id, store_id=store_id) for store_id in stores)):
        return jsonify(error="permission_denied", message="Sales document view access is required."), 403
    term = (request.args.get("q") or "").strip()[:80]
    if not term or not stores:
        return jsonify(documents=[]), 200
    results = []
    orders = db.session.execute(select(SalesOrder).where(SalesOrder.tenant_container_id == company.tenant_container_id, SalesOrder.company_id == company.id, SalesOrder.origin_store_id.in_(stores), (SalesOrder.order_number.ilike(f"%{term}%") | SalesOrder.invoice_number.ilike(f"%{term}%"))).order_by(SalesOrder.created_at.desc()).limit(20)).scalars()
    results.extend({"type":"invoice","id":o.id,"number":o.invoice_number or o.order_number,"customer":o.customer_name or o.customer_phone} for o in orders)
    notices = db.session.execute(select(DemandNotice).where(DemandNotice.tenant_container_id == company.tenant_container_id, DemandNotice.company_id == company.id, DemandNotice.store_id.in_(stores), DemandNotice.notice_number.ilike(f"%{term}%")).order_by(DemandNotice.created_at.desc()).limit(20)).scalars()
    results.extend({"type":"demand_notice","id":n.id,"number":n.notice_number,"customer":n.customer_name or n.customer_phone} for n in notices)
    quotes = db.session.execute(select(Quotation).where(Quotation.tenant_container_id == company.tenant_container_id, Quotation.company_id == company.id, Quotation.store_id.in_(stores), Quotation.quotation_number.ilike(f"%{term}%")).order_by(Quotation.created_at.desc()).limit(20)).scalars()
    results.extend({"type":"quotation","id":q.id,"number":q.quotation_number,"customer":q.customer_name or q.customer_phone} for q in quotes)
    return jsonify(documents=results[:50]), 200


@catalog_bp.get("/catalog/products/export.csv")
@login_required
def export_products_csv():
    try:
        rows, store, can_view_inventory = list_products(
            current_user,
            store_id=request.args.get("store_id", ""),
            search=request.args.get("q", ""),
            limit=10001,
        )
        if len(rows) > 10000:
            raise CatalogRuleError("CSV export is limited to 10000 matching products.", 413, "csv_too_large")
    except CatalogRuleError as error:
        abort(error.status_code)

    output = io.StringIO(newline="")
    fields = [
        "name", "sku", "barcode", "category", "price", "quantityInStock",
        "expiryDate", "isDemandNoticeProduct", "lowStockThreshold", "lowStockPrice", "imageUrl",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        product = row["product"]
        writer.writerow(
            {
                "name": _spreadsheet_safe_text(product.name),
                "sku": _spreadsheet_safe_text(product.sku),
                "barcode": _spreadsheet_safe_text(product.barcode),
                "category": _spreadsheet_safe_text(product.category),
                "price": format(product.price, ".3f") if product.price is not None else "",
                "quantityInStock": row["stock_quantity"] if can_view_inventory and row["stock_quantity"] is not None else "",
                "expiryDate": product.expiry_date.date().isoformat() if product.expiry_date else "",
                "isDemandNoticeProduct": "true" if product.is_demand_notice_product else "false",
                "lowStockThreshold": row["low_stock_threshold"] if can_view_inventory and row["low_stock_threshold"] is not None else "",
                "lowStockPrice": format(product.low_stock_price, ".3f") if product.low_stock_price is not None else "",
                "imageUrl": _spreadsheet_safe_text(product.image_url),
            }
        )
    response = Response(output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="products_export.csv"'
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@catalog_bp.post("/catalog/products/import")
@login_required
def import_products_csv_page():
    store_id = str(request.form.get("store_id", ""))
    try:
        contents = _read_csv_upload()
        counts, event_ids = import_products_csv(current_user, store_id=store_id, contents=contents)
        db.session.commit()
        for event_id in event_ids:
            publish_realtime_event(event_id)
        flash(
            f"CSV import complete: {counts['created']} created, {counts['updated']} updated, "
            f"{counts['stock_adjustments']} stock adjustments.",
            "success",
        )
    except CatalogRuleError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("CSV import conflicted with existing catalog data; no rows were saved.", "error")
    return redirect(url_for("catalog.products_page", store_id=store_id))


@catalog_bp.post("/catalog/products/<product_id>/transfer")
@login_required
def transfer_inventory_page(product_id: str):
    source_store_id = str(request.form.get("source_store_id", ""))
    try:
        _perform_transfer(product_id, request.form.to_dict(flat=True))
        flash("Stock transferred. Both store balances and movement records were updated.", "success")
    except CatalogRuleError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("The transfer conflicted with another transaction; no stock was moved.", "error")
    return redirect(url_for("catalog.products_page", store_id=source_store_id))


@catalog_bp.post("/api/v1/products/<product_id>/transfers")
@login_required
def transfer_inventory_api(product_id: str):
    try:
        source_balance, destination_balance, source_move, destination_move, events = _perform_transfer(
            product_id, _payload()
        )
        return jsonify(
            transfer={
                "product_id": source_balance.product_id,
                "source_store_id": source_balance.store_id,
                "source_quantity_on_hand": source_balance.quantity_on_hand,
                "destination_store_id": destination_balance.store_id,
                "destination_quantity_on_hand": destination_balance.quantity_on_hand,
                "source_movement_id": source_move.id,
                "destination_movement_id": destination_move.id,
                "event_ids": [event.id for event in events],
            }
        ), 201
    except CatalogRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="The stock transfer conflicted with another transaction."), 409


@catalog_bp.route("/catalog/products", methods=["GET", "POST"])
@login_required
def products_page():
    if current_tenant_container_id(current_user) is None:
        return redirect(url_for("auth.select_tenant"))
    try:
        stores = accessible_stores(current_user)
    except CatalogRuleError as error:
        abort(error.status_code)
    store_choices = [(store.id, f"{store.name} ({store.code})") for store in stores]
    allowed_store_ids = {store.id for store in stores}
    form = ProductForm()
    form.store_id.choices = store_choices

    selected_store_id = request.values.get("store_id", "")
    if selected_store_id not in allowed_store_ids:
        selected_store_id = stores[0].id if stores else ""
    if request.method == "GET":
        form.store_id.data = selected_store_id

    selected_store = next((store for store in stores if store.id == selected_store_id), None)
    can_add_product = bool(
        selected_store
        and can_access_data_domain(
            current_user,
            tenant_container_id=selected_store.tenant_container_id,
            domain="product_catalog",
            action="add",
            company_id=selected_store.company_id,
            store_id=selected_store.id,
        )
    )
    can_edit_product = bool(
        selected_store
        and can_access_data_domain(
            current_user,
            tenant_container_id=selected_store.tenant_container_id,
            domain="product_catalog",
            action="edit",
            company_id=selected_store.company_id,
            store_id=selected_store.id,
        )
    )
    can_set_low_stock_threshold = bool(
        selected_store
        and can_access_data_domain(
            current_user,
            tenant_container_id=selected_store.tenant_container_id,
            domain="inventory",
            action="edit",
            company_id=selected_store.company_id,
            store_id=selected_store.id,
        )
    )

    if request.method == "POST" and form.validate_on_submit():
        try:
            store = next((store for store in stores if store.id == form.store_id.data), None)
            if store is None:
                raise CatalogRuleError("Select a store you are authorized to access.", 403, "store_forbidden")
            create_product(
                current_user,
                company_id=store.company_id,
                name=form.name.data,
                sku=form.sku.data,
                barcode=form.barcode.data,
                category=form.category.data,
                price=form.price.data,
                low_stock_price=form.low_stock_price.data,
                expiry_date=form.expiry_date.data,
                is_demand_notice_product=form.is_demand_notice_product.data,
                low_stock_threshold=form.low_stock_threshold.data,
                store_id=store.id,
            )
            db.session.commit()
            flash("Product added to the company catalog.", "success")
            return redirect(url_for("catalog.products_page", store_id=store.id))
        except CatalogRuleError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("The product could not be saved because it conflicts with existing data.", "error")

    products = []
    can_view_inventory = False
    can_adjust_inventory = False
    can_transfer_inventory = False
    transfer_stores = []
    realtime_cursor = 0
    if selected_store:
        realtime_cursor = int(
            db.session.execute(
                select(func.max(RealtimeEvent.id)).where(
                    RealtimeEvent.tenant_container_id == selected_store.tenant_container_id,
                    RealtimeEvent.store_id == selected_store.id,
                )
            ).scalar_one()
            or 0
        )
        try:
            products, _store, can_view_inventory = list_products(
                current_user,
                store_id=selected_store.id,
                search=request.args.get("q", ""),
            )
            can_adjust_inventory = can_view_inventory and any(
                can_access_data_domain(
                    current_user,
                    tenant_container_id=selected_store.tenant_container_id,
                    domain="inventory",
                    action=action,
                    company_id=selected_store.company_id,
                    store_id=selected_store.id,
                )
                for action in ("add", "edit")
            )
            can_edit_source_inventory = can_access_data_domain(
                current_user,
                tenant_container_id=selected_store.tenant_container_id,
                domain="inventory",
                action="edit",
                company_id=selected_store.company_id,
                store_id=selected_store.id,
            )
            transfer_stores = [
                store
                for store in stores
                if store.company_id == selected_store.company_id
                and store.id != selected_store.id
                and can_access_data_domain(
                    current_user,
                    tenant_container_id=selected_store.tenant_container_id,
                    domain="inventory",
                    action="view",
                    company_id=store.company_id,
                    store_id=store.id,
                )
                and can_access_data_domain(
                    current_user,
                    tenant_container_id=selected_store.tenant_container_id,
                    domain="inventory",
                    action="add",
                    company_id=store.company_id,
                    store_id=store.id,
                )
            ]
            can_transfer_inventory = bool(can_view_inventory and can_edit_source_inventory and transfer_stores)
        except CatalogRuleError as error:
            if error.status_code == 403:
                abort(403)
            abort(error.status_code)

    return render_template(
        "catalog/products.html",
        stores=stores,
        selected_store=selected_store,
        products=products,
        form=form,
        can_add_product=can_add_product,
        can_edit_product=can_edit_product,
        can_set_low_stock_threshold=can_set_low_stock_threshold,
        can_view_inventory=can_view_inventory,
        can_adjust_inventory=can_adjust_inventory,
        can_transfer_inventory=can_transfer_inventory,
        transfer_stores=transfer_stores,
        search=request.args.get("q", ""),
        realtime_cursor=realtime_cursor,
    )


@catalog_bp.post("/catalog/products/<product_id>/inventory")
@login_required
def adjust_inventory_page(product_id: str):
    form = InventoryAdjustmentForm()
    if not form.validate_on_submit():
        flash("Enter a whole-number stock change and a reason.", "error")
        return redirect(url_for("catalog.products_page", store_id=request.form.get("store_id", "")))
    try:
        balance, _movement, event, _replayed = adjust_inventory(
            current_user,
            product_id,
            store_id=form.store_id.data,
            quantity_delta=form.delta.data,
            reason=form.reason.data,
        )
        db.session.commit()
        publish_realtime_event(event.id)
        flash(f"Stock updated. New on-hand quantity: {balance.quantity_on_hand}.", "success")
        return redirect(url_for("catalog.products_page", store_id=form.store_id.data))
    except CatalogRuleError as error:
        return _inventory_error_response(error)
    except IntegrityError:
        db.session.rollback()
        flash("The stock update conflicted with another transaction. Reload and try again.", "error")
        return redirect(url_for("catalog.products_page", store_id=form.store_id.data))


@catalog_bp.get("/api/v1/products")
@login_required
def products_api():
    try:
        rows, store, can_view_inventory = list_products(
            current_user,
            store_id=request.args.get("store_id", ""),
            search=request.args.get("q", ""),
        )
        return jsonify(
            store={"id": store.id, "company_id": store.company_id, "name": store.name},
            can_view_inventory=can_view_inventory,
            products=[_row_dict(row) for row in rows],
        )
    except CatalogRuleError as error:
        return _error_response(error)


@catalog_bp.post("/api/v1/products")
@login_required
def create_product_api():
    data = _payload()
    try:
        product = create_product(
            current_user,
            company_id=str(data.get("company_id", "")),
            name=data.get("name", ""),
            sku=data.get("sku"),
            barcode=data.get("barcode"),
            category=data.get("category"),
            price=data.get("price"),
            low_stock_price=data.get("low_stock_price"),
            expiry_date=data.get("expiry_date"),
            is_demand_notice_product=data.get("is_demand_notice_product", False),
            low_stock_threshold=data.get("low_stock_threshold"),
            image_url=data.get("image_url"),
            store_id=data.get("store_id"),
        )
        db.session.commit()
        return jsonify(product=product_dict(product)), 201
    except CatalogRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Product conflicts with existing data."), 409


@catalog_bp.patch("/api/v1/products/<product_id>")
@login_required
def update_product_api(product_id: str):
    data = _payload()
    store_id = data.pop("store_id", None)
    try:
        product = update_product(current_user, product_id, changes=data, store_id=store_id)
        db.session.commit()
        return jsonify(product=product_dict(product))
    except CatalogRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Product conflicts with existing data."), 409


@catalog_bp.delete("/api/v1/products/<product_id>")
@login_required
def archive_product_api(product_id: str):
    try:
        product = archive_product(current_user, product_id)
        db.session.commit()
        return jsonify(product=product_dict(product))
    except CatalogRuleError as error:
        return _error_response(error)


@catalog_bp.post("/api/v1/products/<product_id>/inventory")
@login_required
def adjust_inventory_api(product_id: str):
    data = _payload()
    try:
        idempotency_key = str(data.get("idempotency_key", "")).strip() or None
        balance, movement, event, replayed = adjust_inventory(
            current_user,
            product_id,
            store_id=str(data.get("store_id", "")),
            quantity_delta=data.get("quantity_delta", data.get("delta")),
            reason=data.get("reason", ""),
            idempotency_key=idempotency_key,
        )
        db.session.commit()
        if event is not None:
            publish_realtime_event(event.id)
        return jsonify(
            inventory={
                "id": balance.id,
                "store_id": balance.store_id,
                "product_id": balance.product_id,
                "quantity_on_hand": balance.quantity_on_hand,
            },
            movement={
                "id": movement.id,
                "movement_type": movement.movement_type,
                "quantity_delta": movement.quantity_delta,
                "reason": movement.reason,
                "created_at": movement.created_at.isoformat(),
            },
            event={"id": event.id, "type": event.event_type} if event is not None else None,
            replayed=replayed,
        ), 200 if replayed else 201
    except CatalogRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="The stock update conflicted with another transaction."), 409


@catalog_bp.get("/api/v1/products/<product_id>/inventory-movements")
@login_required
def inventory_movements_api(product_id: str):
    tenant_id = current_tenant_container_id(current_user)
    product = db.session.execute(
        select(CatalogProduct).where(
            CatalogProduct.id == product_id,
            CatalogProduct.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if product is None:
        return jsonify(error="not_found"), 404
    store_id = request.args.get("store_id", "")
    store = db.session.execute(
        select(Store).where(Store.id == store_id, Store.tenant_container_id == tenant_id, Store.is_active.is_(True))
    ).scalar_one_or_none()
    if store is None or not can_access_store(
        current_user,
        store.id,
        company_id=store.company_id,
        tenant_container_id=tenant_id,
    ):
        return jsonify(error="not_found"), 404
    if not can_access_data_domain(
        current_user,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="view",
        company_id=product.company_id,
    ) or not can_access_data_domain(
        current_user,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="view",
        company_id=store.company_id,
        store_id=store.id,
    ):
        return jsonify(error="forbidden"), 403

    movements = db.session.execute(
        select(InventoryMovement)
        .where(
            InventoryMovement.tenant_container_id == tenant_id,
            InventoryMovement.company_id == store.company_id,
            InventoryMovement.store_id == store.id,
            InventoryMovement.product_owner_company_id == product.company_id,
            InventoryMovement.product_id == product.id,
        )
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .limit(100)
    ).scalars()
    return jsonify(
        movements=[
            {
                "id": movement.id,
                "movement_type": movement.movement_type,
                "quantity_delta": movement.quantity_delta,
                "reason": movement.reason,
                "actor_user_id": movement.actor_user_id,
                "created_at": movement.created_at.isoformat(),
            }
            for movement in movements
        ]
    )
