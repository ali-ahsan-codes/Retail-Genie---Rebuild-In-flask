# Retail Genie Application: File Structure and Core Functionality Overview

This document outlines the main directories and key files within the Retail Genie application, highlighting their primary responsibilities and how they contribute to the overall functionality. Currency symbol used: OMR. Data synchronization interval is configurable for development (15s) vs. production (5s). Cloud file data is typically refreshed manually. Customer-facing documents like invoices and quotations are now bilingual (English/Arabic).

## Network Resilience & Performance
-   **Service Worker (`public/sw.js`)**: Handles caching of static assets and API GET requests. Includes cache invalidation logic triggered by messages from `ApiClient` and an `activate` event to clear old caches. Does **not** cache `/api/*` routes (including `/api/uploads/*`) by default. Provides offline fallback for cached content.
-   **Offline Queue (`src/lib/offlineQueue.ts`)**: Implements `EnhancedOfflineQueue` using IndexedDB (`idb-keyval`) to store mutating API requests (POST, PUT, DELETE) that fail due to network issues or specific server errors. Retries them with exponential backoff when online. Dispatches `offlineQueueSuccess` and `offlineQueueFailure` events.
-   **API Client (`src/lib/apiClient.ts`)**: Centralized client for API communication. Integrates with `OfflineQueue` for mutating requests, returning a synthetic `202Accepted` if queued. Notifies service worker to invalidate cache upon successful mutations.
-   **Database Concurrency**: The SQLite database connection is configured in `src/lib/server/database.ts` to use **Write-Ahead Logging (WAL) mode** and a **busy timeout**. This allows for significantly better concurrent performance in a multi-user environment by enabling simultaneous read and write operations.
-   **Network Status Hook (`src/hooks/useNetworkStatus.ts`)**: Detects online/offline status and provides a basic slow network indication.
-   **Network Status Bar (`src/components/network/NetworkStatusBar.tsx`)**: UI component providing feedback on network status.
-   **Optimistic UI Hook (`src/hooks/useOptimisticMutation.ts`)**: Framework for implementing optimistic UI updates. Integrated into `AppContext` for `addProduct`.

## Root Directory

-   **`next.config.js`**: Next.js configuration.
-   **`tailwind.config.ts`**: Tailwind CSS configuration.
-   **`tsconfig.json`**: TypeScript configuration.
-   **`package.json`**: Dependencies, scripts (no `postbuild` script for symlinking). Note: `genkit` and `@genkit-ai/next` have been removed.
-   **`src/`**: Main source code.
-   **`public/`**: Static assets (e.g., `logo.svg`, `favicon.svg`). **Does NOT store dynamic user uploads.**
    -   **`sw.js`**: The application's service worker file. Updated to bypass `/api/` routes and clear cache on activate.
-   **`uploads/`**: Root directory for all user-generated and dynamically uploaded files. This directory must be created manually at the project root.
    -   **`products/`**: Product image files.
    -   **`cloud/[userId]/`**: User-specific cloud files. Subdivided into `documents/` and `images/`.
        -   `cloud_files_metadata.ndjson` (metadata file, also within `uploads/cloud/[userId]/`).
    -   **`attendance/`**: Attendance selfie images.
    -   **`audits/`**:
        -   `selfies/`: Auditor start-audit selfie images.
        -   `item_images/`: Images/videos for audit item counts.
    -   **`csv/`**: Uploaded external store inventory CSVs.
    -   **`messaging/`**: Root for message attachments, organized by `[conversationId]/[messageId]`.
    -   **`scm/`**: For Supply Chain Management documents.
        - `documents/`: For general SCM documents like supplier contracts.
        - `po_invoices/`: For supplier invoices related to POs.
        - `po_attachments/`: Stores general attachments related to Purchase Orders, organized by PO ID.
        - `storage_evidence/`: Stores photos/videos of received stock in its storage location.
-   **`MAP/`**: Project documentation.
-   **`Data_Link/recreate_db.ts`**: Script to recreate the SQLite database.
-   **`scripts/cleanup.sh`**: Shell script for maintenance (e.g., clearing old uploads, cache).
-   **`scripts/init-uploads.js`**: Node.js script to initialize `uploads` directory structure (intended for manual run or integration into custom pre-start scripts, not part of default `npm start`).

## `src/app/` - Next.js App Router

