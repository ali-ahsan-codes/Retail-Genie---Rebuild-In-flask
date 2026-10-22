# Retail Genie Final — Application Blueprint

Yeh file app ka **architecture map, folder map, Blueprint/route map, database model map aur callable-function index** hai. Isay source code se banaya gaya hai; implementation details mein tabdeeli ho to source files ko final authority samjhein.

## 1. App ka short overview

Retail Genie ek Flask + MySQL retail operations app hai. Is mein user accounts/roles, tenant/company/store separation, product catalog, store-level stock, POS sales, returns/store credit, purchase orders, attendance, stock audits, internal messaging, private files, reports, real-time display, SaaS subscriptions aur database backups shamil hain.

**Request ka main raasta:**

```text
Browser page / JavaScript
    -> Flask application factory (create_app)
    -> request/session/security checks
    -> matched Blueprint route
    -> permission + tenant/store scope checks
    -> service function (business rules)
    -> SQLAlchemy model/session
    -> MySQL transaction
    -> JSON/HTML response; optional Socket.IO event
```

Routes user input aur HTTP response sambhalte hain. Services business rules, tenant scope, database reads/writes aur transaction decisions sambhalte hain. Models MySQL tables ko represent karte hain. Templates HTML render karte hain; static JavaScript API aur Socket.IO ke zariye UI update karta hai.

## 2. Startup aur request lifecycle

1. **`run.py`** `.env` load karke `create_app()` banata hai. Local server `FLASK_HOST`, `FLASK_PORT`, aur `FLASK_DEBUG` use karta hai.
2. **`wsgi.py`** WSGI servers ke liye application object expose karta hai.
3. **`retail_genie/__init__.py:create_app()`** `Config` load karta hai, `SECRET_KEY` aur MySQL `DATABASE_URL` lazmi check karta hai, extensions initialize karta hai, models register karta hai, Blueprints mount karta hai, security headers/error handlers configure karta hai aur CLI commands register karta hai.
4. `before_request` hooks request nonce banate, forced password change enforce karte aur logged-in tenant membership/context verify karte hain.
5. Login session ka user Flask-Login user loader se load hota hai. Non-super-admin ke liye active container membership aur `auth_version` match lazmi hai.
6. Route `@login_required` / permission decorators se actor authorize karti hai. Tenant/store-aware services har object ko active membership aur scope ke andar dobara verify karte hain.
7. SQLAlchemy transaction successful hone par commit hoti hai. Business action ke baad relevant audit/outbox/event records transaction mein persist hote hain.
8. Response par security headers lagte hain; HTML templates / JSON clients ko bheja jata hai.

## 3. Flask Blueprints aur feature map

Blueprint prefixes is app mein aam tor par root (`/`) hain; routes apne full path khud define karte hain. Admin-related prefixes route files mein explicitly set kiye gaye hain.

| Blueprint / code location | URL area / representative routes | Kaam |
|---|---|---|
| `auth` — `auth/routes.py` | `/login`, `/logout`, `/account/tenant`, `/account/password`, `/api/v1/me` | Sign-in/out, tenant selection, password reset/change, current account summary. |
| `main` — `main/routes.py` | `/`, `/dashboard`, `/app-qr.svg` | Main dashboard aur desktop/tablet ke liye current login URL ka QR. |
| `health` — `health/routes.py` | `/healthz`, `/readyz` | Liveness aur MySQL readiness check. |
| `admin` — `admin/routes.py`, prefix `/admin` | `/admin/users` | Users banana, roles/permissions assign karna, active status toggle. |
| `tenancy_admin` — `admin/tenancy_routes.py`, prefix `/admin` | `/admin/companies`, `/admin/companies/<id>/stores`, `/admin/store-assignments`, `/admin/containers/.../policies` | Tenant/company/store setup, billing series, user-store access, data-sharing policies. |
| `admin_backups` — `admin/backup_routes.py`, prefix `/admin/backups` | `/admin/backups/` and `/admin/backups/run` | Backup preferences dekhna/change karna aur manual backup queue karna. |
| `catalog` — `catalog/routes.py` | `/catalog/products`, `/api/v1/products`, `/api/v1/catalog/categories`, `/api/v1/labels/...` | Products/categories, CSV import/export, labels, stock adjustment/transfer, movement history. |
| `sales` — `sales/routes.py` | `/pos`, `/api/v1/orders`, `/returns`, `/cashups` | POS, open bills, orders, payments, returns/exchanges, store credit, removal approvals, daily cash-up. |
| `express` — `express/routes.py` | `/express`, `/api/v1/express/...` | Restricted SKU-based fast checkout. |
| `commercial` — `commercial/routes.py` | `/demand-notices`, `/quotations`, `/api/v1/demand-notices`, `/api/v1/quotations` | Demand notices, quotations, payments/fulfillment/conversion, printable/email documents. |
| `scm` — `scm/routes.py` | `/scm`, `/api/v1/suppliers`, `/api/v1/purchase-orders` | Suppliers, supplier products/files, purchase-order lifecycle, receiving/logistics. |
| `attendance` — `attendance/routes.py` | `/attendance`, `/api/v1/attendance/...`, `/api/v1/breaks` | Clock-in/out, private selfie evidence, break start/end, logs/dashboard. |
| `stock_audits` — `stock_audits/routes.py` | `/audits`, `/api/v1/audits/...` | Physical stock count workflow, count events/evidence, completion/cancel/report. |
| `settings` — `settings/routes.py` | `/settings`, `/api/v1/settings/...` | Company tax, commission, global discount, attendance settings, number-series counters. |
| `reports` — `reports/routes.py` | `/admin/salesperson-reports`, `/admin/activity-logs`, `/api/v1/reports/...` | Sales/activity reports and CSV export. |
| `messaging` — `messaging/routes.py` | `/messaging`, `/messaging/conversations/...`, `/api/v1/messaging/...` | Tenant-member conversations, messages, recipient lookup, attachment download, read status. |
| `cloud` — `cloud/routes.py` | `/my-cloud`, `/admin/file-management`, `/api/v1/cloud/files` | Private file upload/download, notes, delete, controlled share/unshare. |
| `realtime` — `realtime/routes.py`, `handlers.py` | `/api/v1/realtime/stores`, `/api/v1/realtime/events` + Socket.IO | Store-scoped live events and missed-event replay after reconnect. |
| `display` — `display/routes.py` | `/lcd-display`, `/api/v1/display/orders` | Read-only customer-facing order display. |
| `saas` — `saas/routes.py` | `/admin/saas/...`, `/subscription`, `/subscription/invoices/...` | Plans, tenant subscriptions, plan-change requests, invoices/payment records and tenant portal. |

The complete route/decorator inventory generated from source is in **Appendix A** below.

## 4. Core business workflows

### Sign-in, tenant and permissions

`auth/routes.py` verifies submitted credentials and password state. If a user has multiple active memberships, the app asks which tenant container to enter. `auth/tenant_context.py` is the source of the active tenant scope; `auth/permissions.py`, `auth/store_scope.py`, and `auth/tenant_policy.py` apply role, permission, store assignment, and data-sharing checks. A company ID alone is never sufficient proof of tenant access.

### Tenant/company/store provisioning

A Main Admin creates a tenant container and first company/store. The provisioning flow seeds restrictive company-level data policies, billing series and order-number series. Staff accounts are linked through container membership; store-specific staff also receive explicit active store assignments. Tenant admins cannot cross company/container boundaries.

### Product and inventory

`catalog/service.py` validates tenant/company/store scope and product values. Catalog products are company-owned; inventory balances and movements are store-scoped. Adjustments, transfers, purchase-order receiving, sales, returns and stock-audit completion update stock through explicit business operations. Movement rows give an audit trail instead of silently replacing stock history.

### POS sale and return

A route validates the request and asks `sales/service.py` to enforce assigned-store/sales access. The service allocates an order number, validates products/prices, snapshots tax/discounts, writes order/lines/payments, adjusts inventory, records audit/outbox events, and commits atomically. Returns/exchanges allocate return data, restore stock as appropriate, and handle refund/store credit. Cash-up compares expected collections and is reviewed by an authorized manager/admin.

### Purchase orders and commercial documents

SCM services validate supplier, company, product and store scope. Purchase orders move through create/update/confirm/receive/cancel states; receiving updates inventory and audit records together. Demand notices and quotations have their own number series, statuses, printable documents and optional SMTP delivery.

### Realtime updates

Business code stages durable realtime event rows inside the business transaction. `realtime/service.py` dispatches committed events to authorized store rooms; the API replay endpoint supplies a cursor-based recovery path if a browser reconnects after missing a live event. The UI connects using the same-origin Socket.IO client.

### Backups

