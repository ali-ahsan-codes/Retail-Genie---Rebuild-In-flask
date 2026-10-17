// src/lib/server/database.ts
import sqlite3 from 'sqlite3';
import { open, type Database } from 'sqlite';
import path from 'path';
import fs from 'fs';
import type { Product, User, Order, AttendanceLog, BreakLog, DeliveryStatus, DemandNotice, DemandNoticeStatus, TaxSetting, GlobalDiscountSetting, Permission, OrderItem, PaymentDetail, ReturnTransactionInfo, CommissionSetting, SeriesNumberSetting, AttendanceSetting, Quotation, QuotationItem, SeriesId, Audit, AuditItem, AuditItemCount, AuditImage, Supplier, PurchaseOrder, POItem, POAttachment } from '@/types';
import { INITIAL_PRODUCTS, INITIAL_USERS, INITIAL_ORDERS, INITIAL_DEMAND_NOTICES, INITIAL_TAX_SETTINGS, INITIAL_GLOBAL_DISCOUNT_SETTING, INITIAL_COMMISSION_SETTING, INITIAL_INVOICE_NUMBER_SETTING, INITIAL_QUOTATION_NUMBER_SETTING, INITIAL_DEMAND_NOTICE_NUMBER_SETTING, INITIAL_ATTENDANCE_SETTING, INITIAL_AUDIT_NUMBER_SETTING } from '@/lib/constants';
import { format, isValid, parseISO } from 'date-fns';

const DB_FILE_NAME = 'netpos.db';
const DB_PATH = path.join(process.cwd(), DB_FILE_NAME);

let db: Database | null = null;
let isDbInitializing = false; // Mutex for initialization
let dbInitializationPromise: Promise<Database | null> | null = null;


async function ensureInitialUsers(dbInstance: Database): Promise<void> {
  console.log('[DB] Ensuring initial users are present...');
  for (const user of INITIAL_USERS) {
    await dbInstance.run(
      'INSERT OR IGNORE INTO users (id, username, password, role, permissions, activeBreakId) VALUES (?, ?, ?, ?, ?, ?)',
      [
        user.id,
        user.username,
        user.password,
        user.role,
        JSON.stringify(user.permissions || []),
        user.activeBreakId
      ]
    );
  }
  console.log('[DB] Initial users check complete.');
}

