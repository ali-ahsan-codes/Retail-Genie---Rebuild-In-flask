# Retail Genie API Endpoints

This document outlines the primary backend API endpoints for the Retail Genie application. These endpoints are handled by Next.js API Routes located in the `src/app/api/` directory. Currency values are typically processed as numbers, displayed as OMR on the frontend.

**Important Note on File Storage & Serving:**
-   All media files (product images, attendance selfies, audit media, user cloud files, external store CSVs, message attachments, SCM documents) are now stored locally on the server's filesystem in a root-level `uploads/` directory, structured by type.
-   **All uploaded files are served via a dedicated API route: `/api/uploads/[...path]`**.
-   Database entries related to these files store paths relative to the `uploads/` root (e.g., `products/image.jpg`, `scm/documents/contract.pdf`).
-   Frontend components will request these files using URLs like `/api/uploads/products/image.jpg`.

**Important Note on API Client and Offline Queueing:**
The application uses a central `ApiClient` (`src/lib/apiClient.ts`) for all backend communication.
-   `GET` requests are fetched directly. Caching is primarily handled by the Service Worker (`public/sw.js`).
-   Mutating requests (`POST`, `PUT`, `DELETE`) are designed to be resilient and can be queued offline if the network connection is lost or if the server is temporarily unavailable.
-   Authenticated endpoints may require an `X-User-ID` header, which is handled by the `ApiClient`.

## Base URL: `/api`

---

### File Serving (`/api/uploads`)
-   **`GET /uploads/[...path]`**: Serves files from the root `uploads/` directory.

---

### Messaging (`/api/messaging`)
- **`GET /conversations`**: Get all conversations for the authenticated user.
- **`POST /conversations`**: Create a new conversation and send the first message. Accepts `forwardedAttachmentIds` and multipart form data. Message content is limited to 3500 characters.
- **`GET /conversations/[conversationId]`**: Get details and all messages for a specific conversation. The response now includes full attachment metadata for each message.
- **`DELETE /conversations/[conversationId]`**: Delete an entire conversation.
- **`POST /conversations/[conversationId]/messages`**: Reply to an existing conversation. Accepts multipart form data. Message content is limited to 3500 characters.
- **`PUT /messages/[messageId]/read`**: Mark a specific message as read for the current user.
- **`GET /attachments?ids=[id1],[id2]`**: Get metadata for specific attachments (used for forwarding).

---

### Express Checkout (`/api/express`)
- **`POST /checkout`**: Processes a complete express sale. Creates an order, payment, and updates stock in a single transaction.

---

### Products (`/api/products`)
-   **`GET /`**: Fetch all products.
-   **`POST /`**: Create a new product.
-   **`GET /[productId]`**: Fetch a specific product by its ID.
-   **`PUT /[productId]`**: Update an existing product.
-   **`DELETE /[productId]`**: Delete a product.
-   **`POST /image`**: Upload a product image.
-   **`GET /sku/[sku]`**: Fetch a product by its SKU (for barcode scanning).

---

### Users (`/api/users`)
-   **`GET /`**: Fetch all users.
-   **`POST /`**: Create a new user.
-   **`GET /[userId]`**: Fetch a specific user.
-   **`GET /username/[username]`**: Fetch user by username for auth.
-   **`PUT /[userId]`**: Update a user.
-   **`DELETE /[userId]`**: Delete a user.

---

### Orders (`/api/orders`)
-   **`GET /`**: Fetch all orders.
-   **`POST /`**: Create a new order (standard flow).
-   **`PUT /[orderId]`**: Update order details.
-   **`DELETE /[orderId]`**: Delete an order.
-   **`POST /[orderId]/return`**: Process returns/exchanges.
-   **`GET /status`**: Fetches orders for LCD display.

---

### Attendance & Breaks (`/api/attendance`, `/api/breaks`)
-   **`GET /attendance`**: Fetch all attendance logs.
-   **`POST /attendance`**: Create an attendance log (clock-in).
-   **`DELETE /attendance/[logId]/selfie`**: Deletes a specific attendance selfie.
-   **`GET /breaks`**: Fetch all break logs.
-   **`POST /breaks`**: Start a new break.
-   **`PUT /breaks/[breakId]`**: End an active break.

