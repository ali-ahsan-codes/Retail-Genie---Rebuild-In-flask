# Legacy SQLite → MySQL landing schema

This is the reviewed mapping for the 27 tables in `Node Js Version/netpos.db`. The target metadata is implemented in `retail_genie/models/user.py` and `retail_genie/models/legacy_schema.py`; the importer and field conversions are in `retail_genie/migrations/legacy_import.py`. The checked-in SQLite database is sample data only.

## Mapping and type rules

- Table names are retained. Most legacy `camelCase` column names become `snake_case` (for example, `createdAt` → `created_at`, `userId` → `user_id`). IDs remain stable strings, with 64-character target columns.
- Every target table uses InnoDB and `utf8mb4`. JSON payloads are native MySQL JSON; paths and ordinary text remain text. Long message text, embedded selfie data, and product image data use MySQL `LONGTEXT` variants.
- Legacy monetary `REAL` columns become `DECIMAL(14,3)` for OMR. Percentage/rate columns use `DECIMAL(12,8)`. SQLite floating-point artifacts within a small rounding tolerance are normalized; values outside target precision/range fail preflight rather than being silently truncated.
- Legacy ISO date/time values become UTC `DATETIME`. Date-only values are represented at midnight UTC. Time-of-day settings remain text. Booleans and integer counters are validated during import.
- `users.password` is never copied into the new schema. By default, a random unknown password is Argon2-hashed and `force_password_change` is enabled. A separately confirmed policy may Argon2-hash vetted legacy passwords. Legacy paths are retained as metadata; this importer does not copy upload files.

## Table and column inventory

| Legacy table | MySQL target columns (in addition to `id`) |
|---|---|
| `users` | `username`, `password` → `password_hash` (Argon2 only), `role`, `permissions` (JSON), `activeBreakId` → `active_break_id`, `auto_enter_after_scan`; importer initializes `is_active`, `force_password_change`, `auth_version`, `created_at`, and `updated_at`. |
| `attachments` | `message_id`, `file_path`, `original_name`, `mime_type` |
| `attendance_logs` | `userId` → `user_id`, `timestamp`, `method`, `selfieDataUri` → `selfie_data_uri`, `selfieImagePath` → `selfie_image_path` |
| `attendance_settings` | `mandatory_attendance_time`, `is_mandatory_attendance_active`, `max_concurrent_breaks` |
| `audit_images` | `countEventId` → `count_event_id`, `imagePath` → `image_path`, `createdAt` → `created_at` |
| `audit_item_counts` | `auditItemId` → `audit_item_id`, `count`, `notes`, `createdAt` → `created_at` |
| `audit_items` | `auditId` → `audit_id`, `productId` → `product_id`, `productName` → `product_name`, `productSku` → `product_sku`, `currentStock` → `current_stock`, `finalAuditedQty` → `final_audited_qty`, `notes`, `createdAt` → `created_at`, `updatedAt` → `updated_at` |
| `audits` | `title`, `adminId` → `admin_id`, `auditorId` → `auditor_id`, `storeLocation` → `store_location`, `status`, `startedAt` → `started_at`, `completedAt` → `completed_at`, `createdAt` → `created_at`, `updatedAt` → `updated_at`, `auditorSelfiePath` → `auditor_selfie_path` |
| `break_logs` | `userId` → `user_id`, `startTime` → `start_time`, `endTime` → `end_time`, `durationMs` → `duration_ms` |
| `commission_settings` | `salesTarget` → `sales_target`, `commissionInterval` → `commission_interval`, `commissionPercentage` → `commission_percentage`, `isActive` → `is_active` |
| `conversations` | `subject`, `created_at`, `creator_id` |
| `demand_notices` | `salespersonId` → `salesperson_id`, `salespersonName` → `salesperson_name`, `customerContactNumber` → `customer_contact_number`, `productId` → `product_id`, `productName` → `product_name`, `productSku` → `product_sku`, `quantityRequested` → `quantity_requested`, `quantityFulfilled` → `quantity_fulfilled`, `agreedPrice` → `agreed_price`, `expectedAvailabilityDate` → `expected_availability_date`, `status`, `isNewProduct` → `is_new_product`, `createdAt` → `created_at`, `updatedAt` → `updated_at`, `notes`, `payments` (JSON), `linkedOrderId` → `linked_order_id` |
| `global_discount_settings` | `percentage`, `startDate` → `start_date`, `endDate` → `end_date`, `isActive` → `is_active`, `description` |
| `invoice_number_settings` | `nextNumber` → `next_number` |
| `message_recipients` | `message_id`, `recipient_id`, `recipient_type`, `read_at` |
| `messages` | `conversation_id`, `sender_id`, `content`, `sent_at` |
| `orders` | `primarySalespersonId` → `primary_salesperson_id`, `primarySalespersonName` → `primary_salesperson_name`, `secondarySalespersonId` → `secondary_salesperson_id`, `secondarySalespersonName` → `secondary_salesperson_name`, `primarySalespersonCommission` → `primary_salesperson_commission`, `secondarySalespersonCommission` → `secondary_salesperson_commission`, `items` (JSON), `subtotal`, `discountAmount` → `discount_amount`, `appliedDiscountPercentage` → `applied_discount_percentage`, `appliedGlobalDiscountPercentage` → `applied_global_discount_percentage`, `taxes` (JSON), `totalAmount` → `total_amount`, `status`, `deliveryStatus` → `delivery_status`, `customerName` → `customer_name`, `customerPhone` → `customer_phone`, `deliveryAddress` → `delivery_address`, `createdAt` → `created_at`, `updatedAt` → `updated_at`, `payments` (JSON), `storekeeperNotes` → `storekeeper_notes`, `cashierNotes` → `cashier_notes`, `reminderDate` → `reminder_date`, `reminderNotes` → `reminder_notes`, `returnTransactions` → `return_transactions` (JSON), `linkedDemandNoticeId` → `linked_demand_notice_id` |
| `po_attachments` | `po_id`, `file_path`, `original_name`, `notes`, `uploaded_at`, `uploaded_by_id`, `type` |
| `po_items` | `po_id`, `product_id`, `quantity_ordered`, `quantity_received`, `notes`, `updatedAt` → `updated_at` |
| `products` | `name`, `price`, `quantityInStock` → `quantity_in_stock`, `sku`, `expiryDate` → `expiry_date`, `imageUrl` → `image_url`, `category`, `isDemandNoticeProduct` → `is_demand_notice_product`, `lowStockThreshold` → `low_stock_threshold`, `lowStockPrice` → `low_stock_price` |
| `purchase_orders` | `supplier_id`, `status`, `total_amount`, `advance_paid`, `deadline`, `expected_delivery`, `invoice_path`, `createdAt` → `created_at`, `updatedAt` → `updated_at`, `transportationDetails` → `transportation_details` |
| `quotation_items` | `quotationId` → `quotation_id`, `productId` → `product_id`, `productName` → `product_name`, `productSku` → `product_sku`, `price`, `quantity`, `isExternal` → `is_external`, `converted` |
| `quotations` | `salespersonId` → `salesperson_id`, `customerName` → `customer_name`, `customerPhone` → `customer_phone`, `customerEmail` → `customer_email`, `customerAddress` → `customer_address`, `preparationDays` → `preparation_days`, `validUntil` → `valid_until`, `status`, `createdAt` → `created_at`, `updatedAt` → `updated_at`, `totalAmount` → `total_amount`, `notes` |
| `supplier_attachments` | `supplier_id`, `file_path`, `original_name`, `uploaded_at`, `uploaded_by_id` |
| `supplier_products` | `supplier_id`, `product_id`, `unit_price`, `document_path` |
| `suppliers` | `name`, `contact_email`, `phone`, `lead_time`, `notes` |
| `tax_settings` | `name`, `rate`, `enabled` |

