"""Server-rendered catalog screen and authenticated JSON product APIs."""

import csv
import io

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..auth.store_scope import can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import CatalogProduct, InventoryMovement, RealtimeEvent, Store
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
        balance, _movement, event = adjust_inventory(
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
        balance, movement, event = adjust_inventory(
            current_user,
            product_id,
            store_id=str(data.get("store_id", "")),
            quantity_delta=data.get("quantity_delta", data.get("delta")),
            reason=data.get("reason", ""),
        )
        db.session.commit()
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
            event={"id": event.id, "type": event.event_type},
        ), 201
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