`backups/service.py` invokes MySQL dump utilities with private temporary credentials/config, writes a compressed dump atomically, and prunes old successful artifacts according to retention settings. `backups/scheduler.py` queues due/manual jobs, recovers abandoned jobs and uses a MySQL advisory lock so only one scheduler owns the work. Start it separately with `flask --app wsgi backup-scheduler` when automatic backups are configured.

### Demo data

`retail_genie/demo_data.py` holds the opt-in local sample tenant/company/store, five products and opening stock. The CLI refuses non-MySQL, non-local hosts, a database other than `retail_genie`, or an existing business dataset. No demo data is inserted merely by starting the web app.

## 5. Access-control and data-safety design

- **Identity:** password hashes; no default app login; `create-admin` prompts interactively for an initial Main Admin password.
- **Tenant isolation:** active `ContainerMembership` determines tenant scope; companies/stores/products are checked against that scope in services.
- **Permissions:** route decorators and service checks validate the actor on each operation. Store access is based on company-admin scope or an active `UserStoreAssignment`.
- **Domain policies:** each tenant has per-domain sharing policy rows (catalog, inventory, sales, files, settings, and related domains). Policies affect whether data can be shared across a tenant's companies.
- **CSRF/session:** Flask-WTF CSRF, HTTP-only session cookies, configurable secure-cookie flag, password-change enforcement, CSP nonce and response security headers.
- **Private files:** uploads/backups are outside the public static tree; download routes re-check authorization.
- **MySQL:** production/app target is MySQL/InnoDB. Never expose port 3306 to client devices/the internet; do not use the database administrator account for a shared/production app.
- **Secrets:** `.env` is local configuration and ignored by Git. Never place secrets in this document or commit `.env`.

## 6. Database model groups

`retail_genie/models/` defines the SQLAlchemy schema. `models/__init__.py` imports the model modules so the metadata contains the app's tables.

| Model file | Main records |
|---|---|
| `user.py` | User identities, roles, permissions, password/auth version. |
| `tenancy.py` | Tenant containers, companies, stores, memberships, store grants, data policies/scopes, audit events. |
| `catalog.py` | Catalog products, inventory balances and immutable-style inventory movements. |
| `billing.py` | Billing/order series, sales orders/lines/payments, return/removal requests, store credits/redemptions, daily cash-ups. |
| `commercial.py` | Commercial number series, demand notices/fulfillments and quotations/lines. |
| `scm.py` | Suppliers, supplier-product links/files, purchase orders/items/files. |
| `settings.py` | Tax, commission, discount, attendance and product-category settings. |
| `attendance.py` | Attendance punches and break logs. |
| `stock_audit.py` | Stock audit headers/items/count events/evidence. |
| `messaging.py` | Conversations, messages, recipients and private attachments. |
| `cloud.py` | Private cloud-file metadata and sharing grants. |
| `realtime.py` | Durable realtime event/outbox rows. |
| `saas.py` | Subscription plans/tenants/invoices/plan changes and platform audit events. |
| `backup.py` | Backup configuration and backup execution history. |

A fuller class inventory follows in Appendix B.

## 7. File-structure map

`retail_genie/<feature>/routes.py` = HTTP/UI/API boundary; `service.py` = business logic; `forms.py` = form validation; `models/` = persistence; `templates/` = server-rendered screens; `static/` = browser-side CSS/JS/vendor assets. The tree below is generated from the checked-in application files. `.env`, local databases, uploads, backups and caches are intentionally excluded.

## 8. Local commands

```powershell
# Create and activate an environment, install requirements, copy .env.example to .env.
# Load database-schema.sql into a new retail_genie database in MySQL Workbench.
flask --app wsgi create-admin --username admin
flask --app wsgi seed-demo --confirm-demo-data  # optional, fresh local DB only
python run.py
```

- `database-schema.sql` is initial schema for a fresh empty database, not a way to upgrade existing business data.
- `/healthz` checks process liveness; `/readyz` checks database readiness.
- `preview/` contains illustrative desktop/mobile screenshots captured with synthetic local demo data. The desktop screenshot shows the QR launcher; mobile clients intentionally omit it. Screenshot data does not represent live-MySQL validation.

## 9. Reading the indexes

- **Appendix A — Routes:** every route decorator found in `retail_genie/**/routes.py`, with HTTP method/path and handler name.
- **Appendix B — Functions/classes:** callable names from every Python source file, grouped by source file. One-line source docstrings are included where present. This is an index, not a replacement for reading the implementation.
- **Appendix C — File tree:** paths as stored in this application copy.

## Appendix A — Complete route inventory

Route paths include any Blueprint prefix. Methods and handlers are extracted from the current route decorators. Function-level auth decorators still apply even if they are not shown in this table.

