# Role-based application verification

**Run date:** 2026-10-23. Tests used isolated SQLite demo data and synthetic role accounts. No production or live-MySQL database was accessed.

## Results

- Signed in as all **11 account roles** and captured each role's dashboard with its navigation expanded at 1440 × 1000. See [`dashboards/`](dashboards/).
- Exercised **156 role-specific dashboard/menu links** (deduplicated within each role): all returned HTTP 200 after authenticating; **0** unexpected 401/403 responses, request failures, or server errors.
- The super-admin flow selected the demo tenant workspace, then the company before opening company-scoped catalog tools. The tenant selector, Settings company picker, category/label company pickers, and both label search APIs were verified in-browser; each returned HTTP 200 with the company scope present and no page errors. This revealed and closed the missing company-selection path for categories and barcode labels.
- Revisited **25 manager-accessible module screens**; all returned HTTP 200. Current screenshots and route results are in [`../full-app/`](../full-app/) and [`../full-app/route-test-manager.json`](../full-app/route-test-manager.json).
- Ran the compatible application suite against the `Retail Genie Final` package with SQLite fixtures: **147 passed, 1 interactive CLI test deselected**. Migration/import-only tests were omitted because the final copy intentionally excludes the migration footprint. This is not live-MySQL validation.

The navigation audit checked GET links only; it did not submit business mutations or claim end-to-end coverage for every write workflow. Authentication and explicit workspace/company selection were exercised with temporary demo accounts.

## Role dashboards

| Role | Screenshot |
|---|---|
| Super admin | [Dashboard](dashboards/super-admin.png) · [Tenant selector](special-pages/super-admin-tenant-selection.png) · [Settings company picker](special-pages/super-admin-settings-company-picker.png) |
| Company admin | [Dashboard](dashboards/company-admin.png) |
| Admin | [Dashboard](dashboards/admin.png) |
| Manager | [Dashboard](dashboards/manager.png) |
| Salesperson | [Dashboard](dashboards/salesperson.png) |
| Storekeeper | [Dashboard](dashboards/storekeeper.png) |
| Cashier | [Dashboard](dashboards/cashier.png) |
| Logistics | [Dashboard](dashboards/logistics.png) |
| Auditor | [Dashboard](dashboards/auditor.png) |
| Display | [Dashboard](dashboards/display.png) |
| Express | [Dashboard](dashboards/express.png) |

Company-scoped super-admin screens: [Category picker](special-pages/super-admin-categories-company-picker.png) · [Selected categories](special-pages/super-admin-categories-selected-company.png) · [Label picker](special-pages/super-admin-labels-company-picker.png) · [Selected labels](special-pages/super-admin-labels-selected-company.png).

The dashboard images show the screens under test; the link checks were read-only GET requests, so no business records were changed.
