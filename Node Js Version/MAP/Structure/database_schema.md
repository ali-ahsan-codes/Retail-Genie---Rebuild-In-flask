# Retail Genie Database Schema (`netpos.db` - SQLite)

This document outlines the structure of the tables within the `netpos.db` SQLite database used by the Retail Genie application.

**Important Note on File Storage & Serving:**
- All binary files (product images, attendance selfies, audit media, cloud files, message attachments, SCM documents) are stored locally on the server's file system in a root-level `uploads/` directory.
- The database stores **paths relative to this `uploads/` root** (e.g., `products/image.jpg`, `scm/documents/contract.pdf`).
- Files are served to the client via a dedicated API endpoint: `/api/uploads/[...filePath]`.

**Important Note on Concurrency:**
- The database connection is configured to use **WAL (Write-Ahead Logging) mode** and a **busy timeout**. This significantly improves concurrent performance by allowing multiple read operations to happen at the same time as a write operation, reducing "database is locked" errors in a multi-user environment.

---

## Table: `products`
Stores product information.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID. |
| `name` | TEXT | NOT NULL | Product name. |
| `price` | REAL | NOT NULL | Price (OMR). |
| `quantityInStock` | INTEGER | NOT NULL | Stock quantity. |
| `sku` | TEXT | UNIQUE, NOT NULL | Product Code. |
| `imageUrl` | TEXT | | Relative path to image in `uploads/products/`. |
... (other columns omitted for brevity) ...

---

## Table: `users`
Stores user accounts and roles.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID. |
| `username` | TEXT | UNIQUE, NOT NULL | Login username. |
| `password` | TEXT | NOT NULL | Hashed password. |
| `role` | TEXT | NOT NULL | User role. |
| `permissions` | TEXT | | JSON array of permissions. |
... (other columns omitted for brevity) ...

---

## Table: `orders`
Stores sales order information.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique Order ID. |
| `items` | TEXT | NOT NULL | JSON array of `OrderItem` objects. |
| `totalAmount` | REAL | NOT NULL | Final amount. |
| `status` | TEXT | NOT NULL | Order status. |
| `createdAt` | TEXT | NOT NULL | ISO timestamp. |
... (other columns omitted for brevity) ...

---

## Table: `demand_notices`
Tracks requests for out-of-stock or new items.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID. |
| `productName` | TEXT | NOT NULL | Requested product name. |
| `quantityRequested` | INTEGER | NOT NULL | Quantity requested. |
| `status` | TEXT | NOT NULL | Status of the notice. |
| `linkedOrderId` | TEXT | FK -> `orders` | ID of Order if converted. |
... (other columns omitted for brevity) ...

---

## Table: `quotations` & `quotation_items`
Manages customer price quotations.
- **`quotations`**: Stores main quotation details (customer, dates, status).
- **`quotation_items`**: Stores individual items within a quotation.

---

## Table: `audits`, `audit_items`, `audit_item_counts`, `audit_images`
Manages stock auditing process.
- **`audits`**: Main audit session details. `auditorSelfiePath` stores relative path.
- **`audit_items`**: Items included in the audit.
- **`audit_item_counts`**: Specific counts for an item.
- **`audit_images`**: Media evidence for a count. `imagePath` stores relative path.

---

## Table: `conversations`
Groups messages into a single conversation thread.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique identifier for the conversation. |
| `subject` | TEXT | NOT NULL | The subject or title of the conversation. |
| `created_at` | TEXT | NOT NULL | ISO timestamp of creation. |
| `creator_id` | TEXT | NOT NULL, FK -> `users(id)` | User who started the conversation. |

---

## Table: `messages`
Stores individual messages within a conversation.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique identifier for the message. |
| `conversation_id` | TEXT | NOT NULL, FK -> `conversations(id)` | Links message to a conversation. |
| `sender_id` | TEXT | NOT NULL, FK -> `users(id)` | User who sent the message. |
| `content` | TEXT | NOT NULL | The text content of the message (max 3500 chars). |
| `sent_at` | TEXT | NOT NULL | ISO timestamp when the message was sent. |

---

## Table: `message_recipients`
Maps messages to their recipients and tracks read status.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique identifier for the recipient entry.|
| `message_id` | TEXT | NOT NULL, FK -> `messages(id)` | Links to the specific message. |
| `recipient_id` | TEXT | NOT NULL, FK -> `users(id)` | User ID of the recipient. |
| `recipient_type` | TEXT | NOT NULL | Type of recipient ('to', 'cc', 'bcc'). |
| `read_at` | TEXT | | ISO timestamp when the message was read. |

---