| Blueprint | Method | Path | Handler | Summary (when documented) |
|---|---|---|---|---|
| `admin` | GET, POST | `/admin/users` | `users()` |  |
| `admin` | POST | `/admin/users/<string:user_id>/toggle-active` | `toggle_user_active()` |  |
| `admin_backups` | GET, POST | `/admin/backups/` | `settings()` |  |
| `admin_backups` | POST | `/admin/backups/run` | `run_now()` |  |
| `attendance` | GET | `/admin/breaks-dashboard` | `breaks_dashboard_page()` |  |
| `attendance` | POST | `/api/v1/attendance/clock-in` | `clock_in_api()` |  |
| `attendance` | POST | `/api/v1/attendance/clock-out` | `clock_out_api()` |  |
| `attendance` | GET | `/api/v1/attendance/logs` | `attendance_logs_api()` |  |
| `attendance` | GET | `/api/v1/attendance/logs/<string:log_id>/selfie` | `attendance_selfie_api()` |  |
| `attendance` | GET | `/api/v1/breaks` | `breaks_api()` |  |
| `attendance` | POST | `/api/v1/breaks` | `start_break_api()` |  |
| `attendance` | POST | `/api/v1/breaks/<string:break_id>/end` | `end_break_api()` |  |
| `attendance` | GET | `/attendance` | `attendance_page()` |  |
| `auth` | GET, POST | `/account/password` | `change_password()` |  |
| `auth` | GET, POST | `/account/tenant` | `select_tenant()` |  |
| `auth` | GET | `/api/v1/me` | `current_account()` |  |
| `auth` | GET, POST | `/login` | `login()` |  |
| `auth` | POST | `/logout` | `logout()` |  |
| `catalog` | GET | `/admin/label-printing` | `label_printing_page()` |  |
| `catalog` | GET | `/admin/product-categories` | `categories_page()` |  |
| `catalog` | GET | `/api/v1/catalog/categories` | `list_categories_api()` |  |
| `catalog` | POST | `/api/v1/catalog/categories` | `create_category_api()` |  |
| `catalog` | DELETE | `/api/v1/catalog/categories/<string:category_id>` | `delete_category_api()` |  |
| `catalog` | PATCH | `/api/v1/catalog/categories/<string:category_id>` | `rename_category_api()` |  |
| `catalog` | GET | `/api/v1/labels/documents` | `label_documents_api()` |  |
| `catalog` | GET | `/api/v1/labels/products` | `label_products_api()` |  |
| `catalog` | GET | `/api/v1/products` | `products_api()` |  |
| `catalog` | POST | `/api/v1/products` | `create_product_api()` |  |
| `catalog` | DELETE | `/api/v1/products/<product_id>` | `archive_product_api()` |  |
| `catalog` | PATCH | `/api/v1/products/<product_id>` | `update_product_api()` |  |
| `catalog` | POST | `/api/v1/products/<product_id>/inventory` | `adjust_inventory_api()` |  |
| `catalog` | GET | `/api/v1/products/<product_id>/inventory-movements` | `inventory_movements_api()` |  |
| `catalog` | POST | `/api/v1/products/<product_id>/transfers` | `transfer_inventory_api()` |  |
| `catalog` | GET, POST | `/catalog/products` | `products_page()` |  |
| `catalog` | POST | `/catalog/products/<product_id>/inventory` | `adjust_inventory_page()` |  |
| `catalog` | POST | `/catalog/products/<product_id>/transfer` | `transfer_inventory_page()` |  |
| `catalog` | GET | `/catalog/products/export.csv` | `export_products_csv()` |  |
| `catalog` | POST | `/catalog/products/import` | `import_products_csv_page()` |  |
| `cloud` | GET | `/admin/file-management` | `file_management_page()` |  |
| `cloud` | GET | `/api/v1/cloud/files` | `list_files_api()` |  |
| `cloud` | POST | `/api/v1/cloud/files` | `upload_file_api()` |  |
| `cloud` | DELETE | `/api/v1/cloud/files/<string:file_id>` | `delete_file_api()` |  |
| `cloud` | GET | `/api/v1/cloud/files/<string:file_id>` | `download_file_api()` |  |
| `cloud` | PATCH | `/api/v1/cloud/files/<string:file_id>/notes` | `update_notes_api()` |  |
| `cloud` | POST | `/api/v1/cloud/files/<string:file_id>/share` | `share_file_api()` |  |
| `cloud` | POST | `/api/v1/cloud/files/<string:file_id>/unshare` | `unshare_file_api()` |  |
| `cloud` | GET | `/my-cloud` | `my_cloud_page()` |  |
| `commercial` | GET | `/api/v1/demand-notices` | `api_list_demand_notices()` |  |
| `commercial` | POST | `/api/v1/demand-notices` | `api_create_demand_notice()` |  |
| `commercial` | PATCH | `/api/v1/demand-notices/<string:notice_id>` | `api_update_demand_notice()` |  |
| `commercial` | POST | `/api/v1/demand-notices/<string:notice_id>/cancel` | `api_cancel_demand_notice()` |  |
| `commercial` | POST | `/api/v1/demand-notices/<string:notice_id>/convert` | `api_convert_demand_notice()` |  |
| `commercial` | POST | `/api/v1/demand-notices/<string:notice_id>/email` | `email_demand_notice()` |  |
| `commercial` | POST | `/api/v1/demand-notices/<string:notice_id>/fulfill` | `api_fulfill_demand_notice()` |  |
| `commercial` | POST | `/api/v1/demand-notices/<string:notice_id>/payments` | `api_record_demand_notice_payment()` |  |
| `commercial` | GET | `/api/v1/quotations` | `api_list_quotations()` |  |
| `commercial` | POST | `/api/v1/quotations` | `api_create_quotation()` |  |
| `commercial` | PATCH | `/api/v1/quotations/<string:quotation_id>` | `api_update_quotation()` |  |
| `commercial` | POST | `/api/v1/quotations/<string:quotation_id>/convert` | `api_convert_quotation()` |  |
| `commercial` | POST | `/api/v1/quotations/<string:quotation_id>/email` | `email_quotation()` |  |
| `commercial` | POST | `/api/v1/quotations/<string:quotation_id>/status` | `api_change_quotation_status()` |  |
| `commercial` | GET | `/commercial/demand-notices/<string:notice_id>/print` | `print_demand_notice()` |  |
| `commercial` | GET | `/commercial/quotations/<string:quotation_id>/print` | `print_quotation()` |  |
| `commercial` | GET | `/demand-notices` | `demand_notices_page()` |  |
| `commercial` | POST | `/demand-notices` | `create_demand_notice_page()` |  |
| `commercial` | GET | `/quotations` | `quotations_page()` |  |
| `commercial` | POST | `/quotations` | `create_quotation_page()` |  |
| `display` | GET | `/api/v1/display/orders` | `display_orders_api()` |  |
| `display` | GET | `/lcd-display` | `lcd_display_page()` |  |
| `express` | POST | `/api/v1/express/checkout` | `express_checkout_api()` |  |
| `express` | GET | `/api/v1/express/products` | `express_products_api()` |  |
| `express` | GET | `/express` | `express_page()` |  |
| `health` | GET | `/healthz` | `liveness()` |  |
| `health` | GET | `/readyz` | `readiness()` |  |
| `main` | GET | `/` | `dashboard()` |  |
| `main` | GET | `/app-qr.svg` | `app_login_qr()` | Render a request-specific SVG QR code for the shared login URL. |
| `main` | GET | `/dashboard` | `dashboard()` |  |
| `messaging` | GET | `/api/v1/messaging/attachments/<string:attachment_id>` | `download_message_attachment_api()` |  |
| `messaging` | GET | `/api/v1/messaging/conversations/<string:conversation_id>/messages` | `conversation_messages_api()` |  |
| `messaging` | POST | `/api/v1/messaging/messages/<string:message_id>/read` | `mark_message_read_api()` |  |
| `messaging` | GET | `/api/v1/messaging/recipients` | `recipient_suggestions_api()` |  |
| `messaging` | GET | `/messaging` | `messaging_page()` |  |
| `messaging` | GET | `/messaging/compose` | `compose_page()` |  |
| `messaging` | GET | `/messaging/conversations` | `conversations_api()` |  |
| `messaging` | POST | `/messaging/conversations` | `create_conversation_api()` |  |
| `messaging` | GET | `/messaging/conversations/<string:conversation_id>` | `conversation_page()` |  |
| `messaging` | POST | `/messaging/conversations/<string:conversation_id>/messages` | `send_message_api()` |  |
| `realtime` | GET | `/api/v1/realtime/events` | `replay_events()` |  |
| `realtime` | GET | `/api/v1/realtime/stores` | `realtime_stores()` |  |
| `reports` | GET | `/admin/activity-logs` | `activity_logs_page()` |  |
| `reports` | GET | `/admin/salesperson-reports` | `salesperson_reports_page()` |  |
| `reports` | GET | `/api/v1/reports/activity` | `activity_api()` |  |
| `reports` | GET | `/api/v1/reports/sales` | `sales_report_api()` |  |
| `reports` | GET | `/api/v1/reports/sales.csv` | `sales_report_csv()` |  |
| `saas` | POST | `/admin/saas/invoices/<string:invoice_id>/record-payment` | `record_invoice_payment()` |  |
| `saas` | GET, POST | `/admin/saas/plans` | `plans()` |  |
| `saas` | POST | `/admin/saas/plans/<string:plan_id>/toggle` | `toggle_plan()` |  |
| `saas` | GET | `/admin/saas/requests` | `plan_requests()` |  |
| `saas` | POST | `/admin/saas/requests/<string:request_id>` | `review_request()` |  |
| `saas` | GET | `/admin/saas/subscriptions` | `subscriptions()` |  |
| `saas` | POST | `/admin/saas/subscriptions/<string:tenant_container_id>` | `save_subscription()` |  |
| `saas` | POST | `/admin/saas/subscriptions/<string:tenant_container_id>/invoices` | `issue_invoice()` |  |
| `saas` | GET, POST | `/subscription` | `tenant_portal()` |  |
| `saas` | GET | `/subscription/invoices/<string:invoice_id>/print` | `print_invoice()` |  |
| `sales` | GET | `/admin/orders` | `admin_orders_page()` |  |
| `sales` | GET | `/api/v1/cashups` | `list_daily_cashups()` |  |
| `sales` | POST | `/api/v1/cashups` | `create_daily_cashup()` |  |
| `sales` | POST | `/api/v1/cashups/<string:cashup_id>/review` | `review_daily_cashup()` |  |
| `sales` | GET | `/api/v1/order-removal-requests` | `list_order_removal_requests()` |  |
| `sales` | POST | `/api/v1/order-removal-requests/<string:request_id>/review` | `review_sales_order_item_removal()` |  |
| `sales` | GET | `/api/v1/orders` | `list_sales_orders_api()` |  |
| `sales` | POST | `/api/v1/orders` | `create_sales_order()` |  |
| `sales` | GET | `/api/v1/orders/<string:order_id>` | `get_sales_order()` |  |
| `sales` | PATCH | `/api/v1/orders/<string:order_id>/fulfillment` | `update_order_fulfillment_api()` |  |
| `sales` | POST | `/api/v1/orders/<string:order_id>/items` | `append_sales_order_item()` |  |
| `sales` | POST | `/api/v1/orders/<string:order_id>/items/<string:line_id>/removal-requests` | `request_sales_order_item_removal()` |  |
| `sales` | POST | `/api/v1/orders/<string:order_id>/payments` | `create_order_payment()` |  |
| `sales` | POST | `/api/v1/orders/<string:order_id>/returns` | `create_order_return()` |  |
| `sales` | POST | `/api/v1/orders/<string:order_id>/store-credits/<string:credit_id>/redeem` | `redeem_store_credit_api()` |  |
| `sales` | GET | `/api/v1/orders/open` | `open_orders()` |  |
| `sales` | GET | `/api/v1/store-credits` | `list_store_credits_api()` |  |
| `sales` | GET | `/cashups` | `daily_cashup_page()` |  |
| `sales` | GET | `/pos` | `point_of_sale()` |  |
| `sales` | GET | `/removals` | `removal_approvals_page()` |  |
| `sales` | GET | `/returns` | `returns_page()` |  |
| `sales` | POST | `/returns/<string:order_id>` | `submit_order_return_page()` |  |
| `sales` | GET | `/sales/orders/<string:order_id>/print` | `print_sales_order()` |  |
| `sales` | GET | `/sales/returns/<string:return_id>/print` | `print_return_slip()` |  |
| `scm` | POST | `/api/v1/purchase-orders` | `create_purchase_order_api()` |  |
| `scm` | GET | `/api/v1/purchase-orders/<string:po_id>` | `get_purchase_order_api()` |  |
| `scm` | PATCH | `/api/v1/purchase-orders/<string:po_id>` | `update_purchase_order_api()` |  |
| `scm` | POST | `/api/v1/purchase-orders/<string:po_id>/attachments` | `add_po_attachment_api()` |  |
| `scm` | GET | `/api/v1/purchase-orders/<string:po_id>/attachments/<string:attachment_id>` | `download_po_attachment_api()` |  |
| `scm` | POST | `/api/v1/purchase-orders/<string:po_id>/cancel` | `cancel_purchase_order_api()` |  |
| `scm` | POST | `/api/v1/purchase-orders/<string:po_id>/confirm` | `confirm_purchase_order_api()` |  |
| `scm` | PATCH | `/api/v1/purchase-orders/<string:po_id>/logistics` | `update_po_logistics_api()` |  |
| `scm` | POST | `/api/v1/purchase-orders/<string:po_id>/receive` | `receive_purchase_order_api()` |  |
| `scm` | POST | `/api/v1/suppliers` | `create_supplier_api()` |  |
| `scm` | PATCH | `/api/v1/suppliers/<string:supplier_id>` | `update_supplier_api()` |  |
| `scm` | GET | `/api/v1/suppliers/<string:supplier_id>/attachments` | `list_supplier_attachments_api()` |  |
| `scm` | POST | `/api/v1/suppliers/<string:supplier_id>/attachments` | `add_supplier_attachment_api()` |  |
| `scm` | GET | `/api/v1/suppliers/<string:supplier_id>/attachments/<string:attachment_id>` | `download_supplier_attachment_api()` |  |
| `scm` | GET | `/api/v1/suppliers/<string:supplier_id>/products` | `list_supplier_products_api()` |  |
| `scm` | POST | `/api/v1/suppliers/<string:supplier_id>/products` | `link_supplier_product_api()` |  |
| `scm` | POST | `/api/v1/suppliers/<string:supplier_id>/status` | `set_supplier_status_api()` |  |
| `scm` | DELETE | `/api/v1/suppliers/products/<string:link_id>` | `remove_supplier_product_api()` |  |
| `scm` | GET | `/scm` | `scm_dashboard()` |  |
| `scm` | GET | `/scm/purchase-orders` | `purchase_orders_page()` |  |
| `scm` | GET | `/scm/purchase-orders/<string:po_id>` | `purchase_order_page()` |  |
| `scm` | GET | `/scm/suppliers` | `suppliers_page()` |  |
| `scm` | GET | `/scm/suppliers/<string:supplier_id>` | `supplier_detail_page()` |  |
| `settings` | POST | `/api/v1/settings/attendance` | `update_attendance()` |  |
| `settings` | POST | `/api/v1/settings/commission` | `update_commission()` |  |
| `settings` | POST | `/api/v1/settings/global-discount` | `update_global_discount()` |  |
| `settings` | POST | `/api/v1/settings/series/<string:series_id>/next-number` | `update_series_next_number()` | Move a document counter forward; every change is audited. |
| `settings` | GET | `/api/v1/settings/summary` | `settings_summary_api()` |  |
| `settings` | POST | `/api/v1/settings/tax` | `update_tax()` |  |
| `settings` | GET | `/settings` | `settings_index()` |  |
| `stock_audits` | POST | `/api/v1/audits` | `create_audit_api()` |  |
| `stock_audits` | POST | `/api/v1/audits/<string:audit_id>/cancel` | `cancel_audit_api()` |  |
| `stock_audits` | POST | `/api/v1/audits/<string:audit_id>/complete` | `complete_audit_api()` |  |
| `stock_audits` | GET | `/api/v1/audits/<string:audit_id>/counts/<string:item_id>` | `audit_counts_api()` |  |
| `stock_audits` | GET | `/api/v1/audits/<string:audit_id>/evidence/<string:count_event_id>` | `audit_evidence_api()` |  |
| `stock_audits` | POST | `/api/v1/audits/<string:audit_id>/items/<string:item_id>/counts` | `record_count_api()` |  |
| `stock_audits` | POST | `/api/v1/audits/<string:audit_id>/items/<string:item_id>/counts/<string:count_event_id>/evidence` | `add_evidence_api()` |  |
| `stock_audits` | POST | `/api/v1/audits/<string:audit_id>/start` | `start_audit_api()` |  |
| `stock_audits` | GET | `/audits` | `audits_page()` |  |
| `stock_audits` | GET | `/audits/<string:audit_id>` | `audit_detail_page()` |  |
| `stock_audits` | GET | `/audits/<string:audit_id>/report` | `audit_report_page()` |  |
| `stock_audits` | GET | `/audits/create` | `create_audit_page()` |  |
| `tenancy_admin` | GET, POST | `/admin/companies` | `companies()` |  |
| `tenancy_admin` | GET, POST | `/admin/companies/<string:company_id>/billing` | `billing_settings()` |  |
| `tenancy_admin` | GET, POST | `/admin/companies/<string:company_id>/stores` | `stores()` |  |
| `tenancy_admin` | POST | `/admin/companies/<string:company_id>/toggle-active` | `toggle_company()` |  |
| `tenancy_admin` | GET, POST | `/admin/containers/<string:tenant_container_id>/companies/<string:parent_company_id>/new` | `create_child_company()` | Create a nested operating company without creating a new tenant boundary. |
| `tenancy_admin` | GET | `/admin/containers/<string:tenant_container_id>/policies` | `domain_policies()` |  |
| `tenancy_admin` | GET, POST | `/admin/containers/<string:tenant_container_id>/policies/<string:domain>` | `edit_domain_policy()` |  |
| `tenancy_admin` | GET | `/admin/domain-policies` | `domain_policy_index()` |  |
| `tenancy_admin` | GET, POST | `/admin/store-assignments` | `store_assignments()` |  |
| `tenancy_admin` | POST | `/admin/store-assignments/<string:assignment_id>/revoke` | `revoke_store_assignment()` |  |

