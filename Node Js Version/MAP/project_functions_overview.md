# Retail Genie Application: Functional Overview

This document provides a high-level overview of the key features and functionalities of the Retail Genie application. Branding, invoice details, and return policy notes are configured via `src/config/branding.ts`. Data synchronization for core database entities with the server occurs periodically. User cloud file data is refreshed manually. Error handling and reporting mechanisms are in place. The root `uploads/` directory and its subdirectories must be created manually if they do not exist.

## I. Core User Roles & Dashboards
-   **Admin**: Full system access, dashboards for overview, user management, product management, all orders, financial settings, audit management, SCM, reports (including exports with cashier payment details), system configuration.
-   **Manager**: Configurable access based on permissions (e.g., can manage products, orders, users, audits, SCM). May have access to operational dashboards for other roles.
-   **Salesperson**: Dashboard for sales, quotation creation, demand notice management, personal sales reports.
-   **Storekeeper**: Dashboard for order preparation, stock receiving, demand notice stock processing, and PO receiving.
-   **Cashier**: Dashboard for payment processing. Features a streamlined UI with a single, context-aware "Pay" button that handles both partial and full payments based on the amount entered. Also allows viewing demand notice details for advance payments.
-   **Logistics**: Dashboard for order tracking, delivery status updates, and follow-up reminders. Can view assigned Purchase Orders, manage transportation details (assign vehicle/driver), and update the PO status (e.g., to "Shipped").
-   **Auditor**: Dashboard listing assigned audits, interface for conducting audits, and viewing completed audit reports.
-   **Express**: A simplified checkout interface featuring tabs for rapid barcode-driven sales and manual product search. Supports immediate full payment with a change calculator and direct-to-print receipts. Now has access to Messaging and My Cloud Files.
-   **Display**: Access only to the LCD Order Status Display page.

## II. Authentication & Authorization
-   User login with username and password.
-   Role-based access control (RBAC) for different sections and features.
-   Granular permissions for 'manager' role (e.g., `manage_products`, `manage_orders`, `manage_audits`, `manage_suppliers`).
-   Admins/Managers can view and manage all quotations.
-   Auditors have `conduct_audits` permission for audits assigned to them.
-   Express users have `express_checkout` permission.

## III. Product & Inventory Management
-   **Product Catalog**: View list of all products with details. Features advanced filtering by text search and stock quantity (e.g., less than, greater than, equals).
-   **Admin/Manager CRUD**: Create, Read, Update, Delete products. The product form includes an integrated tab for managing supplier links.
-   **Image Upload**: Product images uploaded and stored locally on the server in `uploads/products/`. Path relative to `uploads/` stored in DB. Served via `/api/uploads/products/[filename]`.
-   **CSV Import/Export**: Admin/Manager can import/export product data.
-   **External Stores Data**: Admin/Manager can upload CSVs (stored in `uploads/csv/`), view parsed data. CSVs are served via `/api/uploads/csv/[filename]`.
-   **Label Printing**: Admin/Manager can generate and print modern, styled product labels (with barcodes) and invoice ID labels from a unified interface. Uses `jsbarcode` for client-side SVG barcode generation for crisp printing. A reliable new-window printing method with injected CSS is used, and dashed borders are added to printed product labels as a cutting guide.
-   **Low Stock Pricing**: Special pricing for low stock products.

## IV. Supply Chain Management (SCM)
-   **Supplier Management**: Admins/Managers can add, view, and edit supplier information, including attaching multiple documents. Supplier IDs can be customized or auto-generated.
-   **Supplier-Product Linking**: Link inventory products to specific suppliers with agreed-upon unit prices. This can be managed from the main SCM dashboard or directly from a product's edit page.
-   **Purchase Order (PO) Management**: Create, manage, and track purchase orders from draft to received. Includes ability to add products not yet in the system, edit PO details, and upload/manage attachments (GRNs, invoices, general files).
-   **Stock Receiving**: Storekeepers can verify and receive incoming stock against purchase orders, including uploading picture/video evidence for GRN and for where stock is stored (`storage_evidence`). The system correctly categorizes GRN documents for verification.
-   **Logistics Management**: Logistics users can view assigned POs, manage transportation details (assign vehicle/driver, add notes), and update the status of shipments (e.g., from 'Confirmed' to 'Shipped').
-   **Document Management**: Upload and associate documents (contracts, invoices) with suppliers and POs. Files stored in `uploads/scm/`. Attachment types are categorized (e.g., `grn`, `storage_evidence`).
-   **Activity Logging & Tracking**: View a timeline of all actions taken on a PO, including document uploads by specific user roles.