async function performDbInitialization(): Promise<Database | null> {
    try {
        console.log(`[DB] Performing DB Initialization. DB_PATH: ${DB_PATH}`);
        const dbExists = fs.existsSync(DB_PATH);
        const dir = path.dirname(DB_PATH);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
            console.log(`[DB] Created directory: ${dir}`);
        }

        const newDbInstance = await open({
            filename: DB_PATH,
            driver: sqlite3.Database,
        });
        console.log('[DB] Database connection established.');
        
        // Enable WAL mode and set a busy timeout for better concurrency
        await newDbInstance.exec('PRAGMA journal_mode=WAL;');
        await newDbInstance.exec('PRAGMA busy_timeout=5000;'); // 5 seconds
        console.log('[DB] WAL mode enabled and busy timeout set.');


        if (!dbExists) {
            console.log('[DB] New database. Initializing schema and seeding data...');
            await initializeSchema(newDbInstance);
            await seedInitialData(newDbInstance);
            console.log('[DB] Database initialized and seeded.');
        } else {
            console.log('[DB] Existing database. Verifying schema and core data...');
            await initializeSchema(newDbInstance); // Migrates
            await ensureInitialUsers(newDbInstance); // Ensures users
            
            const settingsToEnsure = [
                { table: 'tax_settings', initialData: INITIAL_TAX_SETTINGS, seedFn: async () => {
                    for (const setting of INITIAL_TAX_SETTINGS) {
                        await newDbInstance.run('INSERT OR IGNORE INTO tax_settings (id, name, rate, enabled) VALUES (?, ?, ?, ?)', 
                        setting.id, setting.name, setting.rate, setting.enabled ? 1 : 0);
                    }
                }},
                { table: 'global_discount_settings', initialData: INITIAL_GLOBAL_DISCOUNT_SETTING, seedFn: async () => {
                    if (INITIAL_GLOBAL_DISCOUNT_SETTING) {
                        const gds = INITIAL_GLOBAL_DISCOUNT_SETTING;
                        await newDbInstance.run('INSERT OR IGNORE INTO global_discount_settings (id, percentage, startDate, endDate, isActive, description) VALUES (?, ?, ?, ?, ?, ?)', 
                        gds.id, gds.percentage, gds.startDate, gds.endDate, gds.isActive ? 1 : 0, gds.description);
                    }
                }},
                { table: 'commission_settings', initialData: INITIAL_COMMISSION_SETTING, seedFn: async () => {
                    if (INITIAL_COMMISSION_SETTING) {
                        const cs = INITIAL_COMMISSION_SETTING;
                        await newDbInstance.run('INSERT OR IGNORE INTO commission_settings (id, salesTarget, commissionInterval, commissionPercentage, isActive) VALUES (?, ?, ?, ?, ?)', 
                        cs.id, cs.salesTarget, cs.commissionInterval, cs.commissionPercentage, cs.isActive ? 1 : 0);
                    }
                }},
                { table: 'invoice_number_settings', initialData: [INITIAL_INVOICE_NUMBER_SETTING, INITIAL_QUOTATION_NUMBER_SETTING, INITIAL_DEMAND_NOTICE_NUMBER_SETTING, INITIAL_AUDIT_NUMBER_SETTING], seedFn: async () => {
                     await newDbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_INVOICE_NUMBER_SETTING.id, INITIAL_INVOICE_NUMBER_SETTING.nextNumber);
                     await newDbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_QUOTATION_NUMBER_SETTING.id, INITIAL_QUOTATION_NUMBER_SETTING.nextNumber);
                     await newDbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_DEMAND_NOTICE_NUMBER_SETTING.id, INITIAL_DEMAND_NOTICE_NUMBER_SETTING.nextNumber);
                     await newDbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_AUDIT_NUMBER_SETTING.id, INITIAL_AUDIT_NUMBER_SETTING.nextNumber);
                }},
                { table: 'attendance_settings', initialData: INITIAL_ATTENDANCE_SETTING, seedFn: async () => {
                    if (INITIAL_ATTENDANCE_SETTING) {
                        const as = INITIAL_ATTENDANCE_SETTING;
                        await newDbInstance.run('INSERT OR IGNORE INTO attendance_settings (id, mandatory_attendance_time, is_mandatory_attendance_active, max_concurrent_breaks) VALUES (?, ?, ?, ?)', 
                        as.id, as.mandatory_attendance_time, as.is_mandatory_attendance_active ? 1 : 0, as.max_concurrent_breaks);
                    }
                }}
            ];

            for (const settingInfo of settingsToEnsure) {
              try {
                const countResult = await newDbInstance.get(`SELECT COUNT(*) as count FROM ${settingInfo.table}`);
                if (countResult?.count === 0 && settingInfo.initialData) {
                  console.log(`[DB] Seeding initial ${settingInfo.table}...`);
                  await settingInfo.seedFn();
                  console.log(`[DB] Initial ${settingInfo.table} seeded.`);
                } else if (settingInfo.table === 'invoice_number_settings') { 
                    const seriesIds: SeriesId[] = ['invoice', 'quotation', 'demand_notice', 'audit', 'po'];
                    for (const seriesId of seriesIds) {
                        const row = await newDbInstance.get('SELECT id FROM invoice_number_settings WHERE id = ?', seriesId);
                        if (!row) {
                            console.log(`[DB] Seeding missing series ${seriesId} in invoice_number_settings...`);
                            let nextNum = 1;
                            if (seriesId === 'invoice') nextNum = INITIAL_INVOICE_NUMBER_SETTING.nextNumber;
                            if (seriesId === 'quotation') nextNum = INITIAL_QUOTATION_NUMBER_SETTING.nextNumber;
                            if (seriesId === 'demand_notice') nextNum = INITIAL_DEMAND_NOTICE_NUMBER_SETTING.nextNumber;
                            if (seriesId === 'audit') nextNum = INITIAL_AUDIT_NUMBER_SETTING.nextNumber;
                            if (seriesId === 'po') nextNum = 1; // Default for new PO series
                            await newDbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', seriesId, nextNum);
                        }
                    }
                }
              } catch (e: any) {
                console.error(`[DB] Error checking/seeding ${settingInfo.table}:`, e.message);
              }
            }
            console.log('[DB] Initial data checks complete for existing database.');
        }
        return newDbInstance;
    } catch (error: any) {
        console.error('[DB] CRITICAL ERROR: Failed to open or initialize database in performDbInitialization:', error.message, error.stack);
        return null; 
    } finally {
        isDbInitializing = false;
        dbInitializationPromise = null; 
    }
}


export async function getDb(): Promise<Database | null> {
    if (db) {
        try {
            // A simple, fast query to check if the connection is still alive.
            await db.get('SELECT 1'); 
            return db; // Connection is good, return cached instance.
        } catch (e) {
            console.warn('[DB] Stale database connection detected. Attempting to re-open.', (e as Error).message);
            try { await db.close(); } catch (closeError) { /* ignore error during close, as we're re-opening anyway */ }
            db = null; // Force re-initialization by falling through.
        }
    }

    if (isDbInitializing && dbInitializationPromise) {
        console.log('[DB] Waiting for ongoing DB initialization to complete...');
        return dbInitializationPromise;
    }
    
    if (isDbInitializing && !dbInitializationPromise) {
        console.warn('[DB] Inconsistent State: isDbInitializing is true, but no initialization promise found. Waiting briefly before retrying...');
        await new Promise(resolve => setTimeout(resolve, 500));
        return getDb();
    }

    isDbInitializing = true;
    dbInitializationPromise = performDbInitialization().then(initializedDb => {
        if (!initializedDb) {
            console.error("[DB getDb] performDbInitialization returned null. Database is not available.");
        }
        db = initializedDb;
        return db;
    }).catch(err => {
        console.error("[DB getDb] Unhandled exception during performDbInitialization promise.", err);
        db = null;
        return null;
    });
    
    return dbInitializationPromise;
}


async function columnExists(dbInstance: Database, tableName: string, columnName: string): Promise<boolean> {
  const columns = await dbInstance.all(`PRAGMA table_info(${tableName});`);
  return columns.some(col => col.name === columnName);
}