## Appendix B — Complete function and class index

Index generated from the application Python source: **600 function/method definitions and 91 classes**. Private helpers are included. Nested hooks/callbacks are shown under their containing function. A documented first line is included where available.

### `retail_genie/__init__.py`

- `create_app()`
    - `create_app > inject_template_context()`
    - `create_app > load_user()`
    - `create_app > handle_unauthorized()`
    - `create_app > _ensure_realtime_dispatcher_started()`
    - `create_app > require_tenant_context_and_password_change()`
    - `create_app > add_security_headers()`
    - `create_app > forbidden()`
    - `create_app > not_found()`
    - `create_app > internal_error()`
- `register_cli_commands()` — Register first-admin provisioning and the MySQL backup worker.
    - `register_cli_commands > create_admin()` — Create the initial Main Admin after loading the provided MySQL schema.
    - `register_cli_commands > seed_demo()` — Add opt-in demo records to a fresh local Retail Genie database.
    - `register_cli_commands > backup_scheduler()` — Run the separate MySQL backup scheduler/worker process.

### `retail_genie/admin/backup_forms.py`

- **class `BackupSettingsForm`**

### `retail_genie/admin/backup_routes.py`

- `_render_settings()`
- `format_utc()`
- `settings()`
- `run_now()`

### `retail_genie/admin/forms.py`

- **class `CreateUserForm`**
    - `CreateUserForm > validate_username()`

### `retail_genie/admin/routes.py`

- `_assignable_roles()`
- `_assignable_permissions()`
- `_visible_users()`
- `_target_membership()`
- `_can_manage_target()`
- `_render_accounts()`
- `users()`
- `toggle_user_active()`

### `retail_genie/admin/tenancy_forms.py`

- **class `CreateCompanyForm`**
    - `CreateCompanyForm > validate_timezone()`
- **class `StoreForm`**
- **class `AssignmentForm`**
- **class `DomainPolicyForm`**
- **class `BillingSettingsForm`**

### `retail_genie/admin/tenancy_routes.py`

- `_company_or_404()`
- `_audit()`
- `companies()`
- `create_child_company()` — Create a nested operating company without creating a new tenant boundary.
- `toggle_company()`
- `stores()`
- `billing_settings()`
- `_domain_label()`
- `_scope_snapshot()`
- `domain_policy_index()`
- `domain_policies()`
- `edit_domain_policy()`
- `store_assignments()`
- `revoke_store_assignment()`

### `retail_genie/attendance/routes.py`

- `_payload()`
- `_error()`
- `_company_id()`
- `attendance_page()`
- `clock_in_api()`
- `attendance_selfie_api()`
- `clock_out_api()`
- `attendance_logs_api()`
- `start_break_api()`
- `end_break_api()`
- `breaks_api()`
- `breaks_dashboard_page()`

### `retail_genie/attendance/service.py`

- **class `AttendanceRuleError`**
    - `AttendanceRuleError > __init__()`