-   **`layout.tsx` (Root)**: Main HTML shell. Includes `AppInitializer` (for service worker registration/unregistration and update logic), global providers, `NetworkStatusBar`, and the main background gradient.
-   **`page.tsx` (Root)**: Entry point, handles redirection.
-   **`globals.css`**: Global styles, updated to a modern, semi-transparent glassmorphism theme with an enhanced accent color for better visibility. Also includes modern, styled templates for product and invoice labels, including dashed borders for printouts.
-   **`error.tsx` (Root)`**: Global error boundary.

-   **`src/app/(auth)/login/page.tsx`**: User login UI. Handles user authentication by validating credentials. Specifically handles 'User not found' errors from the API by showing a generic "Invalid username or password" message to avoid username enumeration.

-   **`src/app/(main)/`**: Authenticated sections.
    *   Layouts and pages displaying uploaded content use the `/api/uploads/[...path]` route.
    *   `(main)/admin/products/page.tsx`: Main product management UI. Includes advanced filters for stock quantity.
    *   `(main)/admin/accounts/page.tsx`, `(main)/auditor/audits/[auditId]/conduct/page.tsx`.
    *   **`(main)/admin/label-printing/page.tsx`**: Unified UI for generating and printing modern styled product labels (with barcodes) and invoice ID labels. Uses a reliable new window printing method with injected CSS.
    -   **`(main)/express/page.tsx`**: New page for the streamlined Express Checkout role, featuring both barcode scanning and a manual product search tab.
    -   **`(main)/messaging/`**: New section for the internal messaging system UI.
    -   **`(main)/admin/scm/`**: New section for Supply Chain Management UI.
        - `po/[poId]/page.tsx`: Page for viewing and managing a specific Purchase Order.
        - `po/[poId]/edit/page.tsx`: Page for editing PO details.
    *   **`(main)/profile/page.tsx`**: Profile management page now includes a "Shift Summary" tab for Cashier and Express roles.

-   **`src/app/lcd-display/`**: LCD Order Status Display.

-   **`src/app/api/`**: Backend API route handlers.
    *   **`uploads/[...path]/route.ts`**: New route to serve files from the root `uploads/` directory.
    *   **`express/checkout/route.ts`**: New API route for processing Express Checkout sales.
    *   **`products/sku/[sku]/route.ts`**: New API route for fetching a product by its SKU.
    *   **`messaging/`**: New API routes for the messaging system. Message content is limited to 3500 characters.
    *   **`scm/supplier-products/`**: New API routes for Supplier-Product links.
    *   **`suppliers/`**: New API routes for Suppliers.
    *   **`purchase-orders/`**: New API routes for Purchase Orders.
    *   **`purchase-orders/[poId]/attachments/`**: New API routes for PO attachments.
    *   **`purchase-orders/[poId]/receive/route.ts`**: API route for recording received goods, now supports `grnAttachments` and `storageEvidence` file uploads.
    *   Other API routes interacting with file paths have been updated for the `uploads/` structure.
    *   Refer to `MAP/Structure/api_endpoints.md` for detailed API descriptions.

## `src/components/` - Reusable UI Components
-   **`messaging/`**: New components for the messaging system (e.g., `MessageComposer` with character count, `RecipientField`, `AttachmentManager`).
-   **`scm/`**: New components for SCM (e.g., `StorageCalculator`).
-   **`admin/ProductForm.tsx`**: A comprehensive form for creating/editing products, now includes an integrated "Suppliers" tab to manage supplier-product links directly.
-   **`admin/ProductBarcodeGenerator.tsx`**: Unified component for selecting products and printing modern-styled product labels and barcodes.
-   **`admin/InvoiceIdLabelGenerator.tsx`**: Component for searching and printing modern-styled invoice and demand notice ID labels.
-   **`admin/PrintableLabelWrapper.tsx`**: Component that defines the HTML structure and uses `jsbarcode` for modern product and invoice labels ready for printing.
-   Components displaying images (e.g., `ProductCard.tsx`, `SelfieImageDisplay.tsx`) construct image URLs using `/api/uploads/`.
-   `layout/AppInitializer.tsx`: Updated to handle service worker registration/unregistration based on environment and prompt updates.
-   `shared/SelfieImageDisplay.tsx`: Handles display of images served via `/api/uploads/`.
-   `InvoiceModal.tsx`, `DemandNoticeReceiptModal.tsx`: These components now contain logic to generate bilingual (English/Arabic) printouts.
-   `ui/card.tsx`, `ui/sidebar.tsx`: Updated to include styles for the glassmorphism theme (backdrop blur, transparency).
-   `ui/button.tsx`: Updated with enhanced hover and active states for better visual feedback.
-   `cashier/CashierShiftSummary.tsx`: Component used by both Cashier and Express roles to display transaction summaries.

## `src/config/`
-   **`branding.ts`**: App branding. Logo/favicon paths remain in `/public/assets/`.

## `src/context/AppContext.tsx` (`'use client'`)
-   Manages global state, including now fetching and providing messaging data (`conversations`, `totalUnreadCount`) and SCM data (`suppliers`, `purchaseOrders`).
-   Data refresh interval (`AUTO_REFRESH_INTERVAL`) is now configurable for development (15s) vs. production (5s).
-   Toast notifications for new messages are suppressed for the `display` user role.
-   Contains functions for sending new messages and replying to conversations.
-   Mutations now trigger `loadDataFromDb()` to ensure UI consistency after server updates.

## `src/lib/`
-   **`apiClient.ts`**: Handles API calls, integrates with Offline Queue, and notifies Service Worker for cache invalidation.
-   **`constants.ts`**: Initial data, now includes 'express' role.
-   **`database.ts` (Client-side API layer)**: Uses `ApiClient`. All API call functions.
-   **`offlineQueue.ts`**: Manages offline requests using IndexedDB.
-   **`server/database.ts` (Server-side)**: SQLite interaction. **Now enables WAL mode and a busy timeout for improved multi-user concurrency.** Path storage for images/files updated to be relative to `uploads/` root. Database path resolution is absolute. Enhanced `getDb` for connection resilience. Includes `getNextSeriesNumber` utility for generating formatted, sequential IDs.
-   **`server/cloudStorageUtils.ts`**: Utilities for cloud file storage, paths updated to `uploads/cloud/[userId]/`.

## `src/types/index.ts`
-   Includes new types for the messaging system: `Conversation`, `Message`, `MessageRecipient`, `Attachment`.
-   Includes new types for SCM: `Supplier`, `SupplierProduct`, `PurchaseOrder`, `POAttachment`, `SupplierAttachment` etc.
-   Interpretation of path fields (e.g., `imageUrl`) changes to mean paths relative to `uploads/` root.
-   Added 'express' to `UserRole` and `express_checkout` to `Permission`.

This structure reflects the move of dynamic uploads to a root `uploads/` directory, served by a dedicated API, and the addition of a comprehensive internal messaging system and a Supply Chain Management module.
