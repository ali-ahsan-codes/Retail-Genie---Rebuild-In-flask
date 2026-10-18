"""Tenant and store administration, scoped server-side to the signed-in actor."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.permissions import company_admin_required, super_admin_required
from ..extensions import db
from ..models import AuditEvent, BillingSeries, Company, ContainerMembership, INVOICE_CATEGORIES, Store, TenantContainer, User, UserStoreAssignment, normalize_username
from ..tenancy.service import seed_tenant_data_policies
from ..auth.tenant_context import current_membership
from ..models.user import is_valid_username
from .tenancy_forms import AssignmentForm, BillingSettingsForm, CreateCompanyForm, StoreForm

tenancy_admin_bp = Blueprint("tenancy_admin", __name__, url_prefix="/admin")

_ASSIGNABLE_STAFF_ROLES = {"manager", "salesperson", "cashier", "storekeeper", "logistics", "auditor", "display", "express"}


def _company_or_404(company_id: str) -> Company:
    company = db.session.get(Company, company_id)
    if company is None or not company.is_active:
        abort(404)
    if not current_user.is_super_admin:
        membership = current_membership(current_user, tenant_container_id=company.tenant_container_id)
        if membership is None or membership.company_id != company.id:
            abort(404)
    return company


def _audit(company_id: str, action: str, entity_type: str, entity_id: str, *, store_id: str | None = None, before=None, after=None, reason=None):
    db.session.add(
        AuditEvent(
            tenant_container_id=db.session.get(Company, company_id).tenant_container_id,
            company_id=company_id,
            store_id=store_id,
            actor_user_id=current_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            before_data=before,
            after_data=after,
        )
    )


@tenancy_admin_bp.route("/companies", methods=["GET", "POST"])
@super_admin_required
def companies():
    form = CreateCompanyForm()
    if form.validate_on_submit():
        slug = (form.slug.data or "").strip().lower()
        username = normalize_username(form.admin_username.data or "")
        if not is_valid_username(username):
            form.admin_username.errors.append("Use 3–48 characters: letters, numbers, dots, underscores, or hyphens.")
        elif TenantContainer.query.filter_by(slug=slug).first():
            form.slug.errors.append("That tenant-container code is already in use.")
        elif User.query.filter_by(username=username).first():
            form.admin_username.errors.append("That username is already in use.")
        else:
            container = TenantContainer(
                name=(form.company_name.data or "").strip(),
                slug=slug,
                timezone=(form.timezone.data or "Asia/Muscat").strip(),
            )
            db.session.add(container)
            db.session.flush()
            seed_tenant_data_policies(container.id)
            company = Company(
                tenant_container_id=container.id,
                name=(form.company_name.data or "").strip(),
                slug=slug,
                timezone=container.timezone,
            )
            db.session.add(company)
            db.session.flush()
            prefixes = {"cash": "CASH-", "bank": "BANK-", "bank_transfer": "BT-", "other": "OTH-"}
            db.session.add_all(
                [
                    BillingSeries(tenant_container_id=container.id, company_id=company.id, category=category, prefix=prefixes[category], next_number=1)
                    for category in INVOICE_CATEGORIES
                ]
            )
            store = Store(
                tenant_container_id=container.id,
                company_id=company.id,
                code=(form.store_code.data or "").strip().upper(),
                name=(form.store_name.data or "").strip(),
            )
            company_admin = User(
                company_id=company.id,
                username=username,
                role="company_admin",
                permissions=[],
                force_password_change=True,
            )
            company_admin.set_password(form.admin_password.data or "")
            db.session.add_all([store, company_admin])
            db.session.flush()
            db.session.add(
                ContainerMembership(
                    tenant_container_id=container.id,
                    user_id=company_admin.id,
                    company_id=company.id,
                    role="company_admin",
                    permissions=[],
                    is_default=True,
                    is_active=True,
                )
            )
            _audit(company.id, "company.created", "company", company.id, after={"name": company.name, "slug": company.slug, "tenant_container_id": container.id})
            _audit(company.id, "store.created", "store", store.id, store_id=store.id, after={"name": store.name, "code": store.code})
            _audit(company.id, "company_admin.created", "user", company_admin.id, after={"role": company_admin.role, "username": username})
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.slug.errors.append("Company code, store code, or username is already in use.")
            else:
                flash(f"Company '{company.name}' and its first store and Company Admin were created.", "success")
                return redirect(url_for("tenancy_admin.companies"))

    companies_list = Company.query.order_by(Company.name.asc()).all()
    return render_template("admin/companies.html", form=form, companies=companies_list)


@tenancy_admin_bp.route(
    "/containers/<string:tenant_container_id>/companies/<string:parent_company_id>/new",
    methods=["GET", "POST"],
)
@company_admin_required
def create_child_company(tenant_container_id: str, parent_company_id: str):
    """Create a nested operating company without creating a new tenant boundary."""
    container = db.session.get(TenantContainer, tenant_container_id)
    parent = db.session.get(Company, parent_company_id)
    if container is None or not container.is_active or parent is None or not parent.is_active:
        abort(404)
    if parent.tenant_container_id != container.id:
        abort(404)
    if not current_user.is_super_admin:
        membership = current_membership(current_user, tenant_container_id=container.id)
        if membership is None or membership.company_id != parent.id:
            abort(404)

    form = CreateCompanyForm()
    if form.validate_on_submit():
        slug = (form.slug.data or "").strip().lower()
        username = normalize_username(form.admin_username.data or "")
        if not is_valid_username(username):
            form.admin_username.errors.append("Use 3–48 characters: letters, numbers, dots, underscores, or hyphens.")
        elif Company.query.filter_by(tenant_container_id=container.id, slug=slug).first():
            form.slug.errors.append("That company code is already in use in this container.")
        elif User.query.filter_by(username=username).first():
            form.admin_username.errors.append("That username is already in use.")
        else:
            company = Company(
                tenant_container_id=container.id,
                parent_company_id=parent.id,
                name=(form.company_name.data or "").strip(),
                slug=slug,
                timezone=(form.timezone.data or container.timezone).strip(),
            )
            db.session.add(company)
            db.session.flush()
            prefixes = {"cash": "CASH-", "bank": "BANK-", "bank_transfer": "BT-", "other": "OTH-"}
            db.session.add_all(
                [
                    BillingSeries(tenant_container_id=container.id, company_id=company.id, category=category, prefix=prefixes[category], next_number=1)
                    for category in INVOICE_CATEGORIES
                ]
            )
            store = Store(
                tenant_container_id=container.id,
                company_id=company.id,
                code=(form.store_code.data or "").strip().upper(),
                name=(form.store_name.data or "").strip(),
            )
            company_admin = User(
                company_id=company.id,
                username=username,
                role="company_admin",
                permissions=[],
                force_password_change=True,
            )
            company_admin.set_password(form.admin_password.data or "")
            db.session.add_all([store, company_admin])
            db.session.flush()
            db.session.add(
                ContainerMembership(
                    tenant_container_id=container.id,
                    user_id=company_admin.id,
                    company_id=company.id,
                    role="company_admin",
                    permissions=[],
                    is_default=True,
                    is_active=True,
                )
            )
            _audit(
                company.id,
                "company.created",
                "company",
                company.id,
                after={"name": company.name, "slug": company.slug, "parent_company_id": parent.id},
            )
            _audit(company.id, "store.created", "store", store.id, store_id=store.id, after={"name": store.name, "code": store.code})
            _audit(company.id, "company_admin.created", "user", company_admin.id, after={"role": company_admin.role, "username": username})
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.slug.errors.append("Company code, store code, or username is already in use.")
            else:
                flash(f"Child company '{company.name}' was added to {container.name}.", "success")
                return redirect(url_for("tenancy_admin.companies" if current_user.is_super_admin else "tenancy_admin.stores", **({} if current_user.is_super_admin else {"company_id": parent.id})))

    return render_template(
        "admin/child_company.html",
        form=form,
        container=container,
        parent_company=parent,
    )


@tenancy_admin_bp.post("/companies/<string:company_id>/toggle-active")
@super_admin_required
def toggle_company(company_id: str):
    company = db.session.get(Company, company_id)
    if company is None:
        abort(404)
    before = {"is_active": company.is_active}
    company.is_active = not company.is_active
    company.updated_at = db.func.now()
    _audit(company.id, "company.status_changed", "company", company.id, before=before, after={"is_active": company.is_active})
    db.session.commit()
    flash(f"Company '{company.name}' is now {'active' if company.is_active else 'inactive'}.", "success")
    return redirect(url_for("tenancy_admin.companies"))


@tenancy_admin_bp.route("/companies/<string:company_id>/stores", methods=["GET", "POST"])
@company_admin_required
def stores(company_id: str):
    company = _company_or_404(company_id)
    form = StoreForm()
    if form.validate_on_submit():
        store = Store(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            code=(form.code.data or "").strip().upper(),
            name=(form.name.data or "").strip(),
        )
        db.session.add(store)
        db.session.flush()
        _audit(company.id, "store.created", "store", store.id, store_id=store.id, after={"name": store.name, "code": store.code})
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.code.errors.append("That store code is already in use in this company.")
        else:
            flash(f"Store '{store.name}' created.", "success")
            return redirect(url_for("tenancy_admin.stores", company_id=company.id))
    store_list = Store.query.filter_by(company_id=company.id).order_by(Store.code.asc()).all()
    return render_template("admin/stores.html", form=form, company=company, stores=store_list)


@tenancy_admin_bp.route("/companies/<string:company_id>/billing", methods=["GET", "POST"])
@company_admin_required
def billing_settings(company_id: str):
    company = _company_or_404(company_id)
    form = BillingSettingsForm()
    defaults = {"cash": "CASH-", "bank": "BANK-", "bank_transfer": "BT-", "other": "OTH-"}
    series_rows = BillingSeries.query.filter_by(company_id=company.id).all()
    series_by_category = {series.category: series for series in series_rows}
    missing = [category for category in INVOICE_CATEGORIES if category not in series_by_category]
    if missing:
        for category in missing:
            series = BillingSeries(tenant_container_id=company.tenant_container_id, company_id=company.id, category=category, prefix=defaults[category], next_number=1)
            db.session.add(series)
            series_by_category[category] = series
        db.session.commit()

    if request.method == "GET":
        form.mixed_tender_category.data = company.mixed_tender_category
        for category in INVOICE_CATEGORIES:
            getattr(form, f"{category}_prefix").data = series_by_category[category].prefix
            getattr(form, f"{category}_next_number").data = series_by_category[category].next_number

    if form.validate_on_submit():
        values = {
            category: {
                "prefix": (getattr(form, f"{category}_prefix").data or "").strip().upper(),
                "next_number": getattr(form, f"{category}_next_number").data,
            }
            for category in INVOICE_CATEGORIES
        }
        prefixes = [entry["prefix"] for entry in values.values()]
        if len(set(prefixes)) != len(prefixes):
            form.cash_prefix.errors.append("Each payment category must use a different prefix.")
        for category, entry in values.items():
            if entry["next_number"] < series_by_category[category].next_number:
                getattr(form, f"{category}_next_number").errors.append("Invoice numbers cannot be moved backwards.")
        if not any(field.errors for field in form):
            before = {
                "mixed_tender_category": company.mixed_tender_category,
                "series": {
                    category: {"prefix": series_by_category[category].prefix, "next_number": series_by_category[category].next_number}
                    for category in INVOICE_CATEGORIES
                },
            }
            company.mixed_tender_category = form.mixed_tender_category.data
            for category, entry in values.items():
                series_by_category[category].prefix = entry["prefix"]
                series_by_category[category].next_number = entry["next_number"]
            after = {
                "mixed_tender_category": company.mixed_tender_category,
                "series": values,
            }
            _audit(company.id, "billing_settings.updated", "billing_settings", company.id, before=before, after=after)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.cash_prefix.errors.append("Prefixes must be unique within the company.")
            else:
                flash("Mixed-tender classification and invoice series saved.", "success")
                return redirect(url_for("tenancy_admin.billing_settings", company_id=company.id))

    return render_template("admin/billing_settings.html", form=form, company=company)


@tenancy_admin_bp.route("/store-assignments", methods=["GET", "POST"])
@company_admin_required
def store_assignments(): 
    form = AssignmentForm()
    if current_user.is_super_admin:
        companies_list = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all()
        form.company_id.choices = [(company.id, company.name) for company in companies_list]
        requested_company_id = form.company_id.data or request.args.get("company_id")
        if requested_company_id not in {company.id for company in companies_list}:
            requested_company_id = companies_list[0].id if companies_list else None
        if requested_company_id and not form.company_id.data:
            form.company_id.data = requested_company_id
        company_id = requested_company_id
    else:
        companies_list = []
        membership = current_membership(current_user)
        company_id = membership.company_id if membership else None
        form.company_id.choices = [(company_id, "My company")] if company_id else []
        form.company_id.data = company_id

    company = db.session.get(Company, company_id) if company_id else None
    if company is None or not company.is_active:
        if current_user.is_super_admin:
            flash("Create an active company before assigning staff to stores.", "info")
            return redirect(url_for("tenancy_admin.companies"))
        abort(404)
    if not current_user.is_super_admin:
        membership = current_membership(current_user, tenant_container_id=company.tenant_container_id)
        if membership is None or membership.company_id != company.id:
            abort(404)

    staff_rows = db.session.execute(
        select(User, ContainerMembership)
        .join(ContainerMembership, ContainerMembership.user_id == User.id)
        .where(
            ContainerMembership.tenant_container_id == company.tenant_container_id,
            ContainerMembership.company_id == company.id,
            ContainerMembership.role.in_(_ASSIGNABLE_STAFF_ROLES),
            ContainerMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.username.asc())
    ).all()
    staff = [user for user, _membership in staff_rows]
    staff_roles = {user.id: membership.role for user, membership in staff_rows}
    store_list = Store.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id, is_active=True).order_by(Store.code.asc()).all()
    form.user_id.choices = [(user.id, f"{user.username} — {staff_roles[user.id]}") for user in staff]
    form.store_id.choices = [(store.id, f"{store.code} — {store.name}") for store in store_list]

    if form.validate_on_submit():
        target = db.session.get(User, form.user_id.data)
        target_membership = ContainerMembership.query.filter_by(
            tenant_container_id=company.tenant_container_id,
            user_id=form.user_id.data,
            company_id=company.id,
            is_active=True,
        ).first()
        target_store = db.session.get(Store, form.store_id.data)
        if target is None or target_membership is None or target_membership.role not in _ASSIGNABLE_STAFF_ROLES:
            abort(404)
        if target_store is None or target_store.tenant_container_id != company.tenant_container_id or target_store.company_id != company.id or not target_store.is_active:
            abort(404)
        assignment = UserStoreAssignment.query.filter_by(tenant_container_id=company.tenant_container_id, user_id=target.id, store_id=target_store.id).first()
        requested_shared_bill_access = bool(form.can_view_shared_bills.data)
        if current_user.is_super_admin:
            allow_shared_bills = requested_shared_bill_access
        else:
            if requested_shared_bill_access:
                abort(403)
            allow_shared_bills = assignment.can_view_shared_bills if assignment else False
        if assignment:
            before = {"is_active": assignment.is_active, "can_view_shared_bills": assignment.can_view_shared_bills}
            assignment.company_id = company.id
            assignment.assigned_by_id = current_user.id
            assignment.is_active = True
            assignment.can_view_shared_bills = allow_shared_bills
            assignment.updated_at = db.func.now()
            action = "store_assignment.updated"
        else:
            before = None
            assignment = UserStoreAssignment(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                user_id=target.id,
                store_id=target_store.id,
                assigned_by_id=current_user.id,
                can_view_shared_bills=allow_shared_bills,
                is_active=True,
            )
            db.session.add(assignment)
            action = "store_assignment.created"
        db.session.flush()
        _audit(
            company.id,
            action,
            "user_store_assignment",
            assignment.id,
            store_id=target_store.id,
            before=before,
            after={"user_id": target.id, "store_id": target_store.id, "can_view_shared_bills": allow_shared_bills, "is_active": True},
        )
        db.session.commit()
        flash(f"Store access for '{target.username}' saved.", "success")
        return redirect(url_for("tenancy_admin.store_assignments", company_id=company.id))

    assignments = (
        UserStoreAssignment.query.join(User, User.id == UserStoreAssignment.user_id)
        .join(Store, (Store.id == UserStoreAssignment.store_id) & (Store.company_id == UserStoreAssignment.company_id) & (Store.tenant_container_id == UserStoreAssignment.tenant_container_id))
        .filter(UserStoreAssignment.tenant_container_id == company.tenant_container_id, UserStoreAssignment.company_id == company.id)
        .order_by(User.username.asc(), Store.code.asc())
        .all()
    )
    assignment_rows = [
        {"assignment": assignment, "user": db.session.get(User, assignment.user_id), "store": db.session.get(Store, assignment.store_id)}
        for assignment in assignments
    ]
    return render_template(
        "admin/store_assignments.html",
        form=form,
        company=company,
        companies=companies_list,
        assignments=assignment_rows,
        is_super_admin=current_user.is_super_admin,
    )


@tenancy_admin_bp.post("/store-assignments/<string:assignment_id>/revoke")
@company_admin_required
def revoke_store_assignment(assignment_id: str):
    assignment = db.session.get(UserStoreAssignment, assignment_id)
    if assignment is None:
        abort(404)
    if not current_user.is_super_admin:
        target_company = db.session.get(Company, assignment.company_id)
        membership = current_membership(current_user, tenant_container_id=assignment.tenant_container_id)
        if target_company is None or membership is None or membership.company_id != assignment.company_id:
            abort(404)
    if not assignment.is_active:
        return redirect(url_for("tenancy_admin.store_assignments", company_id=assignment.company_id))
    before = {"is_active": assignment.is_active, "can_view_shared_bills": assignment.can_view_shared_bills}
    assignment.is_active = False
    assignment.can_view_shared_bills = False
    assignment.assigned_by_id = current_user.id
    assignment.updated_at = db.func.now()
    _audit(
        assignment.company_id,
        "store_assignment.revoked",
        "user_store_assignment",
        assignment.id,
        store_id=assignment.store_id,
        before=before,
        after={"is_active": False, "can_view_shared_bills": False},
    )
    db.session.commit()
    flash("Store access revoked.", "success")
    return redirect(url_for("tenancy_admin.store_assignments", company_id=assignment.company_id))