- `_tenant_for_actor()`
- `_company_for_actor()`
- `_audit_attendance()`
- `_business_date()`
- `_store_selfie()` — Persist a data-URI selfie under the private uploads directory.
- `clock_in()` — Record one punch-in per user per company business day.
- `clock_out()`
- `list_attendance_logs()`
- `active_break()`
- `_attendance_setting()`
- `start_break()`
- `end_break()`
- `list_breaks()`
- `breaks_dashboard()` — Active breaks and today's attendance for managers and admins.
- `get_attendance_selfie()`
- `attendance_dict()`
- `break_dict()`
- `new_id()`

### `retail_genie/auth/forms.py`

- **class `LoginForm`**
- **class `SelectTenantForm`**
- **class `PasswordChangeForm`**

### `retail_genie/auth/permissions.py`

- `permission_required()` — Require an authenticated account and a permission checked from MySQL.
    - `permission_required > decorator()`
      - `permission_required > decorator > wrapped()`
- `admin_required()` — Require a tenant or platform administrator.
    - `admin_required > wrapped()`
- `super_admin_required()` — Require the global Main Admin; tenant admins cannot cross companies.
    - `super_admin_required > wrapped()`
- `company_admin_required()` — Require a company admin or the global Main Admin.
    - `company_admin_required > wrapped()`

### `retail_genie/auth/routes.py`

- `login()`
- `select_tenant()`
- `request_method_is_post()` — Small helper to keep GET defaults separate from WTForms validation.
- `logout()`
- `change_password()`
- `current_account()`

### `retail_genie/auth/store_scope.py`

- `accessible_store_ids()` — Return active stores in one authorized container and optional company.
- `can_access_store()` — Require tenant membership plus company-admin scope or an active assignment.
- `can_view_shared_bill()` — Shared-bill access requires a domain policy and an explicit store grant.
- `company_for_user()`

### `retail_genie/auth/tenant_context.py`

- `available_memberships()` — Return only active memberships in active containers/companies.
- `current_membership()` — Resolve the active membership; never infer tenant scope from company_id.
- `current_tenant_container_id()` — Return the one active container selected for this request/account.
- `has_tenant_membership()` — Check one requested tenant without granting access to sibling containers.
- `select_container_for_session()` — Set an active container only when an active membership proves access.

### `retail_genie/auth/tenant_policy.py`

- `_actor_permissions()`
- `can_access_data_domain()` — Authorize view/add/edit/delete against membership, role, and policy.  ``company_id`` and ``store_id`` identify the record's owning unit, not the acting user's preferred scope. A missing policy denies access by default. Explicit denials in selected-unit mode override grants.

### `retail_genie/backups/scheduler.py`

- `get_or_create_settings()`
- `normalize_utc()`
- `queue_manual_backup()` — Queue at most one outstanding backup and return (run, newly_queued).
- `recover_abandoned_runs()` — Mark interrupted worker runs failed after the configured dump timeout.
- `queue_due_backup()` — Return the next queued run, creating one if the schedule is due.
- `execute_backup_run()` — Run a queued backup and persist a success or failure audit record.
- `_scheduler_lock_name()`
- `_acquire_scheduler_lock()`
- `run_backup_scheduler()` — Run the scheduled worker, protected by a MySQL advisory lock.  The worker is a separate process by design; starting it from Flask web workers would cause duplicate schedulers under common WSGI deployments.

### `retail_genie/backups/service.py`

- **class `BackupError`** — A backup could not be produced safely.
- **class `BackupArtifact`**
- `_backup_directory()`
- `_option_value()`
- `_socket_path()`
- `_database_identity()`
- `_mysql_connection_options()`
- `_write_mysql_defaults_file()`
- `_mysqldump_executable()`
- `create_mysql_backup()` — Dump the configured MySQL database to an atomic, private gzip file.
- `prune_retained_backups()` — Remove older successful dump files, retaining their audit rows.

### `retail_genie/catalog/forms.py`

- **class `ProductForm`**
- **class `InventoryAdjustmentForm`**

### `retail_genie/catalog/routes.py`

- `_payload()`
- `_error_response()`
- `_inventory_error_response()`
- `_row_dict()`
- `_read_csv_upload()`
- `_spreadsheet_safe_text()`
- `_perform_transfer()`
- `_category_company()`
- `_category_access()`
- `_category_rows()`
- `categories_page()`
- `list_categories_api()`
- `create_category_api()`
- `rename_category_api()`
- `delete_category_api()`
- `_label_company()`
- `label_printing_page()`
- `label_products_api()`
- `label_documents_api()`
- `export_products_csv()`
- `import_products_csv_page()`
- `transfer_inventory_page()`
- `transfer_inventory_api()`
- `products_page()`
- `adjust_inventory_page()`
- `products_api()`
- `create_product_api()`
- `update_product_api()`
- `archive_product_api()`
- `adjust_inventory_api()`
- `inventory_movements_api()`

### `retail_genie/catalog/service.py`

- **class `CatalogRuleError`**
    - `CatalogRuleError > __init__()`
- `_tenant_for_actor()`
- `_company_in_tenant()`
- `_store_in_tenant()`
- `_product_in_tenant()`
- `_catalog_store_for_actor()`
- `_require_domain()`
- `accessible_stores()`
- `list_products()`
- `_money()`
- `_expiry_datetime()`
- `_as_boolean()`
- `_stock_threshold()`
- `_product_snapshot()`
- `create_product()`
- `update_product()`
- `archive_product()`
- `adjust_inventory()`
- `product_dict()`
- `transfer_inventory()` — Move stock atomically between two stores of the same legal company.
- `parse_product_csv()`
- `import_products_csv()` — Atomically import catalog rows and optional target stock quantities.  Existing active products are matched only by company-scoped SKU. CSV product IDs are ignored so a file cannot select or overwrite another tenant's row. The caller owns the transaction and must roll back on any raised error.

### `retail_genie/cloud/routes.py`

- `_payload()`
- `_error()`
- `my_cloud_page()`
- `file_management_page()`
- `list_files_api()`
- `upload_file_api()`
- `download_file_api()`
- `update_notes_api()`
- `delete_file_api()`
- `share_file_api()`
- `unshare_file_api()`

### `retail_genie/cloud/service.py`

- **class `CloudRuleError`**
    - `CloudRuleError > __init__()`
- `_tenant()`
- `_owner_company()`
- `_can_files()`
- `_file_row()`
- `_may_read()`
- `file_dict()`
- `list_files()`
- `upload_file()`
- `authorized_file_path()`
- `update_file_notes()`
- `delete_file()`
- `share_file()`
- `unshare_file()`

### `retail_genie/commercial/emailing.py`

- **class `CommercialEmailError`** — An expected mail-delivery or configuration failure.
- `send_commercial_email()` — Send a commercial document summary using explicitly configured SMTP.  The document is delivered as HTML email content, avoiding a dependency on a PDF renderer while remaining printable or savable as PDF from the recipient's mail client. No message is silently accepted when SMTP is not configured.

### `retail_genie/commercial/routes.py`

- `_payload()`
- `_error()`
- `_page_context()`
- `demand_notices_page()`
- `create_demand_notice_page()`
- `quotations_page()`
- `create_quotation_page()`
- `api_list_demand_notices()`
- `api_create_demand_notice()`
- `api_cancel_demand_notice()`
- `api_fulfill_demand_notice()`
- `api_convert_demand_notice()`
- `api_list_quotations()`
- `api_create_quotation()`
- `api_change_quotation_status()`
- `api_convert_quotation()`
- `api_update_demand_notice()`
- `api_record_demand_notice_payment()`
- `api_update_quotation()`
- `print_demand_notice()`
- `print_quotation()`
- `_email_document()`
- `email_demand_notice()`
- `email_quotation()`

### `retail_genie/commercial/service.py`

- `_document_number()` — Lock the company row before allocating/creating its per-type counter.
- `_valid_date()`
- `_optional_text()`
- `_parse_bool()`
- `_authorized_company_store()`
- `_product_for_document()`
- `demand_notice_dict()`
- `quotation_dict()`
- `create_demand_notice()`
- `list_demand_notices()`
- `cancel_demand_notice()`
- `create_quotation()`
- `_quotation_for_actor()`
- `list_quotations()`
- `change_quotation_status()`
- `convert_quotation_to_order()`
- `fulfill_demand_notice()`
- `convert_demand_notice_to_order()`
- `_demand_notice_for_actor()`
- `record_demand_notice_payment()` — Record a serialized, replay-safe deposit against an open demand notice.
- `update_demand_notice()`
- `update_quotation()`
- `get_demand_notice_document()`
- `get_quotation_document()`

### `retail_genie/config.py`

- `_env_bool()`
- **class `Config`**

### `retail_genie/demo_data.py`

- `seed_demo_records()` — Create one demo tenant, store, products and opening stock exactly once.  Returns ``False`` without writes if this seed container already exists. The caller must restrict use to a fresh local database and require explicit confirmation before invoking this function.