## V. Order Processing & Sales
(Functionality remains the same, image display paths for products in order details will use `/api/uploads/`)

## VI. Express Checkout (New)
-   **Dual-Mode Product Entry**: A dedicated UI (`/express`) with tabs for both barcode scanning and manual product search, allowing flexible cart management.
-   **Immediate Full Payment**: Process sales with immediate, full payment via multiple methods (Cash, Card, Bank Transfer) in a single transaction. A change calculator is provided for cash payments.
-   **Direct-to-Print Receipts**: Upon successful payment, a detailed, bilingual invoice is automatically generated and sent to the browser's print dialog. The interface then resets for the next customer.
-   **Atomic Transactions**: The backend (`POST /api/express/checkout`) creates the order, records the payment(s), and deducts stock in a single, all-or-nothing database transaction.

## VII. Quotation Management
-   **Creation & Editing**: Salespersons can create detailed quotations, adding items from existing inventory or as new, externally sourced products.
-   **Status Workflow**: Quotations move through a lifecycle (`draft`, `sent`, `accepted`, `rejected`, `revision`, `hold`, `converted`) managed by the salesperson or an admin.
-   **Conversion to Order/DN**: Accepted quotations can be converted into Sales Orders (for internal items) or Demand Notices (for external items), streamlining the sales process.
-   **Flexible, Bilingual Printing**: Users can print quotations in two professional, bilingual (English/Arabic) formats: a full-page A4 version suitable for company letterheads and a compact A5 slip.

## VIII. User & Staff Management
-   **User Accounts**: CRUD operations, role/permission assignment. Now includes 'Express' role.
-   **Profile Management**: User profiles. 'Cashier' and 'Express' roles have access to a printable Shift Summary report.
-   **Attendance Tracking**: Clock-in/out. Selfies saved to `uploads/attendance/`. Path relative to `uploads/` stored in DB. Served via `/api/uploads/attendance/[filename]`.
-   **Break Management**: Start/end breaks.
-   **Mandatory Attendance**: Configurable.

## IX. Demand Notices
-   **Creation**: Salespersons can create demand notices for products that are out of stock or for new, unlisted items.
-   **Management**: Admins/Managers can review, approve, and manage the fulfillment workflow for all demand notices.
-   **Stock Updates**: The system automatically updates the status of notices (e.g., to 'full_stock_available') when stock for the requested product is replenished.
-   **Conversion**: Accepted notices can be converted into Sales Orders by salespersons or managers for final processing.
-   **Advance Payments**: Cashiers can accept and record advance payments against a demand notice.
-   **Bilingual Receipt Printing**: A clear, bilingual (English/Arabic) receipt, similar in structure to the main sales invoice, can be printed for any advance payments made. This receipt is optimized for 80mm thermal receipt printers.

## X. Financial Settings & Configuration (Admin/Manager)
(Functionality remains the same)

## XI. Cloud File Storage (`/my-cloud`, Admin File Management)
-   **Personal Storage**: Users have personal cloud storage.
-   **File Management**: Upload, view, add notes, delete files.
-   **Admin View**: Admins/Managers can view all system and user cloud files.
-   **Local Storage**: Files stored in `uploads/cloud/[userId]/[images|documents]/`. Metadata in `uploads/cloud/[userId]/cloud_files_metadata.ndjson`. Paths relative to `uploads/` stored. Served via `/api/uploads/cloud/[userId]/[type]/[filename]`.

## XII. Audit Management & Conduction
-   **Launch Audits**: Admins/Managers launch audits (includes defining items from product list or manually).
-   **Auditor Assignment**: Assign to 'auditor' role users.
-   **Conduct Audits**:
    -   **Start Audit**: Auditor selfie saved to `uploads/audits/selfies/`. Path relative to `uploads/` stored. Served via `/api/uploads/audits/selfies/[filename]`.
    -   **Item Counting**: Auditor records counts. Optional media (image/video) per count saved to `uploads/audits/item_images/`. Paths relative to `uploads/` stored. Served via `/api/uploads/audits/item_images/[filename]`.
    -   **Complete Audit**: Finalize and complete. `finalAuditedQty` for each item is calculated.