async function initializeSchema(dbInstance: Database): Promise<void> {
  console.log("[DB] Attempting to create table: products");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS products (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      price REAL NOT NULL,
      quantityInStock INTEGER NOT NULL,
      sku TEXT UNIQUE NOT NULL,
      expiryDate TEXT,
      imageUrl TEXT,
      category TEXT,
      isDemandNoticeProduct INTEGER DEFAULT 0,
      lowStockThreshold INTEGER,
      lowStockPrice REAL
    );
  `);
  console.log("[DB] Table 'products' created or already exists.");

  console.log("[DB] Attempting to create table: users");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      role TEXT NOT NULL,
      permissions TEXT,
      activeBreakId TEXT,
      auto_enter_after_scan BOOLEAN DEFAULT 1
    );
  `);
  console.log("[DB] Table 'users' created or already exists.");
  if (!await columnExists(dbInstance, 'users', 'auto_enter_after_scan')) {
    console.log("[DB] MIGRATION: Adding 'auto_enter_after_scan' column to 'users' table.");
    await dbInstance.exec('ALTER TABLE users ADD COLUMN auto_enter_after_scan BOOLEAN DEFAULT 1;');
  }

  console.log("[DB] Attempting to create table: orders");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS orders (
      id TEXT PRIMARY KEY,
      primarySalespersonId TEXT,
      primarySalespersonName TEXT,
      secondarySalespersonId TEXT,
      secondarySalespersonName TEXT,
      primarySalespersonCommission REAL,
      secondarySalespersonCommission REAL,
      items TEXT NOT NULL,
      subtotal REAL NOT NULL,
      discountAmount REAL DEFAULT 0,
      appliedDiscountPercentage REAL,
      appliedGlobalDiscountPercentage REAL,
      taxes TEXT,
      totalAmount REAL NOT NULL,
      status TEXT NOT NULL,
      deliveryStatus TEXT,
      customerName TEXT,
      customerPhone TEXT,
      deliveryAddress TEXT,
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      payments TEXT,
      storekeeperNotes TEXT,
      cashierNotes TEXT,
      reminderDate TEXT,
      reminderNotes TEXT,
      returnTransactions TEXT,
      linkedDemandNoticeId TEXT, 
      FOREIGN KEY (primarySalespersonId) REFERENCES users(id),
      FOREIGN KEY (secondarySalespersonId) REFERENCES users(id),
      FOREIGN KEY (linkedDemandNoticeId) REFERENCES demand_notices(id) ON DELETE SET NULL
    );
  `);
  console.log("[DB] Table 'orders' created or already exists.");

  console.log("[DB] Attempting to create table: attendance_logs");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS attendance_logs (
      id TEXT PRIMARY KEY,
      userId TEXT NOT NULL,
      timestamp TEXT NOT NULL,
      method TEXT,
      selfieDataUri TEXT,
      selfieImagePath TEXT, 
      FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB] Table 'attendance_logs' created or already exists.");
  if (!await columnExists(dbInstance, 'attendance_logs', 'method')) {
    console.log("[DB] Adding 'method' column to 'attendance_logs' table.");
    await dbInstance.exec('ALTER TABLE attendance_logs ADD COLUMN method TEXT;');
  }
  if (!await columnExists(dbInstance, 'attendance_logs', 'selfieImagePath')) {
    console.log("[DB] Adding 'selfieImagePath' column to 'attendance_logs' table.");
    await dbInstance.exec('ALTER TABLE attendance_logs ADD COLUMN selfieImagePath TEXT;');
  }


  console.log("[DB] Attempting to create table: break_logs");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS break_logs (
      id TEXT PRIMARY KEY,
      userId TEXT NOT NULL,
      startTime TEXT NOT NULL,
      endTime TEXT,
      durationMs INTEGER,
      FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB] Table 'break_logs' created or already exists.");

  console.log("[DB] Attempting to create table: demand_notices");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS demand_notices (
      id TEXT PRIMARY KEY,
      salespersonId TEXT NOT NULL,
      salespersonName TEXT NOT NULL,
      customerContactNumber TEXT NOT NULL,
      productId TEXT, 
      productName TEXT NOT NULL,
      productSku TEXT NOT NULL, 
      quantityRequested INTEGER NOT NULL,
      quantityFulfilled INTEGER DEFAULT 0,
      agreedPrice REAL NOT NULL, 
      expectedAvailabilityDate TEXT NOT NULL,
      status TEXT NOT NULL,
      isNewProduct INTEGER NOT NULL DEFAULT 0, 
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      notes TEXT,
      payments TEXT, 
      linkedOrderId TEXT,
      FOREIGN KEY (salespersonId) REFERENCES users(id),
      FOREIGN KEY (productId) REFERENCES products(id) ON DELETE SET NULL,
      FOREIGN KEY (linkedOrderId) REFERENCES orders(id) ON DELETE SET NULL
    );
  `);
  console.log("[DB] Table 'demand_notices' created or already exists.");

  console.log("[DB] Attempting to create table: tax_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS tax_settings (
      id TEXT PRIMARY KEY,
      name TEXT UNIQUE NOT NULL,
      rate REAL NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 0 
    );
  `);
  console.log("[DB] Table 'tax_settings' created or already exists.");
  
  console.log("[DB] Attempting to create table: global_discount_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS global_discount_settings (
      id TEXT PRIMARY KEY,
      percentage REAL NOT NULL,
      startDate TEXT,
      endDate TEXT,
      isActive INTEGER NOT NULL DEFAULT 0,
      description TEXT
    );
  `);
  console.log("[DB] Table 'global_discount_settings' created or already exists.");

  console.log("[DB] Attempting to create table: commission_settings");
   await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS commission_settings (
      id TEXT PRIMARY KEY,
      salesTarget REAL NOT NULL,
      commissionInterval REAL NOT NULL,
      commissionPercentage REAL NOT NULL,
      isActive INTEGER NOT NULL DEFAULT 0
    );
  `);
  console.log("[DB] Table 'commission_settings' created or already exists.");

  console.log("[DB] Checking/Creating/Migrating table: invoice_number_settings (for series numbering)");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS invoice_number_settings (
      id TEXT PRIMARY KEY, 
      nextNumber INTEGER NOT NULL 
    );
  `);
   
  const invoiceColumns = await dbInstance.all("PRAGMA table_info(invoice_number_settings);");
  const hasOldInvoiceNumberColumn = invoiceColumns.some(col => col.name === 'nextInvoiceNumber');
  const hasNewNextNumberColumn = invoiceColumns.some(col => col.name === 'nextNumber');

  if (hasOldInvoiceNumberColumn && !hasNewNextNumberColumn) {
      console.log("[DB] Migrating 'invoice_number_settings' table: renaming 'nextInvoiceNumber' to 'nextNumber'.");
      
      await dbInstance.exec('ALTER TABLE invoice_number_settings RENAME TO old_invoice_number_settings;');
      await dbInstance.exec(`
          CREATE TABLE invoice_number_settings (
            id TEXT PRIMARY KEY,
            nextNumber INTEGER NOT NULL
          );
      `);
      
      const oldInvoiceSetting = await dbInstance.get("SELECT nextInvoiceNumber FROM old_invoice_number_settings WHERE id = 'main_invoice_config'");
      if (oldInvoiceSetting && oldInvoiceSetting.nextInvoiceNumber) {
          await dbInstance.run("INSERT INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)", 'invoice', oldInvoiceSetting.nextInvoiceNumber);
      } else {
          await dbInstance.run("INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)", INITIAL_INVOICE_NUMBER_SETTING.id, INITIAL_INVOICE_NUMBER_SETTING.nextNumber);
      }
      await dbInstance.exec('DROP TABLE old_invoice_number_settings;');
      console.log("[DB] Migration of 'invoice_number_settings' complete.");
  } else if (!hasNewNextNumberColumn && !hasOldInvoiceNumberColumn) { 
    console.log("[DB] 'invoice_number_settings' table is fresh or was malformed. Seeding defaults for all series.");
    await dbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_INVOICE_NUMBER_SETTING.id, INITIAL_INVOICE_NUMBER_SETTING.nextNumber);
    await dbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_QUOTATION_NUMBER_SETTING.id, INITIAL_QUOTATION_NUMBER_SETTING.nextNumber);
    await dbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_DEMAND_NOTICE_NUMBER_SETTING.id, INITIAL_DEMAND_NOTICE_NUMBER_SETTING.nextNumber);
    await dbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', INITIAL_AUDIT_NUMBER_SETTING.id, INITIAL_AUDIT_NUMBER_SETTING.nextNumber);
  }
  console.log("[DB] Table 'invoice_number_settings' (for series numbering) successfully checked/created/migrated.");


  console.log("[DB] Attempting to create table: attendance_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS attendance_settings (
      id TEXT PRIMARY KEY, 
      mandatory_attendance_time TEXT, 
      is_mandatory_attendance_active INTEGER NOT NULL DEFAULT 0,
      max_concurrent_breaks INTEGER 
    );
  `);
  console.log("[DB] Table 'attendance_settings' created or already exists.");

  if (!await columnExists(dbInstance, 'attendance_settings', 'max_concurrent_breaks')) {
    console.log("[DB] Column 'max_concurrent_breaks' not detected by PRAGMA in 'attendance_settings'. Attempting to add it...");
    try {
      await dbInstance.exec('ALTER TABLE attendance_settings ADD COLUMN max_concurrent_breaks INTEGER;');
      console.log("[DB] Column 'max_concurrent_breaks' ADD command executed for 'attendance_settings'.");
    } catch (alterError: any) {
      if (alterError.message && alterError.message.toLowerCase().includes('duplicate column name')) {
        console.warn("[DB] 'max_concurrent_breaks' column likely already exists in 'attendance_settings' (SQLite quirk or race condition). Ignoring 'duplicate column' error.");
      } else {
        console.error("[DB] CRITICAL: Failed to add 'max_concurrent_breaks' column to 'attendance_settings' with non-duplicate error:", alterError.message);
        throw new Error(`Failed to migrate attendance_settings table (add max_concurrent_breaks): ${alterError.message}`);
      }
    }
  } else {
    console.log("[DB] Column 'max_concurrent_breaks' already exists in 'attendance_settings'.");
  }

  
  console.log("[DB] Attempting to create table: quotations");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS quotations (
      id TEXT PRIMARY KEY,
      salespersonId TEXT NOT NULL,
      customerName TEXT,
      customerPhone TEXT,
      customerEmail TEXT,
      customerAddress TEXT,
      preparationDays INTEGER NOT NULL,
      validUntil TEXT NOT NULL,
      status TEXT NOT NULL,
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      totalAmount REAL NOT NULL,
      notes TEXT,
      FOREIGN KEY (salespersonId) REFERENCES users(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB] Table 'quotations' created or already exists.");

  console.log("[DB] Attempting to create table: quotation_items");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS quotation_items (
      id TEXT PRIMARY KEY,
      quotationId TEXT NOT NULL,
      productId TEXT,
      productName TEXT NOT NULL,
      productSku TEXT,
      price REAL NOT NULL,
      quantity INTEGER NOT NULL,
      isExternal INTEGER NOT NULL DEFAULT 0,
      converted INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (quotationId) REFERENCES quotations(id) ON DELETE CASCADE,
      FOREIGN KEY (productId) REFERENCES products(id) ON DELETE SET NULL
    );
  `);
  console.log("[DB] Table 'quotation_items' created or already exists.");

  // New Audit Tables
  console.log("[DB SCRIPT] Attempting to create table: audits");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audits (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      adminId TEXT NOT NULL,
      auditorId TEXT, 
      storeLocation TEXT NOT NULL,
      status TEXT NOT NULL, -- 'pending', 'in_progress', 'completed', 'cancelled'
      startedAt TEXT,
      completedAt TEXT,
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      auditorSelfiePath TEXT,
      FOREIGN KEY (adminId) REFERENCES users(id),
      FOREIGN KEY (auditorId) REFERENCES users(id)
    );
  `);
  console.log("[DB SCRIPT] Table 'audits' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: audit_items");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audit_items (
      id TEXT PRIMARY KEY,
      auditId TEXT NOT NULL,
      productId TEXT,
      productName TEXT NOT NULL,
      productSku TEXT,
      currentStock INTEGER NOT NULL, -- System stock at audit launch
      finalAuditedQty INTEGER,      -- Final quantity after all counts (can be updated upon audit completion)
      notes TEXT,                   -- Overall notes for this item's audit (e.g., discrepancy reason)
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      FOREIGN KEY (auditId) REFERENCES audits(id) ON DELETE CASCADE,
      FOREIGN KEY (productId) REFERENCES products(id) ON DELETE SET NULL
    );
  `);
  console.log("[DB SCRIPT] Table 'audit_items' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: audit_item_counts");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audit_item_counts (
      id TEXT PRIMARY KEY,
      auditItemId TEXT NOT NULL,
      count INTEGER NOT NULL,
      notes TEXT,
      createdAt TEXT NOT NULL, -- Timestamp of this specific count event
      FOREIGN KEY (auditItemId) REFERENCES audit_items(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB SCRIPT] Table 'audit_item_counts' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: audit_images");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audit_images (
      id TEXT PRIMARY KEY,
      countEventId TEXT NOT NULL, -- Links to audit_item_counts
      imagePath TEXT NOT NULL,
      createdAt TEXT NOT NULL,
      FOREIGN KEY (countEventId) REFERENCES audit_item_counts(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB SCRIPT] Table 'audit_images' created or already exists.");

  // New Messaging Tables
  await dbInstance.exec(`
      CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY,
          subject TEXT NOT NULL,
          created_at TEXT NOT NULL,
          creator_id TEXT NOT NULL,
          FOREIGN KEY (creator_id) REFERENCES users(id)
      );
  `);

  await dbInstance.exec(`
      CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          conversation_id TEXT NOT NULL,
          sender_id TEXT NOT NULL,
          content TEXT NOT NULL,
          sent_at TEXT NOT NULL,
          FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
          FOREIGN KEY (sender_id) REFERENCES users(id)
      );
  `);

  await dbInstance.exec(`
      CREATE TABLE IF NOT EXISTS message_recipients (
          id TEXT PRIMARY KEY,
          message_id TEXT NOT NULL,
          recipient_id TEXT NOT NULL,
          recipient_type TEXT NOT NULL CHECK(recipient_type IN ('to', 'cc', 'bcc')),
          read_at TEXT,
          FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
          FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE
      );
  `);

  await dbInstance.exec(`
      CREATE TABLE IF NOT EXISTS attachments (
          id TEXT PRIMARY KEY,
          message_id TEXT NOT NULL,
          file_path TEXT NOT NULL,
          original_name TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
      );
  `);

  // New SCM Tables
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS suppliers (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      contact_email TEXT,
      phone TEXT,
      lead_time INTEGER,
      notes TEXT
    );
  `);
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS supplier_attachments (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        original_name TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        uploaded_by_id TEXT,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
        FOREIGN KEY (uploaded_by_id) REFERENCES users(id) ON DELETE SET NULL
    );
  `);
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS supplier_products (
      id TEXT PRIMARY KEY,
      supplier_id TEXT,
      product_id TEXT,
      unit_price REAL NOT NULL,
      document_path TEXT,
      FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
      FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    );
  `);
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS purchase_orders (
      id TEXT PRIMARY KEY,
      supplier_id TEXT,
      status TEXT NOT NULL,
      total_amount REAL,
      advance_paid REAL,
      deadline TEXT,
      expected_delivery TEXT,
      invoice_path TEXT,
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      transportationDetails TEXT,
      FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    );
  `);
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS po_items (
      id TEXT PRIMARY KEY,
      po_id TEXT,
      product_id TEXT,
      quantity_ordered INTEGER NOT NULL,
      quantity_received INTEGER,
      notes TEXT,
      updatedAt TEXT,
      FOREIGN KEY (po_id) REFERENCES purchase_orders(id) ON DELETE CASCADE,
      FOREIGN KEY (product_id) REFERENCES products(id)
    );
  `);
  
  if (!await columnExists(dbInstance, 'po_items', 'updatedAt')) {
    console.log("[DB MIGRATION] Adding 'updatedAt' column to 'po_items' table.");
    await dbInstance.exec('ALTER TABLE po_items ADD COLUMN updatedAt TEXT;');
  }
   if (!await columnExists(dbInstance, 'po_items', 'notes')) {
    console.log("[DB MIGRATION] Adding 'notes' column to 'po_items' table.");
    await dbInstance.exec('ALTER TABLE po_items ADD COLUMN notes TEXT;');
  }

  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS po_attachments (
      id TEXT PRIMARY KEY,
      po_id TEXT NOT NULL,
      file_path TEXT NOT NULL,
      original_name TEXT NOT NULL,
      notes TEXT,
      uploaded_at TEXT NOT NULL,
      uploaded_by_id TEXT,
      type TEXT, -- This will store 'grn', 'storage_evidence', 'other'
      FOREIGN KEY (po_id) REFERENCES purchase_orders(id) ON DELETE CASCADE,
      FOREIGN KEY (uploaded_by_id) REFERENCES users(id) ON DELETE SET NULL
    );
  `);
}