### `retail_genie/device.py`

- `is_mobile_phone()` — Identify phones, while leaving tablet and desktop user agents eligible.

### `retail_genie/display/routes.py`

- `_display_orders()`
- `lcd_display_page()`
- `display_orders_api()`

### `retail_genie/express/routes.py`

- `_payload()`
- `_require_express()`
- `express_page()`
- `express_products_api()`
- `express_checkout_api()`

### `retail_genie/extensions.py`

- **class `Base`**

### `retail_genie/health/routes.py`

- `liveness()`
- `readiness()`

### `retail_genie/main/routes.py`

- `app_login_qr()` — Render a request-specific SVG QR code for the shared login URL.
- `_dashboard_cards()`
    - `_dashboard_cards > add()`
- `dashboard()`

### `retail_genie/messaging/routes.py`

- `_payload()`
- `_error()`
- `messaging_page()`
- `compose_page()`
- `conversations_api()`
- `create_conversation_api()`
- `conversation_page()`
- `conversation_messages_api()`
- `send_message_api()`
- `download_message_attachment_api()`
- `mark_message_read_api()`
- `recipient_suggestions_api()`

### `retail_genie/messaging/service.py`

- `_audit()`
- **class `MessagingRuleError`**
    - `MessagingRuleError > __init__()`
- `_tenant_for_actor()`
- `_container_members()`
- `conversation_dict()`
- `message_dict()`
- `list_conversations()`
- `create_conversation()`
- `_conversation_for_actor()`
- `send_message()`
- `list_messages()`
- `authorized_attachment_path()`
- `mark_read()`
- `_store_message_attachment()`
- `recipient_suggestions()`

### `retail_genie/models/attendance.py`

- `utc_now()`
- **class `AttendanceLog`** — One clock-in event per staff member per business day.
- **class `BreakLog`** — A staff break window; at most the configured concurrent count per user.

### `retail_genie/models/backup.py`

- **class `BackupSettings`**
    - `BackupSettings > __repr__()`
- **class `BackupRun`**
    - `BackupRun > __repr__()`

### `retail_genie/models/billing.py`

- `utc_now()`
- **class `BillingSeries`**
- **class `OrderNumberSeries`** — Company-level monotonic series for a bill reference allocated at creation.
- **class `SalesOrder`**
- **class `SalesOrderLine`**
- **class `OrderPayment`**
- **class `OrderRemovalRequest`**
- **class `OrderReturn`** — Append-only return transaction for one or more lines on a settled order.
- **class `StoreCredit`** — Credit issued to a customer and redeemable against later bills.
- **class `OrderReturnLine`**
- **class `StoreCreditRedemption`** — Auditable tender redemption for a credit against a later sale.
- **class `DailyCashup`**
    - `DailyCashup > variances()`

### `retail_genie/models/catalog.py`

- `utc_now()`
- **class `CatalogProduct`** — A canonical company-owned product; stock remains store-specific.
- **class `InventoryBalance`** — Current on-hand quantity for a canonical product at one store.
- **class `InventoryMovement`** — Append-only stock movement entry used for audit and reconciliation.

### `retail_genie/models/cloud.py`

- `utc_now()`
- **class `CloudFile`** — An uploaded file owned by one account inside one container.
- **class `CloudFileShare`** — An explicit per-user grant on a shared file.

### `retail_genie/models/commercial.py`

- `utc_now()`
- **class `BusinessNumberSeries`** — Company-level counters used for human-readable commercial documents.
- **class `DemandNotice`** — A store-scoped customer request, optionally tied to a known product.
- **class `Quotation`** — Price proposal with immutable product/price snapshots on each line.
- **class `QuotationLine`**
- **class `DemandNoticeFulfillment`** — Idempotent order/quantity fulfillment history for demand notices.

### `retail_genie/models/messaging.py`

- `utc_now()`
- **class `Conversation`** — A message thread inside one tenant container.
- **class `Message`** — One message inside a conversation.
- **class `MessageRecipient`** — Delivery and read state for one message recipient.
- **class `MessageAttachment`** — A private file attached to one message.

### `retail_genie/models/realtime.py`

- `utc_now()`
- **class `RealtimeEvent`** — Committed business event; clients replay by cursor after reconnecting.

### `retail_genie/models/saas.py`

- `_utc_now()`
- **class `SubscriptionPlan`** — A platform price tier; prices are OMR and usage caps are nullable/unlimited.
- **class `TenantSubscription`** — One current platform-managed subscription per independent tenant.
- **class `SubscriptionInvoice`** — Manual OMR subscription invoice; no payment gateway is assumed.
- **class `PlatformAuditEvent`** — Audit log for global plan-catalog and SaaS billing administration.
- **class `PlanChangeRequest`** — A tenant admin request; platform staff explicitly reviews and applies it.

### `retail_genie/models/scm.py`

- `utc_now()`
- **class `Supplier`** — A company-scoped vendor supplying products.
- **class `SupplierProduct`** — A supplier's offered price for one company-owned catalog product.
- **class `SupplierAttachment`** — A private file attached to one supplier record.
- **class `PurchaseOrder`** — A company-scoped purchase order with receiving and logistics status.
- **class `PurchaseOrderItem`** — One ordered product line on a purchase order.
- **class `PurchaseOrderAttachment`** — A private file attached to one purchase order.

### `retail_genie/models/settings.py`

- `utc_now()`
- **class `TaxSetting`** — A named tax rate a company can apply to sales documents.
- **class `CommissionSetting`** — Sales-target commission configuration; one active row per company.
- **class `GlobalDiscountSetting`** — A dated company-wide discount applied automatically at order creation.
- **class `AttendanceSetting`** — Punch-in enforcement and concurrent-break limits for one company.
- **class `ProductCategory`** — An administered category name inside one company's catalog.

### `retail_genie/models/stock_audit.py`

- `utc_now()`
- **class `StockAudit`** — A store-scoped counting exercise assigned to one auditor.
- **class `StockAuditItem`** — One product line under audit with its expected and final counts.
- **class `StockAuditItemCount`** — An append-only count event recorded while an audit is in progress.
- **class `StockAuditImage`** — Evidence captured against one count event.

### `retail_genie/models/tenancy.py`

- `utc_now()`
- **class `TenantContainer`** — Logical SaaS isolation boundary; all customers share the same MySQL DB.
- **class `Company`** — An operating/legal company node inside a tenant container.
- **class `Store`** — A branch/store belonging to one company inside one tenant container.
- **class `ContainerMembership`** — A user identity's role and permission set in a particular tenant.
- **class `TenantDataPolicy`** — Container-level sharing mode for one data domain; roles stay independent.
- **class `TenantDataPolicyScope`** — Explicit allow/deny scopes used when a domain is set to selected_units.
- **class `UserStoreAssignment`** — Revocable store access tied to a tenant membership.
- **class `AuditEvent`** — Append-only-by-application audit event, always scoped to one container.

### `retail_genie/models/user.py`

- `normalize_username()`
- `is_valid_username()`
- `utc_now()`
- **class `User`**
    - `User > __init__()`
    - `User > effective_membership()` — Return the active tenant membership rather than treating company_id as tenancy.
    - `User > effective_role()`
    - `User > is_admin()` — Compatibility predicate for tenant and platform administrators.
    - `User > is_super_admin()`
    - `User > is_company_admin()`
    - `User > set_password()`
    - `User > check_password()`
    - `User > has_permission()`
    - `User > to_public_dict()` — Serialize only safe account fields; password hashes are never exposed.
    - `User > __repr__()`

### `retail_genie/realtime/handlers.py`

- `connect_retail()`
- `subscribe_store()`
- `unsubscribe_store()`
- `disconnect_retail()`

### `retail_genie/realtime/routes.py`

- `_private_json()`
- `realtime_stores()`
- `replay_events()`

### `retail_genie/realtime/service.py`

- `initialize_realtime_registry()` — Create a process-local connection/subscription registry for the single-host MVP.
- `register_connection()`
- `connection_is_active()`
- `_registry()`
- `add_subscription()`
- `remove_subscription()`
- `clear_user_subscriptions()` — Revoke a user's process-local sockets on logout or tenant switch.
- `_policy_allows()`
- `_has_domain_view()`
- `can_user_receive_realtime_event()` — Reauthorize a socket against current membership, role, store and domain policy.
- `can_user_receive_inventory_event()` — Backward-compatible alias used by older callers and tests.
- `event_message()`
- `stage_access_revocation()` — Write an access-change outbox row in the same transaction as ACL edits.
- `stage_container_access_revocations()` — Stage per-user invalidations after a tenant-wide policy change.
- `stage_company_access_revocations()`
- `stage_user_access_revocations()`
- `_claim_event()`
- `_finish_event()`
- `_matching_subscribers()`
- `_revoke_subscriber()`
- `publish_realtime_event()` — Deliver a committed event to local sockets; other workers poll the same outbox.
- `realtime_dispatch_once()` — Poll and deliver a batch of committed outbox rows (also used by tests).
- `prune_realtime_events()` — Delete expired feed rows but keep one cursor anchor for every event scope.
- `start_realtime_dispatcher()` — Start one database-polling publisher per web process for multi-worker fan-out.
- `_realtime_dispatch_loop()`

