# Connected-mode ownership decisions

These are approved design rules, not implemented synchronization in Phase 1.

| Data | Authority | Other systems |
|---|---|---|
| Product, SKU, barcode, UOM, base prices/tax | Retail Genie | Read-only mapped snapshots |
| Warehouse stock / reservation / adjustments | Retail Genie | Availability cache, timestamped |
| Invoice and accounting ledger | Retail Genie | References/status only |
| Field order draft and visit capture | Gyro Pulse/mobile | Imported request, not confirmed stock |
| Order acceptance and stock approval | Retail Genie | Acknowledged status replicated outward |
| Company/branch identity | Retail Genie onboarding + explicit pairing | Stable shared UUID mapping |
| Field authentication and device grants | Gyro Pulse | Linked Retail Genie staff identity |
| Staff activation / field eligibility | Retail Genie in connected mode | Synced provisioning/revocation; no password copying |

A synced stock copy is NOT another stock ledger. Receiving an event does not reserve stock.
The company enters stock only once, in Retail Genie. Connected-mode field stock mutation must
be blocked when Phase 2/4 guards are built; Phase 1 copies still contain inherited standalone
mutation endpoints, so they must not be connected to a real company yet.

Field-only users can be provisioned without POS/accounting permissions; office-only users need
not receive mobile credentials. Shared login passwords/master secrets are not a sync strategy.
Revocation while entirely offline cannot be instantaneous: bounded offline grants and visible
expiry will be specified in Phase 2/6.

First release: one authoritative office deployment per company. Multiple warehouses are not
multiple independent writable replicas. Van-specific stock, if introduced later, is an audited
allocation/transfer out of the same ledger, not duplicated stock.

Delivery guarantees: at-least-once transport with idempotent transactional processing; durable
acks at device/office/cloud are separate. No claim of instantaneous consistency while disconnected.