async function seedInitialData(dbInstance: Database): Promise<void> {
  console.log("[DB] Seeding INITIAL_PRODUCTS...");
  for (const product of INITIAL_PRODUCTS) {
    await dbInstance.run(
      'INSERT OR IGNORE INTO products (id, name, price, quantityInStock, sku, expiryDate, imageUrl, category, isDemandNoticeProduct, lowStockThreshold, lowStockPrice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [
        product.id,
        product.name,
        product.price,
        product.quantityInStock,
        product.sku,
        product.expiryDate,
        product.imageUrl,
        product.category,
        product.isDemandNoticeProduct ? 1 : 0,
        product.lowStockThreshold,
        product.lowStockPrice
      ]
    );
  }
  console.log("[DB] INITIAL_PRODUCTS seeded.");

  await ensureInitialUsers(dbInstance);
  
  console.log("[DB] Seeding INITIAL_ORDERS...");
  for (const order of INITIAL_ORDERS) {
     await dbInstance.run(
      `INSERT OR IGNORE INTO orders (
        id, primarySalespersonId, primarySalespersonName, primarySalespersonCommission, items, subtotal, discountAmount, 
        appliedDiscountPercentage, taxes, totalAmount, status, deliveryStatus, customerName, customerPhone, deliveryAddress, 
        createdAt, updatedAt, payments, returnTransactions, linkedDemandNoticeId
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        order.id,
        order.primarySalespersonId,
        order.primarySalespersonName,
        order.primarySalespersonCommission,
        JSON.stringify(order.items),
        order.subtotal,
        order.discountAmount,
        order.appliedDiscountPercentage,
        JSON.stringify(order.taxes),
        order.totalAmount,
        order.status,
        order.deliveryStatus,
        order.customerName,
        order.customerPhone,
        order.deliveryAddress,
        order.createdAt,
        order.updatedAt,
        JSON.stringify(order.payments || []),
        JSON.stringify(order.returnTransactions || []),
        order.linkedDemandNoticeId
      ]
    );
  }
  console.log("[DB] INITIAL_ORDERS seeded.");

  console.log('[DB] Seeding initial demand notices...');
    if (INITIAL_DEMAND_NOTICES.length > 0) {
        for (const notice of INITIAL_DEMAND_NOTICES) {
            const productNamePart = (notice.productName || 'PROD').substring(0, 5).toUpperCase();
            const phonePart = (notice.customerContactNumber?.toString() || '000').slice(-3);
            const datePart = format(new Date(notice.expectedAvailabilityDate || Date.now()), "ddMMyy");
            const productSku = notice.productSku || 'DN-' + productNamePart + '-' + phonePart + '-' + datePart;
            
            await dbInstance.run(
                `INSERT OR IGNORE INTO demand_notices (
                    id, salespersonId, salespersonName, customerContactNumber, productId, productName, productSku,
                    quantityRequested, quantityFulfilled, agreedPrice, expectedAvailabilityDate, status, isNewProduct, 
                    createdAt, updatedAt, notes, payments, linkedOrderId
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                [
                    notice.id, notice.salespersonId, notice.salespersonName, notice.customerContactNumber.toString(),
                    notice.productId, notice.productName, productSku, notice.quantityRequested,
                    notice.quantityFulfilled || 0, notice.agreedPrice, new Date(notice.expectedAvailabilityDate || new Date()).toISOString(),
                    notice.status, notice.isNewProduct ? 1 : 0, notice.createdAt, notice.updatedAt,
                    notice.notes, JSON.stringify(notice.payments || []), notice.linkedOrderId
                ]
            );
        }
        console.log('[DB] Initial demand notices seeded.');
    } else {
        console.log('[DB] No initial demand notices to seed.');
    }
  
  console.log("[DB] Seeding initial tax settings...");
  if (INITIAL_TAX_SETTINGS.length > 0) {
    for (const setting of INITIAL_TAX_SETTINGS) {
      await dbInstance.run('INSERT OR IGNORE INTO tax_settings (id, name, rate, enabled) VALUES (?, ?, ?, ?)', 
        [
          setting.id,
          setting.name,
          setting.rate,
          setting.enabled ? 1 : 0
        ]
      );
    }
    console.log("[DB] Initial tax settings seeded.");
  } else {
    console.log("[DB] No initial tax settings to seed.");
  }

  if (INITIAL_GLOBAL_DISCOUNT_SETTING) {
      console.log('[DB] Seeding initial global discount setting...');
      const gds = INITIAL_GLOBAL_DISCOUNT_SETTING;
      await dbInstance.run(`INSERT OR IGNORE INTO global_discount_settings 
        (id, percentage, startDate, endDate, isActive, description) 
        VALUES (?, ?, ?, ?, ?, ?)`, 
        [
          gds.id,
          gds.percentage,
          gds.startDate,
          gds.endDate,
          gds.isActive ? 1 : 0,
          gds.description
        ]
      );
      console.log('[DB] Initial global discount setting seeded.');
  }

  if (INITIAL_COMMISSION_SETTING) {
      console.log('[DB] Seeding initial commission setting...');
      const cs = INITIAL_COMMISSION_SETTING;
      await dbInstance.run(`INSERT OR IGNORE INTO commission_settings 
        (id, salesTarget, commissionInterval, commissionPercentage, isActive) 
        VALUES (?, ?, ?, ?, ?)`, 
        [
          cs.id,
          cs.salesTarget,
          cs.commissionInterval,
          cs.commissionPercentage,
          cs.isActive ? 1 : 0
        ]
      );
      console.log('[DB] Initial commission setting seeded.');
  }

  console.log('[DB SCRIPT] Seeding initial series number settings (invoice, quotation, demand_notice, audit)...');
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_INVOICE_NUMBER_SETTING.id, INITIAL_INVOICE_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_QUOTATION_NUMBER_SETTING.id, INITIAL_QUOTATION_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_DEMAND_NOTICE_NUMBER_SETTING.id, INITIAL_DEMAND_NOTICE_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_AUDIT_NUMBER_SETTING.id, INITIAL_AUDIT_NUMBER_SETTING.nextNumber);
  console.log('[DB SCRIPT] Initial series number settings seeded.');


  if (INITIAL_ATTENDANCE_SETTING) {
    console.log('[DB SCRIPT] Seeding initial attendance setting...');
    const as = INITIAL_ATTENDANCE_SETTING;
    await dbInstance.run(`INSERT OR IGNORE INTO attendance_settings
      (id, mandatory_attendance_time, is_mandatory_attendance_active, max_concurrent_breaks)
      VALUES (?, ?, ?, ?)`,
      [
        as.id,
        as.mandatory_attendance_time,
        as.is_mandatory_attendance_active ? 1 : 0,
        as.max_concurrent_breaks
      ]
    );
    console.log('[DB SCRIPT] Initial attendance setting seeded.');
  }

  console.log('[DB SCRIPT] All initial data seeding complete.');
}

