

import sqlite3 from 'sqlite3';
import { open, type Database } from 'sqlite';
import path from 'path';
import fs from 'fs';
import { format } from 'date-fns'; 
import {
  INITIAL_PRODUCTS,
  INITIAL_USERS,
  INITIAL_ORDERS,
  INITIAL_DEMAND_NOTICES,
  INITIAL_TAX_SETTINGS,
  INITIAL_GLOBAL_DISCOUNT_SETTING,
  INITIAL_COMMISSION_SETTING,
  INITIAL_INVOICE_NUMBER_SETTING,
  INITIAL_QUOTATION_NUMBER_SETTING,
  INITIAL_DEMAND_NOTICE_NUMBER_SETTING,
  INITIAL_ATTENDANCE_SETTING,
  INITIAL_AUDIT_NUMBER_SETTING, // New import
} from '../src/lib/constants';

const DB_FILE_NAME = 'netpos.db';
const DB_PATH = path.join(process.cwd(), DB_FILE_NAME);

async function columnExists(dbInstance: Database, tableName: string, columnName: string): Promise<boolean> {
  const columns = await dbInstance.all(`PRAGMA table_info(${tableName});`);
  return columns.some(col => col.name === columnName);
}


async function initializeSchema(dbInstance: Database): Promise<void> {
  console.log("[DB SCRIPT] Attempting to create table: products");
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
  console.log("[DB SCRIPT] Table 'products' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: users");
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
  console.log("[DB SCRIPT] Table 'users' created or already exists.");
  if (!await columnExists(dbInstance, 'users', 'auto_enter_after_scan')) {
    console.log("[DB SCRIPT] MIGRATION: Adding 'auto_enter_after_scan' column to 'users' table.");
    await dbInstance.exec('ALTER TABLE users ADD COLUMN auto_enter_after_scan BOOLEAN DEFAULT 1;');
  }

  console.log("[DB SCRIPT] Attempting to create table: orders");
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
  console.log("[DB SCRIPT] Table 'orders' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: attendance_logs");
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
  console.log("[DB SCRIPT] Table 'attendance_logs' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: break_logs");
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
  console.log("[DB SCRIPT] Table 'break_logs' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: demand_notices");
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
  console.log("[DB SCRIPT] Table 'demand_notices' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: tax_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS tax_settings (
      id TEXT PRIMARY KEY,
      name TEXT UNIQUE NOT NULL,
      rate REAL NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 0 
    );
  `);
  console.log("[DB SCRIPT] Table 'tax_settings' created or already exists.");
  
  console.log("[DB SCRIPT] Attempting to create table: global_discount_settings");
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
  console.log("[DB SCRIPT] Table 'global_discount_settings' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: commission_settings");
   await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS commission_settings (
      id TEXT PRIMARY KEY,
      salesTarget REAL NOT NULL,
      commissionInterval REAL NOT NULL,
      commissionPercentage REAL NOT NULL,
      isActive INTEGER NOT NULL DEFAULT 0
    );
  `);
  console.log("[DB SCRIPT] Table 'commission_settings' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: invoice_number_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS invoice_number_settings (
      id TEXT PRIMARY KEY, 
      nextNumber INTEGER NOT NULL
    );
  `);
  console.log("[DB SCRIPT] Table 'invoice_number_settings' (for series numbering) created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: attendance_settings");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS attendance_settings (
      id TEXT PRIMARY KEY, 
      mandatory_attendance_time TEXT, 
      is_mandatory_attendance_active INTEGER NOT NULL DEFAULT 0,
      max_concurrent_breaks INTEGER 
    );
  `);
  console.log("[DB SCRIPT] Table 'attendance_settings' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: quotations");
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
  console.log("[DB SCRIPT] Table 'quotations' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: quotation_items");
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
  console.log("[DB SCRIPT] Table 'quotation_items' created or already exists.");

  // New Audit Tables
  console.log("[DB SCRIPT] Attempting to create table: audits");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audits (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      adminId TEXT NOT NULL,
      auditorId TEXT, 
      storeLocation TEXT NOT NULL,
      status TEXT NOT NULL,
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
      currentStock INTEGER NOT NULL,
      finalAuditedQty INTEGER, 
      notes TEXT,
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
      createdAt TEXT NOT NULL,
      FOREIGN KEY (auditItemId) REFERENCES audit_items(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB SCRIPT] Table 'audit_item_counts' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: audit_images");
  await dbInstance.exec(`
    CREATE TABLE IF NOT EXISTS audit_images (
      id TEXT PRIMARY KEY,
      countEventId TEXT NOT NULL,
      imagePath TEXT NOT NULL,
      createdAt TEXT NOT NULL,
      FOREIGN KEY (countEventId) REFERENCES audit_item_counts(id) ON DELETE CASCADE
    );
  `);
  console.log("[DB SCRIPT] Table 'audit_images' created or already exists.");

  // New Messaging Tables
  console.log("[DB SCRIPT] Attempting to create table: conversations");
  await dbInstance.exec(`
      CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY,
          subject TEXT NOT NULL,
          created_at TEXT NOT NULL,
          creator_id TEXT NOT NULL,
          FOREIGN KEY (creator_id) REFERENCES users(id)
      );
  `);
  console.log("[DB SCRIPT] Table 'conversations' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: messages");
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
  console.log("[DB SCRIPT] Table 'messages' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: message_recipients");
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
  console.log("[DB SCRIPT] Table 'message_recipients' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: attachments");
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
  console.log("[DB SCRIPT] Table 'attachments' created or already exists.");

  // New SCM Tables
  console.log("[DB SCRIPT] Attempting to create table: suppliers");
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
  console.log("[DB SCRIPT] Table 'suppliers' created or already exists.");
  
  console.log("[DB SCRIPT] Attempting to create table: supplier_attachments");
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
  console.log("[DB SCRIPT] Table 'supplier_attachments' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: supplier_products");
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
  console.log("[DB SCRIPT] Table 'supplier_products' created or already exists.");

  console.log("[DB SCRIPT] Attempting to create table: purchase_orders");
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
      transportationDetails TEXT,
      createdAt TEXT NOT NULL,
      updatedAt TEXT NOT NULL,
      FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    );
  `);
  console.log("[DB SCRIPT] Table 'purchase_orders' created or already exists.");
  if (!await columnExists(dbInstance, 'purchase_orders', 'transportationDetails')) {
    console.log("[DB SCRIPT] MIGRATION: Adding 'transportationDetails' column to 'purchase_orders' table.");
    await dbInstance.exec('ALTER TABLE purchase_orders ADD COLUMN transportationDetails TEXT;');
  }

  console.log("[DB SCRIPT] Attempting to create table: po_items");
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
  console.log("[DB SCRIPT] Table 'po_items' created or already exists.");
  if (!await columnExists(dbInstance, 'po_items', 'updatedAt')) {
    console.log("[DB SCRIPT] MIGRATION: Adding 'updatedAt' column to 'po_items' table.");
    await dbInstance.exec('ALTER TABLE po_items ADD COLUMN updatedAt TEXT;');
  }

  console.log("[DB SCRIPT] Attempting to create table: po_attachments");
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
  console.log("[DB SCRIPT] Table 'po_attachments' created or already exists.");

}

async function ensureInitialUsers(dbInstance: Database): Promise<void> {
  console.log('[DB SCRIPT] Ensuring initial users are present...');
  for (const user of INITIAL_USERS) {
    await dbInstance.run(
      'INSERT OR IGNORE INTO users (id, username, password, role, permissions, activeBreakId, auto_enter_after_scan) VALUES (?, ?, ?, ?, ?, ?, ?)',
      [
        user.id,
        user.username,
        user.password,
        user.role,
        JSON.stringify(user.permissions || []),
        user.activeBreakId,
        user.autoEnterAfterScan === false ? 0 : 1 // Handle boolean to integer conversion
      ]
    );
  }
  console.log('[DB SCRIPT] Initial users check complete.');
}

async function seedInitialData(dbInstance: Database): Promise<void> {
  console.log("[DB SCRIPT] Seeding INITIAL_PRODUCTS...");
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
  console.log("[DB SCRIPT] INITIAL_PRODUCTS seeded.");

  await ensureInitialUsers(dbInstance);
  
  console.log("[DB SCRIPT] Seeding INITIAL_ORDERS...");
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
  console.log("[DB SCRIPT] INITIAL_ORDERS seeded.");

  console.log('[DB SCRIPT] Seeding initial demand notices...');
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
    console.log('[DB SCRIPT] Initial demand notices seeded.');
  } else {
      console.log('[DB SCRIPT] No initial demand notices to seed.');
  }
  
  console.log("[DB SCRIPT] Seeding initial tax settings...");
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
    console.log("[DB SCRIPT] Initial tax settings seeded.");
  } else {
    console.log("[DB SCRIPT] No initial tax settings to seed.");
  }

  if (INITIAL_GLOBAL_DISCOUNT_SETTING) {
      console.log('[DB SCRIPT] Seeding initial global discount setting...');
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
      console.log('[DB SCRIPT] Initial global discount setting seeded.');
  }

  if (INITIAL_COMMISSION_SETTING) {
      console.log('[DB SCRIPT] Seeding initial commission setting...');
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
      console.log('[DB SCRIPT] Initial commission setting seeded.');
  }

  console.log('[DB SCRIPT] Seeding initial series number settings (invoice, quotation, demand_notice, audit)...');
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_INVOICE_NUMBER_SETTING.id, INITIAL_INVOICE_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_QUOTATION_NUMBER_SETTING.id, INITIAL_QUOTATION_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_DEMAND_NOTICE_NUMBER_SETTING.id, INITIAL_DEMAND_NOTICE_NUMBER_SETTING.nextNumber);
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    INITIAL_AUDIT_NUMBER_SETTING.id, INITIAL_AUDIT_NUMBER_SETTING.nextNumber); // Seed audit series
  await dbInstance.run(`INSERT OR IGNORE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)`, 
    'po', 1); // Seed PO series
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

  console.log("[DB SCRIPT] Seeding initial messages...");
  try {
    await dbInstance.run('BEGIN TRANSACTION');
    let messageCounter = 1;
    for (const sender of INITIAL_USERS) {
      // Don't send messages from the system user
      if (sender.id === 'user_system') continue;
      
      for (const recipient of INITIAL_USERS) {
        if (sender.id === recipient.id || recipient.id === 'user_system') continue;

        const conversationId = `conv_${sender.id.slice(-4)}_${recipient.id.slice(-4)}_${messageCounter}`;
        const messageId = `msg_${sender.id.slice(-4)}_${recipient.id.slice(-4)}_${messageCounter}`;
        const recipientEntryId = `rcpt_${sender.id.slice(-4)}_${recipient.id.slice(-4)}_${messageCounter}`;
        const now = new Date().toISOString();

        await dbInstance.run(
          `INSERT OR IGNORE INTO conversations (id, subject, created_at, creator_id) VALUES (?, ?, ?, ?)`,
          [conversationId, `Test message from ${sender.username} to ${recipient.username}`, now, sender.id]
        );

        await dbInstance.run(
          `INSERT OR IGNORE INTO messages (id, conversation_id, sender_id, content, sent_at) VALUES (?, ?, ?, ?, ?)`,
          [messageId, conversationId, sender.id, `Hello ${recipient.username}, this is a test message.`, now]
        );

        await dbInstance.run(
          `INSERT OR IGNORE INTO message_recipients (id, message_id, recipient_id, recipient_type, read_at) VALUES (?, ?, ?, ?, ?)`,
          [recipientEntryId, messageId, recipient.id, 'to', null]
        );

        messageCounter++;
      }
    }
    await dbInstance.run('COMMIT');
    console.log("[DB SCRIPT] Initial messages seeded successfully.");
  } catch (err) {
    console.error('[DB SCRIPT] Error during message seeding transaction, rolling back.', err);
    await dbInstance.run('ROLLBACK');
    throw err; // Re-throw the error to be caught by the main try-catch block
  }

  console.log('[DB SCRIPT] All initial data seeding complete.');
}

async function main() {
  console.log(`[DB SCRIPT] Checking for database file at: ${DB_PATH}`);
  let scriptDbInstance: Database | null = null;
  const dbExists = fs.existsSync(DB_PATH);

  try {
    scriptDbInstance = await open({
      filename: DB_PATH,
      driver: sqlite3.Database,
    });
    console.log('[DB SCRIPT] Database connection opened.');
    
    // Always run schema initialization to apply migrations to existing DBs
    await initializeSchema(scriptDbInstance);
    console.log('[DB SCRIPT] Schema initialization complete (tables created if they did not exist).');

    if (!dbExists) {
      console.log(`[DB SCRIPT] New database file created. Seeding initial data...`);
      await seedInitialData(scriptDbInstance);
      console.log(`[DB SCRIPT] Database "${DB_FILE_NAME}" created and seeded successfully at "${DB_PATH}".`);
    } else {
       console.log(`[DB SCRIPT] Existing database file found. Ensuring initial users are present...`);
       await ensureInitialUsers(scriptDbInstance);
       console.log(`[DB SCRIPT] Initial user check complete for existing database.`);
    }

  } catch (error) {
    console.error('[DB SCRIPT] Error during database script execution:', error);
    if (!dbExists && fs.existsSync(DB_PATH)) {
      try {
        fs.unlinkSync(DB_PATH);
        console.log(`[DB SCRIPT] Cleaned up partially created database file "${DB_PATH}".`);
      } catch (unlinkError) {
        console.error(`[DB SCRIPT] Error cleaning up database file "${DB_PATH}":`, unlinkError);
      }
    }
  } finally {
    if (scriptDbInstance) {
      await scriptDbInstance.close();
      console.log('[DB SCRIPT] Database connection closed.');
    }
  }
}

main().catch(err => {
  console.error("[DB SCRIPT] Critical error in main execution:", err);
  process.exit(1); 
});

