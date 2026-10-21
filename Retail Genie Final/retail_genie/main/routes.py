"""Role-aware home dashboard for the Flask business modules."""

from io import BytesIO

from flask import Blueprint, Response, abort, render_template, url_for
from flask_login import current_user, login_required

from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..extensions import db
from ..models import Company, TenantContainer
from ..share import app_login_url

main_bp = Blueprint("main", __name__)


@main_bp.get("/app-qr.svg")
def app_login_qr():
    """Render a request-specific SVG QR code for the shared login URL."""
    target_url = app_login_url()
    if not target_url:
        abort(503, description="Set PUBLIC_BASE_URL or make a LAN IPv4 route available to this server.")

    import qrcode
    from qrcode.image.svg import SvgPathImage

    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    code.add_data(target_url)
    code.make(fit=True)
    svg = code.make_image(image_factory=SvgPathImage)
    buffer = BytesIO()
    svg.save(buffer)
    response = Response(buffer.getvalue(), mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Vary"] = "Host"
    return response


def _dashboard_cards():

    cards = []

    def add(group, title, description, endpoint, icon, *, permission=None, any_permission=(), **values):
        if permission and not current_user.has_permission(permission):
            return
        if any_permission and not any(current_user.has_permission(item) for item in any_permission):
            return
        cards.append({
            "group": group,
            "title": title,
            "description": description,
            "url": url_for(endpoint, **values),
            "icon": icon,
        })

    add("Daily work", "Point of sale", "Create a bill, find an open order, add items, and record payment.", "sales.point_of_sale", "POS", permission="use_sales_pos")
    add("Daily work", "Express checkout", "Scan or search products and complete a quick sale.", "express.express_page", "EC", permission="express_checkout")
    add("Daily work", "Products & inventory", "Search the catalog, review stock, or submit an authorized adjustment.", "catalog.products_page", "ST", any_permission=("product_catalog.view", "manage_products", "inventory.view"))
    add("Daily work", "Orders & fulfillment", "Review open and completed orders and update delivery status.", "sales.admin_orders_page", "OR", any_permission=("sales.view", "manage_orders"))
    add("Daily work", "Returns & refunds", "Find a completed sale and process an authorized return.", "sales.returns_page", "RT", any_permission=("sales.view", "manage_orders", "use_sales_pos"))
    add("Daily work", "Removal approvals", "Review pending item-removal requests with reasons and audit history.", "sales.removal_approvals_page", "AP", any_permission=("manage_orders", "sales.view"))
    add("Daily work", "Daily closeout", "Submit or review counted cash, bank, and mixed-tender collections.", "sales.daily_cashup_page", "CU", any_permission=("manage_settings", "manage_orders", "use_sales_pos"))
    add("Daily work", "Supply chain", "Manage suppliers, purchase orders, receiving, and logistics.", "scm.scm_dashboard", "SC", any_permission=("manage_suppliers", "create_pos", "approve_pos", "receive_stock", "manage_logistics"))
    add("Daily work", "Stock audits", "Create assigned counts, capture evidence, and reconcile variances.", "stock_audits.audits_page", "AU", any_permission=("manage_audits", "conduct_audits"))
    add("Daily work", "Attendance & breaks", "Record attendance and manage your work breaks.", "attendance.attendance_page", "AT")
    add("Daily work", "Messages", "Open private conversations and send team updates.", "messaging.messaging_page", "MS")
    add("Daily work", "My files", "Access files shared with your account.", "cloud.my_cloud_page", "FI")
    add("Insights", "Sales reports", "Review sales activity and available performance reports.", "reports.salesperson_reports_page", "RP", any_permission=("view_reports", "view_salesperson_reports"))
    add("Insights", "Activity log", "Review authorized audit and activity history.", "reports.activity_logs_page", "LG", permission="view_activity_logs")
    add("Workspace setup", "Categories", "Maintain authorized product categories.", "catalog.categories_page", "CT", any_permission=("product_catalog.edit", "manage_products"))
    add("Workspace setup", "Barcode & labels", "Search products and business documents, then print durable labels.", "catalog.label_printing_page", "BC", any_permission=("manage_labels", "manage_products"))
    add("Workspace setup", "Demand notices", "Create and track demand notices and fulfillment.", "commercial.demand_notices_page", "DN", any_permission=("sales.view", "manage_orders"))
    add("Workspace setup", "Quotations", "Prepare, print, and convert customer quotations.", "commercial.quotations_page", "QT", any_permission=("sales.view", "manage_orders"))
    add("Workspace setup", "Settings", "Configure company-wide tax, discounts, billing, and preferences.", "settings.settings_index", "SE", any_permission=("manage_settings", "manage_commissions"))
    add("Administration", "Accounts & permissions", "Create staff accounts and manage their role permissions.", "admin.users", "US", any_permission=("manage_users", "manage_accounts"))
    if current_user.is_company_admin:
        add("Administration", "Subscription & plan", "Review your tenant plan, usage, OMR invoices, and request a plan change.", "saas.tenant_portal", "SA")
    if current_user.is_super_admin:
        add("Administration", "SaaS plans", "Manage subscription tiers, OMR prices, and tenant usage limits.", "saas.plans", "PL")
        add("Administration", "Tenant subscriptions", "Assign plans, review status, and issue or reconcile manual subscription invoices.", "saas.subscriptions", "SU")
        add("Administration", "Plan requests", "Review tenant plan requests and maintain an auditable decision trail.", "saas.plan_requests", "RQ")
        add("Administration", "Companies & stores", "Set up companies and active branches inside the selected tenant.", "tenancy_admin.companies", "CO")
        add("Administration", "Data policies", "Review tenant data-sharing modes and scoped grants.", "tenancy_admin.domain_policy_index", "DP")
    if current_user.is_company_admin:
        add("Administration", "Store assignments", "Review which stores each staff member may access.", "tenancy_admin.store_assignments", "SA", company_id=current_user.company_id)
        add("Administration", "Billing setup", "Configure tender-specific invoice series and mixed-tender rules.", "tenancy_admin.billing_settings", "BI", company_id=current_user.company_id)
    if current_user.is_admin:
        add("Administration", "Database backups", "Review the private MySQL backup schedule and run history.", "admin_backups.settings", "BK")
    if current_user.effective_role == "display" or current_user.has_permission("view_admin_dashboard"):
        add("Special displays", "LCD order display", "Open the read-only display for an authorized store.", "display.lcd_display_page", "TV")

    return cards


@main_bp.get("/")
@main_bp.get("/dashboard")
@login_required
def dashboard():
    tenant_id = current_tenant_container_id(current_user)
    tenant = db.session.get(TenantContainer, tenant_id) if tenant_id else None
    membership = current_membership(current_user, tenant_container_id=tenant_id) if tenant_id else None
    active_company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
    return render_template(
        "main/dashboard.html",
        dashboard_cards=_dashboard_cards(),
        active_tenant=tenant,
        active_membership=membership,
        active_company=active_company,
    )