---

### Demand Notices (`/api/demand-notices`)
-   **`GET /`**: Fetch all demand notices.
-   **`POST /`**: Create a new demand notice.
-   **`PUT /[noticeId]`**: Update a demand notice.
-   **`DELETE /[noticeId]`**: Delete a demand notice.
--   **`POST /[noticeId]/payment`**: Add advance payment.
-   **`POST /[noticeId]/convert-to-order`**: Convert DN to sales order.

---

### Quotations (`/api/quotations`)
-   **`GET /`**: Fetch quotations for the user.
-   **`POST /`**: Create a new quotation.
-   **`GET /[quotationId]`**: Fetch a specific quotation.
-   **`PUT /[quotationId]`**: Update an existing quotation.
-   **`DELETE /[quotationId]`**: Delete a quotation.
-   **`POST /[quotationId]/convert-to-order`**: Convert internal items to sales order.
-   **`POST /[quotationId]/convert-to-demand-notice`**: Convert external items to demand notices.

---

### Audits (`/api/audits`)
-   **`POST /`**: Create/Launch a new audit.
-   **`GET /`**: Fetch audits.
-   **`GET /[auditId]`**: Fetch a specific audit.
-   **`POST /[auditId]/start`**: Auditor starts a pending audit.
-   **`POST /[auditId]/items/[auditItemId]/counts`**: Auditor records a count.
-   **`POST /[auditId]/items/[auditItemId]/evidence`**: Helper to upload evidence media.
-   **`POST /[auditId]/complete`**: Auditor completes an audit.

---

### Supply Chain Management (SCM)
- **`POST /suppliers`**: Create new supplier (accepts multipart/form-data for attachments).
- **`GET /suppliers`**: List all suppliers.
- **`GET /suppliers/[supplierId]`**: Get supplier details.
- **`PUT /suppliers/[supplierId]`**: Update supplier.
- **`DELETE /suppliers/[supplierId]`**: Delete supplier.
- **`POST /scm/supplier-products`**: Link a product to a supplier with a specific price.
- **`GET /scm/supplier-products`**: Fetch all supplier-product links.
- **`DELETE /scm/supplier-products/[id]`**: Delete a specific supplier-product link.
- **`POST /purchase-orders`**: Create a new Purchase Order.
- **`GET /purchase-orders`**: List all Purchase Orders.
- **`GET /purchase-orders/[poId]`**: Get PO details.
- **`PUT /purchase-orders/[poId]`**: Update PO details (status, amount, logistics).
- **`POST /purchase-orders/[poId]/confirm`**: Confirm PO with supplier.
- **`POST /purchase-orders/[poId]/receive`**: Record received goods (accepts multipart/form-data).
- **`POST /purchase-orders/[poId]/attachments`**: Upload attachments to a PO.
- **`DELETE /purchase-orders/[poId]/attachments`**: Delete a specific PO attachment.

---

### Settings (`/api/settings`)
-   **`/tax`**: `GET`, `PUT`.
-   **`/global-discount`**: `GET`, `PUT`.
-   **`/commission`**: `GET`, `PUT`.
-   **`/invoice-number`**: `GET`, `PUT`.
-   **`/attendance`**: `GET`, `PUT`.

---

### Stores (External Inventory CSVs) (`/api/stores`)
-   **`POST /`**: Upload CSV.
-   **`GET /`**: List and parse CSVs.
-   **`DELETE /?filename={filename}`**: Delete a specific CSV.
-   **`DELETE /?action=deleteAll`**: Delete all CSVs.

---

### Cloud File Management (`/api/cloud`)
-   **`GET /files`**: Lists cloud files.
-   **`POST /upload`**: Upload file to cloud storage.
-   **`GET /file/[fileId]`**: Get metadata for a file.
-   **`PUT /file/[fileId]`**: Update notes for a file.
-   **`DELETE /file/[fileId]`**: Delete a cloud file.

---
This API structure with the new file serving mechanism via `/api/uploads` and standardized storage in the root `uploads/` directory aims for better production compatibility and organization.