## Table: `attachments`
Stores metadata for message attachments.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique identifier for the attachment. |
| `message_id` | TEXT | NOT NULL, FK -> `messages(id)`| Links to the specific message. |
| `file_path` | TEXT | NOT NULL | Relative path to file in `uploads/messaging/...`. |
| `original_name` | TEXT | NOT NULL | The original filename from the user's computer. |
| `mime_type` | TEXT | NOT NULL | The MIME type of the file (e.g., 'application/pdf'). |

---

## Table: `suppliers`
Stores information about product suppliers.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID for the supplier. |
| `name` | TEXT | NOT NULL | Supplier company name. |
| `contact_email` | TEXT | | Primary contact email. |
| `phone` | TEXT | | Primary contact phone number. |
| `lead_time` | INTEGER | | Average lead time in days for orders. |
| `notes` | TEXT | | General notes about the supplier. |

---

## Table: `supplier_attachments`
Stores paths to documents associated with a supplier (e.g., contracts).
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID for the attachment link. |
| `supplier_id` | TEXT | NOT NULL, FK -> `suppliers(id)` ON DELETE CASCADE | Supplier reference. |
| `file_path` | TEXT | NOT NULL | Relative path to file in `uploads/scm/documents/`. |
| `original_name` | TEXT | NOT NULL | Original filename from user's computer. |
| `uploaded_at` | TEXT | NOT NULL | ISO timestamp of upload. |
| `uploaded_by_id` | TEXT | FK -> `users(id)` ON DELETE SET NULL | User who uploaded the file. |

---

## Table: `supplier_products`
Links products to suppliers, establishing an agreed-upon price.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID for the link. |
| `supplier_id` | TEXT | FK -> `suppliers(id)` ON DELETE CASCADE | Supplier reference. |
| `product_id` | TEXT | FK -> `products(id)` ON DELETE CASCADE | Product reference. |
| `unit_price` | REAL | NOT NULL | The price (OMR) agreed upon with this supplier. |
| `document_path` | TEXT | | Optional path to a specific contract/document for this pricing. |

---

## Table: `purchase_orders`
Stores main details for a purchase order sent to a supplier.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique PO ID (e.g., PO-000001). |
| `supplier_id` | TEXT | FK -> `suppliers(id)` | Supplier reference. |
| `status` | TEXT | NOT NULL | [Draft, Pending, Confirmed, Shipped, Received, Cancelled]. |
| `total_amount` | REAL | | Total value of the PO (OMR). |
| `advance_paid` | REAL | DEFAULT 0 | Advance payment made to the supplier. |
| `deadline` | TEXT | | Payment deadline for the PO. |
| `expected_delivery` | TEXT | | Expected delivery date from the supplier. |
| `invoice_path` | TEXT | | Path to supplier invoice in `uploads/scm/po_invoices/`. |
| `transportationDetails`| TEXT | | JSON object with vehicle_number, driver_contact, notes. |
| `createdAt` | TEXT | NOT NULL | ISO timestamp of creation. |
| `updatedAt` | TEXT | NOT NULL | ISO timestamp of last update. |

---

## Table: `po_items`
Stores the individual product items within a purchase order.
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID for the PO item line. |
| `po_id` | TEXT | NOT NULL, FK -> `purchase_orders(id)` ON DELETE CASCADE | Purchase Order reference. |
| `product_id` | TEXT | FK -> `products(id)` | Product reference. |
| `quantity_ordered` | INTEGER | NOT NULL | Quantity of the product ordered. |
| `quantity_received`| INTEGER | DEFAULT 0 | Quantity actually received from the supplier. |
| `notes` | TEXT | | Notes specific to this line item (e.g., backordered). |
| `updatedAt` | TEXT | | ISO timestamp of last update (e.g., when stock is received). |

---

## Table: `po_attachments`
Stores paths to documents related to a purchase order (e.g., GRNs, photos).
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Unique ID for the attachment link. |
| `po_id` | TEXT | NOT NULL, FK -> `purchase_orders(id)` ON DELETE CASCADE | Purchase Order reference. |
| `file_path` | TEXT | NOT NULL | Relative path to file (e.g., `uploads/scm/po_attachments/[poId]/...`). |
| `original_name` | TEXT | NOT NULL | Original filename from user's computer. |
| `notes` | TEXT | | Optional notes about the attachment. |
| `uploaded_at` | TEXT | NOT NULL | ISO timestamp of when the file was uploaded. |
| `uploaded_by_id`| TEXT | FK -> `users(id)` ON DELETE SET NULL | User ID of who uploaded the file. |
| `type` | TEXT | | Type of attachment (e.g., 'grn', 'storage_evidence', 'other'). |

... (Other tables like `tax_settings`, `attendance_logs`, etc., are also present but omitted for brevity.)