## Foreign keys

The MySQL schema keeps these source relationships: `attachments.message_id → messages.id`; `attendance_logs.user_id`, `break_logs.user_id`, `conversations.creator_id`, `audits.admin_id/auditor_id`, `quotations.salesperson_id`, `orders.primary_salesperson_id/secondary_salesperson_id`, `demand_notices.salesperson_id`, `message_recipients.recipient_id`, `messages.sender_id`, `po_attachments.uploaded_by_id`, and `supplier_attachments.uploaded_by_id` → `users.id`; `messages.conversation_id → conversations.id`; `message_recipients.message_id → messages.id`; `audit_images.count_event_id → audit_item_counts.id`; `audit_item_counts.audit_item_id → audit_items.id`; `audit_items.audit_id → audits.id` and `product_id → products.id`; `demand_notices.product_id → products.id`; `demand_notices.linked_order_id → orders.id`; `orders.linked_demand_notice_id → demand_notices.id`; `po_items.po_id → purchase_orders.id` and `product_id → products.id`; `po_attachments.po_id → purchase_orders.id`; `purchase_orders.supplier_id → suppliers.id`; `quotation_items.quotation_id → quotations.id` and `product_id → products.id`; `supplier_attachments.supplier_id → suppliers.id`; and `supplier_products.supplier_id → suppliers.id` and `product_id → products.id`.

`orders` and `demand_notices` have a cyclic link. The migration creates the reverse edge after both tables exist. The importer temporarily inserts `orders.linked_demand_notice_id` as `NULL`, inserts notices, then restores the link in the same transaction before target foreign-key and reconciliation checks.

## Import safety and reconciliation

`flask --app wsgi import-sqlite --source PATH` is a read-only dry run. `--apply --confirm-apply` is required to write to MySQL/MariaDB. The importer checks the source schema and foreign keys, validates conversions, inserts in dependency order, preserves IDs, verifies every target payload and FK, and compares source/target row counts plus aggregate order totals, nested payment totals, stock units, and invoice-number counters. It never updates or deletes target rows; a conflicting ID aborts the transaction. The source file is opened with SQLite `mode=ro` and `immutable=1`, so use only a verified, closed/checkpointed SQLite backup.