-   **Audit Reports**: View detailed reports with media, variances, and value summaries.
-   **Audit IDs**: System generated (e.g., AUD-000001).

## XIII. Messaging System
-   **Internal Conversations**: Users can send and receive messages with attachments.
-   **Rich Text & Attachments**: Compose messages with basic formatting (3500-character limit) and attach multiple files.
-   **Forwarding with Attachments**: Forward messages while retaining their original attachments. The system links to the original file to avoid duplication.
-   **Read Status**: Tracks read/unread status of messages.
-   **Notifications**: Toast notifications for new incoming messages, including SCM alerts from a "System" user.

## XIV. Reporting & Analytics
(Functionality remains the same, with future hooks for PO financial tracking).

## XV. Logistics & Delivery Management
(Functionality remains the same)

## XVI. Returns & Exchanges (Admin/Manager - `/admin/returns/[orderId]`)
- Process returns and exchanges for items from completed or paid orders.
- Automatically adjusts stock levels for returned items.
- **Bilingual Return Slip Printing**: Generate and print a detailed, bilingual (English/Arabic) slip for each individual return transaction from the order's invoice view.

## XVII. LCD Order Status Display (`/lcd-display`)
(Functionality remains the same)

## XVIII. System & Data Management

*   **Branding**: Configurable via `src/config/branding.ts`.
*   **UI & UX**: Next.js, React, ShadCN UI, Tailwind CSS. Features a modern, semi-transparent glassmorphism design with enhanced button hover and active states.
*   **Data Persistence**:
    *   **Main Database (`netpos.db` - SQLite)**: Stores core data. Paths to uploaded files are now relative to the root `uploads/` directory. The database is configured for improved multi-user performance using **WAL (Write-Ahead Logging) mode** and a busy timeout. Sequential document IDs (for invoices, quotations, demand notices, audits, purchase orders) are managed via the `invoice_number_settings` table and generated by a central utility (`getNextSeriesNumber`).
    *   **Local Filesystem Storage (root `uploads/` directory)**:
        *   `uploads/products/`: Product images.
        *   `uploads/cloud/[userId]/[images|documents]/`: User cloud files.
        *   `uploads/attendance/`: Attendance selfies.
        *   `uploads/audits/selfies/` & `uploads/audits/item_images/`: Audit media.
        *   `uploads/csv/`: External store CSVs.
        *   `uploads/messaging/`: Message attachments.
        *   `uploads/scm/`: SCM related documents (including `po_attachments`, `po_invoices`, `storage_evidence`).
    *   **Cloud Metadata (NDJSON in `uploads/cloud/[userId]/cloud_files_metadata.ndjson`)**: Stores metadata for cloud files.
    *   **Offline Queue (IndexedDB)**: Manages offline API requests.
*   **Printing**: Generates print-friendly, bilingual (English/Arabic) slips for invoices, demand notice receipts, and return slips. Product labels are generated as clean, centered, SVG-based barcodes for crisp printing at a standard 40mm x 27mm size, with a dashed border guide. Invoice ID labels also have modern, styled templates. Sales, DN, and return receipts are formatted for 80mm thermal receipt printers using dashed bottom borders between sections instead of a full outer border. Quotations offer flexible bilingual printing options for both A4 (letterhead) and A5 paper sizes. A professional, modernized A4 print layout is available for the Cashier/Express Shift Summary.
*   **File Serving**: All files from the `uploads/` directory are served via `/api/uploads/[...filePath]`.
*   **Network Resilience**: Service Worker caching (excluding `/api/` routes), API Client with Offline Queue, Network Status Bar. Service Worker unregistration in dev, updates in prod.
*   **Optimistic UI**: Foundationally implemented for product additions.
*   **Data Synchronization**: Periodic background refreshes. Sync interval configurable (Dev: 15s, Prod: 5s). AppContext mutations trigger data refresh.
*   **Factory Reset**: Instructions in `MAP/Factory_reset.md` updated for new `uploads/` directory and manual folder recreation.
*   **Production Build**: No `postbuild` script for symlinking. `uploads` directory management is manual or via custom scripts.
*   **Cleanup Script**: `scripts/cleanup.sh` for clearing old uploads and caches.
*   **Initialization Script**: `scripts/init-uploads.js` (optional) to help create `uploads` directory structure if run manually.

This overview reflects the significant change in file storage to a root `uploads/` directory, serving via a dedicated API, and the addition of a comprehensive internal messaging and Supply Chain Management module.