### `retail_genie/reports/routes.py`

- `_scope_context()`
- `_date_arg()`
- `_error()`
- `salesperson_reports_page()`
- `activity_logs_page()`
- `sales_report_api()`
- `sales_report_csv()`
- `activity_api()`

### `retail_genie/reports/service.py`

- **class `ReportRuleError`**
    - `ReportRuleError > __init__()`
- `_scope()`
- `sales_report()`
- `activity_log()`
- `report_csv()`
    - `report_csv > safe_cell()`

### `retail_genie/saas/forms.py`

- **class `SubscriptionPlanForm`**
    - `SubscriptionPlanForm > validate_monthly_price()`
- **class `TenantSubscriptionForm`**
- **class `PlanChangeRequestForm`**
- **class `ReviewPlanRequestForm`**

### `retail_genie/saas/routes.py`

- `enforce_suspended_subscription_read_only()` — Allow suspended tenants to inspect/request service but block writes.
- `_platform_audit()`
- `plans()`
- `toggle_plan()`
- `subscriptions()`
- `save_subscription()`
- `tenant_portal()`
- `plan_requests()`
- `review_request()`
- `issue_invoice()`
- `record_invoice_payment()`
- `print_invoice()`

### `retail_genie/saas/service.py`

- **class `SaaSRuleError`** — A plan, quota, or subscription operation violates platform policy.
- **class `TenantUsage`**
- `tenant_usage()` — Count active tenant resources without crossing container boundaries.
- `tenant_subscription()`
- `_limit_for()`
- `ensure_capacity()` — Lock the tenant row and enforce a currently assigned plan's quota.  No subscription means a grandfathered, unmetered tenant. This avoids silently imposing commercial terms on existing customers during rollout.
- `plan_fits_usage()` — Return whether the current tenant fits all non-null plan limits.
- `_audit_subscription_change()`
- `_platform_audit()`
- `create_subscription_invoice()`
- `mark_subscription_invoice_paid()`
- `create_plan_change_request()`
- `review_plan_change_request()`
- `assign_subscription()`

### `retail_genie/sales/routes.py`

- `_payload()`
- `_error_response()`
- `_parse_business_date()`
- `_cashup_dict()`
- `point_of_sale()`
- `open_orders()`
- `create_sales_order()`
- `get_sales_order()`
- `update_order_fulfillment_api()`
- `list_sales_orders_api()`
- `admin_orders_page()`
- `print_sales_order()`
- `print_return_slip()`
- `append_sales_order_item()`
- `request_sales_order_item_removal()`
- `review_sales_order_item_removal()`
- `create_order_payment()`
- `list_store_credits_api()`
- `redeem_store_credit_api()`
- `create_order_return()`
- `create_daily_cashup()`
- `list_daily_cashups()`
- `review_daily_cashup()`
- `sales_forbidden()`
- `sales_not_found()`
- `_removal_dict()`
- `returns_page()`
- `submit_order_return_page()`
- `removal_approvals_page()`
- `list_order_removal_requests()`
- `daily_cashup_page()`

### `retail_genie/sales/service.py`

- **class `SalesRuleError`**
    - `SalesRuleError > __init__()`
- `as_money()`
- `normalize_phone()`
- `_as_integer()`
- `_require_sales_pos()`
- `_require_sales_domain()`
- `_allocate_order_number()`
- `_validated_catalog_line()`
- `_change_sale_inventory()`
- `_publish_inventory_events()`
- `_active_company()`
- `_company_for_actor()`
- `company_today()`
- `_local_day_bounds_utc()`
- `_store_for_company()`
- `_require_assigned_store()`
- `_order_for_actor()`
- `_paid_amount()`
- `order_dict()`
- `_sales_realtime_event()` — Stage a minimal, store-scoped sales event in the same business transaction.
- `_add_audit()`
- `_add_order_line()`
- `_recalculate_order()` — Recompute subtotal, discounts, taxes, and the bill total.
- `_effective_global_discount()` — Snapshot the dated company-wide discount percentage for a bill.
- `_issue_invoice()`
- `create_order()`
- `express_checkout()` — Atomic SKU checkout: catalog prices, inventory, tender, invoice, audit.
- `find_open_orders()`
- `find_returnable_orders()`
- `add_order_item()`
- `request_item_removal()`
- `_can_approve()`
- `review_removal_request()`
- `record_payment()`
- `find_store_credits()`
- `redeem_store_credit()`
- `_allocate_credit_number()`
- `_issue_store_credit()`
- `_build_exchange_order()`
- `process_order_return()` — Return sold quantities, restore stock, and refund, exchange, or credit.
- `_expected_collections()`
- `submit_cashup()`
- `review_cashup()`
- `list_sales_orders()`
- `update_order_fulfillment()`

### `retail_genie/scm/routes.py`

- `_payload()`
- `_error()`
- `_resolve_company()`
- `_scm_context()`
- `scm_dashboard()`
- `create_supplier_api()`
- `update_supplier_api()`
- `set_supplier_status_api()`
- `link_supplier_product_api()`
- `remove_supplier_product_api()`
- `add_supplier_attachment_api()`
- `list_supplier_attachments_api()`
- `download_supplier_attachment_api()`
- `list_supplier_products_api()`
- `create_purchase_order_api()`
- `update_purchase_order_api()`
- `confirm_purchase_order_api()`
- `cancel_purchase_order_api()`
- `receive_purchase_order_api()`
- `update_po_logistics_api()`
- `add_po_attachment_api()`
- `download_po_attachment_api()`
- `get_purchase_order_api()`
- `suppliers_page()`
- `supplier_detail_page()`
- `purchase_orders_page()`
- `purchase_order_page()`

### `retail_genie/scm/service.py`

- **class `ScmRuleError`**
    - `ScmRuleError > __init__()`
- `_tenant_for_actor()`
- `_company_in_tenant()`
- `_store_in_tenant()`
- `_product_in_tenant()`
- `_require_supplier_access()`
- `_require_po_access()`
- `_money()`
- `_quantity()`
- `_optional_text()`
- `_valid_date()`
- `_po_number()`
- `supplier_dict()`
- `list_suppliers()`
- `_default_company()`
- `create_supplier()`
- `_supplier_in_tenant()`
- `update_supplier()`
- `set_supplier_status()`
- `add_supplier_attachment()`
- `list_supplier_attachments()`
- `link_supplier_product()`
- `list_supplier_products()`
- `remove_supplier_product()`
- `_store_upload()` — Persist an uploaded file under the private tenant uploads directory.
- `purchase_order_dict()`
- `list_purchase_orders()`
- `_po_in_tenant()`
- `_po_item()`
- `create_purchase_order()`
- `update_purchase_order()`
- `confirm_purchase_order()`
- `cancel_purchase_order()`
- `receive_purchase_order()` — Receive one or more lines into a store; stock and audit trail update together.
- `_po_items()`
- `update_purchase_order_logistics()`
- `add_po_attachment()`
- `get_po_attachment()`
- `get_supplier_attachment()`

### `retail_genie/settings/routes.py`

- `_payload()`
- `_error()`
- `_resolve_company()` — Resolve the company the acting user may administer settings for.
- `_require_company_admin()`
- `settings_index()`
- `_series_rows()` — Billing, order, and commercial document counters for one company.
- `update_tax()`
- `update_commission()`
- `update_global_discount()`
- `update_attendance()`
- `update_series_next_number()` — Move a document counter forward; every change is audited.
- `_advance_series()`
- `settings_summary_api()`

### `retail_genie/settings/service.py`

- **class `SettingsRuleError`**
    - `SettingsRuleError > __init__()`
- `_active_company()`
- `_require_manage_settings()`
- `_record()`
- `_as_bool()`
- `_as_percentage()`
- `_as_money()`
- `list_tax_settings()`
- `update_tax_settings()` — Replace the company's tax table in one audited transaction.
- `effective_tax_settings()`
- `get_commission_setting()`
- `update_commission_settings()`
- `effective_commission_setting()`
- `salesperson_commission()` — Commission accrues once interval sales meet the configured target.
- `list_global_discounts()`
- `update_global_discount_settings()`
- `company_today()`
- `effective_global_discount_percentage()` — Return the active dated global discount, or zero when none applies.
- `get_attendance_setting()`
- `update_attendance_settings()`
- `settings_summary()`

