# Factory Reset Instructions for Retail Genie

**WARNING: Performing these steps will permanently delete ALL application data, including user accounts, products, orders, uploaded images, demand notices, quotations, audits, SCM data, and settings. This action is irreversible. Proceed with extreme caution.**

## Steps to Factory Reset:

1.  **Stop the Application Server:**
    *   If your application is running (e.g., `npm run dev` or `npm run start`), stop it completely.

2.  **Delete Server-Side Data & Uploads:**
    You will need to manually delete the following file and folders from your project directory:

    *   **Database File:**
        *   `netpos.db` (This file is located at the root of your project)

    *   **All Uploaded Media & Files:**
        *   Delete the entire `uploads/` directory at the project root. This single directory contains:
            *   `uploads/products/` (product images)
            *   `uploads/cloud/[userId]/` (user cloud files, including `cloud_files_metadata.ndjson` within each user's directory)
            *   `uploads/attendance/` (attendance selfies)
            *   `uploads/audits/selfies/` (audit start selfies)
            *   `uploads/audits/item_images/` (audit item count media)
            *   `uploads/csv/` (external store CSVs)
            *   `uploads/messaging/` (message attachments)
            *   `uploads/scm/` (SCM documents like supplier contracts, PO attachments, GRNs, storage evidence photos, etc.)

    *   **(Optional but Recommended for a True Factory State) Next.js Build Cache:**
        *   Delete the entire folder: `.next/`
          (This will require a fresh build afterwards.)

3.  **Clear Client-Side (Browser) Data:**
    This step is crucial to ensure your browser doesn't hold onto old cached data or queued requests.

    *   Open your web browser's developer tools.
    *   Go to the "Application" tab (or "Storage" tab in Firefox).
    *   **Clear Site Data:** Look for an option like "Clear site data" or "Clear storage" and use it for your application's domain (e.g., `localhost:9002`). Make sure to select options to clear:
        *   Cookies
        *   Cache Storage (this includes Service Worker caches)
        *   IndexedDB (this will clear the Offline Queue)
        *   Local Storage
        *   Session Storage
    *   **Unregister Service Worker:** In the "Application" -> "Service Workers" section, find the service worker for your app and click "Unregister".
    *   Perform a "Hard Refresh" or "Empty Cache and Hard Reload" (often Ctrl+Shift+R or Cmd+Shift+R).

4.  **Re-initialize the Database:**
    *   Open your terminal in the project's root directory.
    *   Run the database recreation script:
        ```bash
        npm run recreate-db
        ```
        (Alternatively: `tsx ./Data_Link/recreate_db.ts`)
    *   This will create a new `netpos.db` file with the initial schema and seed data.

5.  **Manually Recreate Uploads Directory Structure (if deleted):**
    If you deleted the `uploads/` directory in step 2, you need to recreate its structure before starting the app. Open your terminal (e.g., PowerShell on Windows, or bash on Linux/macOS) in the project's root directory and run:
    ```bash
    mkdir uploads
    mkdir uploads\products
    mkdir uploads\cloud
    mkdir uploads\attendance
    mkdir uploads\audits
    mkdir uploads-audits\selfies
    mkdir uploads\audits\item_images
    mkdir uploads\csv
    mkdir -p uploads\messaging
    mkdir -p uploads\scm\documents
    mkdir -p uploads\scm\po_invoices
    mkdir -p uploads\scm\po_attachments
    mkdir -p uploads\scm\storage_evidence
    ```
    Ensure these directories are created successfully.

6.  **Rebuild the Application (if `.next/` was deleted):**
    *   If you deleted the `.next/` folder, you need to rebuild the application:
        ```bash
        npm run build
        ```

7.  **Restart the Application:**
    *   Start your development server:
        ```bash
        npm run dev
        ```
    *   Or, if you built for production, start your production server:
        ```bash
        npm run start
        ```

Your application should now be in a factory reset state, similar to a fresh installation. You will need to log in with the default admin credentials (e.g., `admin` / `password123`).