function safeParseJSONArray(jsonString: string | null | undefined, fieldName: string, entityId?: string): any[] {
  if (typeof jsonString === 'string' && jsonString.trim() !== "") {
    try {
      const parsed = JSON.parse(jsonString);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.error(`[DB] Failed to parse JSON field '${fieldName}' for entity ${entityId || 'unknown'}: Value='${jsonString}'. Error:`, e);
      return []; 
    }
  }
  return []; 
}

export function parseUserJSONFields(user: any): User {
  return {
    ...user,
    permissions: safeParseJSONArray(user.permissions, 'permissions', user.id),
    autoEnterAfterScan: user.auto_enter_after_scan === 0 ? false : true,
  };
}

export function parseOrderJSONFields(order: any): Order {
  return {
    ...order,
    items: safeParseJSONArray(order.items, 'items', order.id),
    taxes: safeParseJSONArray(order.taxes, 'taxes', order.id),
    payments: safeParseJSONArray(order.payments, 'payments', order.id),
    returnTransactions: safeParseJSONArray(order.returnTransactions, 'returnTransactions', order.id),
  };
}


export function parseDemandNoticeJSONFields(notice: any): DemandNotice {
  return {
    ...notice,
    payments: safeParseJSONArray(notice.payments, 'payments', notice.id),
    isNewProduct: Boolean(notice.isNewProduct),
    expectedAvailabilityDate: (typeof notice.expectedAvailabilityDate === 'string' && isValid(parseISO(notice.expectedAvailabilityDate))) 
                              ? parseISO(notice.expectedAvailabilityDate).toISOString() 
                              : (notice.expectedAvailabilityDate instanceof Date && isValid(notice.expectedAvailabilityDate))
                                ? notice.expectedAvailabilityDate.toISOString()
                                : new Date().toISOString(), 
    createdAt: (typeof notice.createdAt === 'string' && isValid(parseISO(notice.createdAt))) 
               ? parseISO(notice.createdAt).toISOString() 
               : (notice.createdAt instanceof Date && isValid(notice.createdAt))
                 ? notice.createdAt.toISOString()
                 : new Date().toISOString(),
    updatedAt: (typeof notice.updatedAt === 'string' && isValid(parseISO(notice.updatedAt))) 
               ? parseISO(notice.updatedAt).toISOString() 
               : (notice.updatedAt instanceof Date && isValid(notice.updatedAt))
                 ? notice.updatedAt.toISOString()
                 : new Date().toISOString(),
  };
}