### `retail_genie/share.py`

- `_primary_lan_ipv4()` — Ask the OS which local IPv4 route it would use for outbound traffic.  UDP connect selects an interface and does not send an application packet. The reserved documentation address below is used only for route selection.
- `app_login_url()` — Return a safe login URL, honoring an operator-set public base URL first.

### `retail_genie/stock_audits/routes.py`

- `_payload()`
- `_error()`
- `_resolve_company()`
- `audits_page()`
- `create_audit_page()`
- `create_audit_api()`
- `start_audit_api()`
- `record_count_api()`
- `add_evidence_api()`
- `complete_audit_api()`
- `cancel_audit_api()`
- `audit_counts_api()`
- `audit_evidence_api()`
- `audit_detail_page()`
- `audit_report_page()`

### `retail_genie/stock_audits/service.py`

- **class `StockAuditRuleError`**
    - `StockAuditRuleError > __init__()`
- `_tenant_for_actor()`
- `_company_in_tenant()`
- `_require_manage_audits()`
- `_audit_number()`
- `audit_dict()`
- `create_stock_audit()`
- `_audit_for_actor()`
- `list_stock_audits()`
- `start_stock_audit()`
- `_conductor_check()`
- `record_count()`
- `_store_evidence()`
- `add_count_evidence()`
- `complete_stock_audit()` — Finalize the audit and post every variance as a stock adjustment.
- `cancel_stock_audit()`
- `audit_counts()`
- `audit_evidence()`

### `retail_genie/tenancy/service.py`

- `seed_tenant_data_policies()` — Create restrictive company-level defaults for every supported data domain.  Call this in the same transaction as container creation. Company-level is a safe default: it preserves standalone-company use but does not silently share data with newly added sibling companies.


## Appendix C — Complete application file tree

Local `.env`, Python caches, and runtime-created upload/backup folders are intentionally omitted. The preview directory contains illustrative synthetic-data screenshots.

```text
.env.example
.gitignore
APPLICATION_BLUEPRINT.md
LOCAL_INSTALL_GUIDE.md
README.md
database-schema.sql
file.md
install.ps1
list.md
preview/accounts.png
preview/dashboard.png
preview/login-desktop.png
preview/login-mobile.png
preview/point-of-sale.png
preview/pos-demo-open-bill.png
preview/pos-demo-settled-invoice.png
preview/products-inventory.png
preview/products-mobile.png
preview/settings.png
preview/stock-audits.png
preview/supply-chain.png
requirements.txt
retail_genie/__init__.py
retail_genie/admin/__init__.py
retail_genie/admin/backup_forms.py
retail_genie/admin/backup_routes.py
retail_genie/admin/forms.py
retail_genie/admin/routes.py
retail_genie/admin/tenancy_forms.py
retail_genie/admin/tenancy_routes.py
retail_genie/attendance/__init__.py
retail_genie/attendance/routes.py
retail_genie/attendance/service.py
retail_genie/auth/__init__.py
retail_genie/auth/forms.py
retail_genie/auth/permissions.py
retail_genie/auth/routes.py
retail_genie/auth/store_scope.py
retail_genie/auth/tenant_context.py
retail_genie/auth/tenant_policy.py
retail_genie/backups/__init__.py
retail_genie/backups/scheduler.py
retail_genie/backups/service.py
retail_genie/catalog/__init__.py
retail_genie/catalog/forms.py
retail_genie/catalog/routes.py
retail_genie/catalog/service.py
retail_genie/cloud/__init__.py
retail_genie/cloud/routes.py
retail_genie/cloud/service.py
retail_genie/commercial/__init__.py
retail_genie/commercial/emailing.py
retail_genie/commercial/routes.py
retail_genie/commercial/service.py
retail_genie/config.py
retail_genie/demo_data.py
retail_genie/device.py
retail_genie/display/__init__.py
retail_genie/display/routes.py
retail_genie/express/__init__.py
retail_genie/express/routes.py
retail_genie/extensions.py
retail_genie/health/__init__.py
retail_genie/health/routes.py
retail_genie/main/__init__.py
retail_genie/main/routes.py
retail_genie/messaging/__init__.py
retail_genie/messaging/routes.py
retail_genie/messaging/service.py
retail_genie/models/__init__.py
retail_genie/models/attendance.py
retail_genie/models/backup.py
retail_genie/models/billing.py
retail_genie/models/catalog.py
retail_genie/models/cloud.py
retail_genie/models/commercial.py
retail_genie/models/messaging.py
retail_genie/models/realtime.py
retail_genie/models/saas.py
retail_genie/models/scm.py
retail_genie/models/settings.py
retail_genie/models/stock_audit.py
retail_genie/models/tenancy.py
retail_genie/models/user.py
retail_genie/realtime/__init__.py
retail_genie/realtime/handlers.py
retail_genie/realtime/routes.py
retail_genie/realtime/service.py
retail_genie/reports/__init__.py
retail_genie/reports/routes.py
retail_genie/reports/service.py
retail_genie/saas/__init__.py
retail_genie/saas/forms.py
retail_genie/saas/routes.py
retail_genie/saas/service.py
retail_genie/sales/__init__.py
retail_genie/sales/routes.py
retail_genie/sales/service.py
retail_genie/scm/__init__.py
retail_genie/scm/routes.py
retail_genie/scm/service.py
retail_genie/settings/__init__.py
retail_genie/settings/routes.py
retail_genie/settings/service.py
retail_genie/share.py
retail_genie/static/css/app.css
retail_genie/static/js/cashup.js
retail_genie/static/js/catalog-offline-stock.js
retail_genie/static/js/catalog-realtime.js
retail_genie/static/js/express-checkout.js
retail_genie/static/js/pos.js
retail_genie/static/js/removal-approvals.js
retail_genie/static/js/sales-realtime.js
retail_genie/static/vendor/SOCKET.IO-CLIENT-LICENSE.txt
retail_genie/static/vendor/socket.io.min.js
retail_genie/stock_audits/__init__.py
retail_genie/stock_audits/routes.py
retail_genie/stock_audits/service.py
retail_genie/templates/admin/backups.html
retail_genie/templates/admin/billing_settings.html
retail_genie/templates/admin/child_company.html
retail_genie/templates/admin/companies.html
retail_genie/templates/admin/domain_policies.html
retail_genie/templates/admin/domain_policy_edit.html
retail_genie/templates/admin/domain_policy_index.html
retail_genie/templates/admin/store_assignments.html
retail_genie/templates/admin/stores.html
retail_genie/templates/admin/users.html
retail_genie/templates/attendance/breaks_dashboard.html
retail_genie/templates/attendance/index.html
retail_genie/templates/auth/change_password.html
retail_genie/templates/auth/login.html
retail_genie/templates/auth/select_tenant.html
retail_genie/templates/base.html
retail_genie/templates/catalog/categories.html
retail_genie/templates/catalog/labels.html
retail_genie/templates/catalog/products.html
retail_genie/templates/cloud/index.html
retail_genie/templates/commercial/demand_notice_print.html
retail_genie/templates/commercial/demand_notices.html
retail_genie/templates/commercial/quotation_print.html
retail_genie/templates/commercial/quotations.html
retail_genie/templates/display/lcd.html
retail_genie/templates/errors/403.html
retail_genie/templates/errors/404.html
retail_genie/templates/errors/500.html
retail_genie/templates/express/checkout.html
retail_genie/templates/main/dashboard.html
retail_genie/templates/messaging/compose.html
retail_genie/templates/messaging/index.html
retail_genie/templates/messaging/thread.html
retail_genie/templates/reports/activity.html
retail_genie/templates/reports/sales.html
retail_genie/templates/saas/invoice_print.html
retail_genie/templates/saas/plans.html
retail_genie/templates/saas/requests.html
retail_genie/templates/saas/subscriptions.html
retail_genie/templates/saas/tenant_portal.html
retail_genie/templates/sales/daily_cashup.html
retail_genie/templates/sales/order_print.html
retail_genie/templates/sales/orders.html
retail_genie/templates/sales/pos.html
retail_genie/templates/sales/removal_approvals.html
retail_genie/templates/sales/return_print.html
retail_genie/templates/sales/returns.html
retail_genie/templates/scm/dashboard.html
retail_genie/templates/scm/purchase_order.html
retail_genie/templates/scm/purchase_orders.html
retail_genie/templates/scm/supplier_detail.html
retail_genie/templates/scm/suppliers.html
retail_genie/templates/settings/index.html
retail_genie/templates/stock_audits/create.html
retail_genie/templates/stock_audits/detail.html
retail_genie/templates/stock_audits/index.html
retail_genie/templates/stock_audits/report.html
retail_genie/tenancy/__init__.py
retail_genie/tenancy/service.py
run.py
scripts/setup_database.py
seed_admin.py
wsgi.py
```
