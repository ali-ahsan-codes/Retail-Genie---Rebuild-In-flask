# Phase 7 — SaaS productization

**Status: Implemented and locally verified.** The selected scope is managed plan/subscription administration, tenant usage limits, tenant-side plan requests, and subscription invoices. Phase 6's live MySQL/staging and office deployment gates remain open and separate from this local Phase 7 result.

## Product and safety decisions

- Tenant creation and the initial Company Admin remain provisioned by the Main Admin through the existing audited workflow. Public self-registration is not introduced.
- Plan prices are stored as OMR `DECIMAL(12,3)`. Null company/store/active-user limits mean unlimited; enforcement counts active resources inside a single tenant.
- A tenant with no assigned subscription remains grandfathered and unmetered. Assigning a plan is an explicit Main Admin action; existing tenants are not silently placed on paid plans.
- Company Admins can see their own plan, usage and invoices, and request a plan change. The Main Admin approves/rejects requests; applying a lower quota is blocked while current active usage exceeds it.
- Subscription invoices are issued/reconciled manually by the Main Admin. No payment gateway, card data, automatic charging, recurring billing worker, or automatic suspension for non-payment is introduced without a payment-provider and billing-policy decision.
- A Main Admin-set `suspended` or `canceled` status makes tenant write requests read-only while keeping the subscription portal available to request service. Reads remain available.
- All plan, subscription, invoice, request, review, and payment-reference changes are audited. Manual payment recording stores only an external receipt/reference; it does not claim to verify settlement with a bank/provider.

## Phase 7 local acceptance

- [x] Platform Admin can create/archive plans with validation for OMR precision and quotas.
- [x] Main Admin can assign a plan/status to a tenant and issue subscription invoices by period.
- [x] Company Admin can see tenant-scoped usage/invoices and request plan changes; only Main Admin can review and apply requests.
- [x] Active company/store/user provisioning respects the assigned tenant plan under a tenant-row lock; legacy unassigned tenants remain unaffected.
- [x] Suspended/canceled tenant write requests fail closed while reads and the plan-request path remain accessible.
- [x] Invoice printing uses three-decimal OMR; manual payment references are audited and duplicate invoice periods are rejected.
- [x] Full local all-phase regression: **153 passed, 1 skipped**. The skipped test requires a migrated disposable MySQL test database.
- [x] Complete Alembic chain upgraded on a temporary SQLite database; schema check, explicit downgrade to the prior head, re-upgrade to Phase 7 head, and final schema check passed.
- [x] Alembic rendered the full migration chain to offline MySQL DDL, including the Phase 7 tables. This generated SQL was not executed against a MySQL server.
- [ ] Live MySQL Phase 7 integration is not available in this workspace. No live-MySQL, staging, restore, or production readiness claim is made.

The SQLite migration run validates schema history and local ORM/migration alignment only; it does not replace MySQL validation or waive any Phase 6 deployment gates.