export function parseQuotationJSONFields(quotation: any): Quotation {
  return {
    ...quotation,
  };
}


export function parseQuotationItemJSONFields(item: any): QuotationItem {
  return {
    ...item,
    isExternal: Boolean(item.isExternal),
    converted: Boolean(item.converted),
  };
}


export function parseBooleanFields<T extends Record<string, any>>(
  obj: T,
  fields: (keyof T)[]
): T {
  const newObj = { ...obj };
  fields.forEach(field => {
    if (newObj[field] !== undefined && newObj[field] !== null) {
      (newObj as Record<keyof T, boolean>)[field] = Boolean(newObj[field]);
    }
  });
  return newObj;
}


export function parseAttendanceSettingJSONFields(setting: any): AttendanceSetting {
  return {
    ...setting,
    is_mandatory_attendance_active: Boolean(setting.is_mandatory_attendance_active),
    max_concurrent_breaks: setting.max_concurrent_breaks === null || setting.max_concurrent_breaks === undefined ? null : Number(setting.max_concurrent_breaks),
  };
}


export async function getNextSeriesNumber(seriesId: SeriesId, dbInstance: Database): Promise<string> {
  const setting = await dbInstance.get<SeriesNumberSetting>('SELECT * FROM invoice_number_settings WHERE id = ?', seriesId);
  
  let currentNumber = 1;
  if (setting) {
    currentNumber = setting.nextNumber;
  } else {
    
    await dbInstance.run('INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)', seriesId, 1);
  }

  let prefix = '';
  switch(seriesId) {
    case 'invoice': prefix = 'INV-'; break;
    case 'quotation': prefix = 'QUO-'; break;
    case 'demand_notice': prefix = 'DN-'; break;
    case 'audit': prefix = 'AUD-'; break; 
    case 'po': prefix = 'PO-'; break;
    default: prefix = 'DOC-';
  }
  
  const formattedNumber = String(currentNumber).padStart(6, '0');
  const newSeriesFullId = `${prefix}${formattedNumber}`;

  
  let checkTable = '';
  if (seriesId === 'invoice') checkTable = 'orders';
  else if (seriesId === 'quotation') checkTable = 'quotations';
  else if (seriesId === 'demand_notice') checkTable = 'demand_notices';
  else if (seriesId === 'audit') checkTable = 'audits';
  else if (seriesId === 'po') checkTable = 'purchase_orders';


  if (checkTable) {
    const existingDoc = await dbInstance.get(`SELECT id FROM ${checkTable} WHERE id = ?`, newSeriesFullId);
    if (existingDoc) {
      
      await dbInstance.run('UPDATE invoice_number_settings SET nextNumber = ? WHERE id = ?', currentNumber + 1, seriesId);
      return getNextSeriesNumber(seriesId, dbInstance); 
    }
  }
  
  await dbInstance.run('UPDATE invoice_number_settings SET nextNumber = ? WHERE id = ?', currentNumber + 1, seriesId);
  return newSeriesFullId;
}

// New parsing functions for Audit feature
export function parseAuditJSONFields(audit: any): Audit {
  let itemsArray: AuditItem[] = [];
  if (typeof audit.items === 'string') {
    itemsArray = safeParseJSONArray(audit.items, 'items', audit.id).map(item => parseAuditItemJSONFields(item));
  } else if (Array.isArray(audit.items)) {
    itemsArray = audit.items.map(item => parseAuditItemJSONFields(item));
  }
  return {
    ...audit,
    items: itemsArray
  };
}

export function parseAuditItemJSONFields(item: any): AuditItem {
  let countsArray: AuditItemCount[] = [];
  if (typeof item.counts === 'string') {
    countsArray = safeParseJSONArray(item.counts, 'counts', item.id).map(count => parseAuditItemCountJSONFields(count));
  } else if (Array.isArray(item.counts)) {
    countsArray = item.counts.map(count => parseAuditItemCountJSONFields(count));
  }
  return {
    ...item,
    counts: countsArray
  };
}

export function parseAuditItemCountJSONFields(count: any): AuditItemCount {
  let imagesArray: AuditImage[] = [];
   if (typeof count.images === 'string') {
    imagesArray = safeParseJSONArray(count.images, 'images', count.id).map(image => parseAuditImageJSONFields(image));
  } else if (Array.isArray(count.images)) {
    // If images come as an array of objects directly from DB join
    imagesArray = count.images.map(image => parseAuditImageJSONFields(image));
  }
  return {
    ...count,
    images: imagesArray
  };
}

export function parseAuditImageJSONFields(image: any): AuditImage {
  return image; 
}
    
export function parseProductJSONFields(product: any): Product { 
  return {
    ...product,
    isDemandNoticeProduct: Boolean(product.isDemandNoticeProduct),
  };
}

// SCM Parsing functions
export function parseSupplierJSONFields(supplier: any): Supplier {
  return supplier; // No JSON fields to parse currently
}

export function parsePOItemJSONFields(poItem: any): POItem {
    return poItem;
}

export function parsePurchaseOrderJSONFields(po: any): PurchaseOrder {
  let transportationDetails = null;
  if (po && typeof po.transportationDetails === 'string') {
    try {
      transportationDetails = JSON.parse(po.transportationDetails);
    } catch (e) {
      console.error(`[DB] Failed to parse transportationDetails for PO ${po.id}:`, e);
      transportationDetails = { notes: `Invalid JSON in DB: ${po.transportationDetails}` };
    }
  } else if (po && typeof po.transportationDetails === 'object') {
    transportationDetails = po.transportationDetails;
  }

  return {
    ...po,
    transportationDetails: transportationDetails,
    items: [],
    attachments: [],
  };
}
