-- ============================================================
-- GYRO PULSE – COMPLETE DATABASE SCHEMA
-- Version: 4.0 (Offline-First, Token-Based Security)
-- Updated: Added device API keys, token pools, media management,
--          device commands, and stock visibility toggle.
-- ============================================================

-- ========================
-- ROLE API KEYS (legacy)
-- ========================
CREATE TABLE IF NOT EXISTS role_api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role VARCHAR(20) UNIQUE NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
);

-- ========================
-- SYSTEM SETTINGS (legacy)
-- ========================
CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
);

-- ========================
-- SERVER CONFIGURATION (NEW)
-- ========================
CREATE TABLE IF NOT EXISTS server_config (
    `key` VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
);

-- ========================
-- CITY (with is_active)
-- ========================
CREATE TABLE IF NOT EXISTS cities (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    created_at  DATETIME DEFAULT NOW(),
    is_active   BOOLEAN DEFAULT TRUE
);

-- ========================
-- USERS
-- ========================
CREATE TABLE IF NOT EXISTS users (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    username              VARCHAR(80) UNIQUE NOT NULL,
    password_hash         VARCHAR(200) NOT NULL,
    role                  VARCHAR(20) NOT NULL,
    city_id               INT,
    created_by            INT,
    created_at            DATETIME DEFAULT NOW(),
    is_active             BOOLEAN DEFAULT TRUE,
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    last_sync_at          DATETIME NULL,
    show_stock_quantity   BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- ========================
-- USER SYNC STATUS
-- ========================
CREATE TABLE IF NOT EXISTS user_sync_status (
    user_id                 INT PRIMARY KEY,
    last_message_timestamp  DATETIME,
    upload_required         BOOLEAN DEFAULT FALSE,
    updated_at              DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ========================
-- MESSAGES
-- ========================
CREATE TABLE IF NOT EXISTS messages (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    sender_id     INT,
    receiver_id   INT,
    type          VARCHAR(20) NOT NULL,
    content       TEXT,
    media_url     VARCHAR(255),
    latitude      DECIMAL(10,7),
    longitude     DECIMAL(10,7),
    created_at    DATETIME DEFAULT NOW(),
    device_id     VARCHAR(50),
    `read`        BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id),
    FOREIGN KEY (receiver_id) REFERENCES users(id)
);

-- ========================
-- PRODUCTS
-- ========================
CREATE TABLE IF NOT EXISTS products (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    name                  VARCHAR(200) NOT NULL,
    sku                   VARCHAR(100) UNIQUE,
    barcode               VARCHAR(100) UNIQUE,
    description           TEXT,
    unit_price            DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    tax_rate              DECIMAL(5,2) DEFAULT 0.00,
    current_warehouse_qty INT DEFAULT 0,
    reserved_warehouse_qty INT DEFAULT 0,
    category              VARCHAR(100),
    image_url             VARCHAR(255),
    is_active             BOOLEAN DEFAULT TRUE,
    city_id               INT NOT NULL,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
);

-- ========================
-- WAREHOUSE
-- ========================
CREATE TABLE IF NOT EXISTS warehouses (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    code        VARCHAR(20) UNIQUE NOT NULL,
    city_id     INT NOT NULL,
    address     TEXT,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT NOW(),
    updated_at  DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
);

-- ========================
-- INVENTORY
-- ========================
CREATE TABLE IF NOT EXISTS inventory (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    product_id    INT NOT NULL,
    warehouse_id  INT NOT NULL,
    current_qty   INT DEFAULT 0,
    reserved_qty  INT DEFAULT 0,
    updated_at    DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE,
    UNIQUE KEY uix_product_warehouse (product_id, warehouse_id)
);

-- ========================
-- CUSTOMERS
-- ========================
CREATE TABLE IF NOT EXISTS customers (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    name                  VARCHAR(200) NOT NULL,
    phone                 VARCHAR(20) UNIQUE NOT NULL,
    email                 VARCHAR(100),
    billing_address       TEXT,
    shipping_address      TEXT,
    credit_limit          DECIMAL(12,2) DEFAULT 0.00,
    outstanding_balance   DECIMAL(12,2) DEFAULT 0.00,
    city_id               INT NOT NULL,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    is_active             BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
);

-- ========================
-- AGENT INVENTORY
-- ========================
CREATE TABLE IF NOT EXISTS agent_inventory (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    user_id               INT NOT NULL,
    product_id            INT NOT NULL,
    current_physical_qty  INT DEFAULT 0,
    reserved_qty          INT DEFAULT 0,
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE KEY unique_agent_product (user_id, product_id)
);

-- ========================
-- ORDERS
-- ========================
CREATE TABLE IF NOT EXISTS orders (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    customer_id           INT,
    customer_name         VARCHAR(200),
    customer_phone        VARCHAR(20),
    shipping_address      TEXT,
    latitude              DECIMAL(10,7),
    longitude             DECIMAL(10,7),
    city_id               INT NOT NULL,
    warehouse_id          INT NULL,
    sales_person_id       INT NOT NULL,
    captain_id            INT,
    store_keeper_id       INT,
    delivery_agent_id     INT,
    order_date            DATETIME DEFAULT NOW(),
    status                VARCHAR(50) DEFAULT 'pending',
    subtotal              DECIMAL(12,2) DEFAULT 0.00,
    tax_amount            DECIMAL(12,2) DEFAULT 0.00,
    discount              DECIMAL(12,2) DEFAULT 0.00,
    net_total             DECIMAL(12,2) DEFAULT 0.00,
    paid_amount           DECIMAL(12,2) DEFAULT 0.00,
    remaining_balance     DECIMAL(12,2) DEFAULT 0.00,
    payment_terms         VARCHAR(100),
    special_instructions  TEXT,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    picked_at             DATETIME NULL,
    packed_at             DATETIME NULL,
    package_barcode       VARCHAR(100) NULL,
    package_qr            VARCHAR(255) NULL,
    storekeeper_confirmed_at DATETIME NULL,
    delivery_confirmed_at    DATETIME NULL,
    dispatched_at          DATETIME NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL,
    FOREIGN KEY (sales_person_id) REFERENCES users(id),
    FOREIGN KEY (captain_id) REFERENCES users(id),
    FOREIGN KEY (store_keeper_id) REFERENCES users(id),
    FOREIGN KEY (delivery_agent_id) REFERENCES users(id)
);

-- ========================
-- ORDER ITEMS
-- ========================
CREATE TABLE IF NOT EXISTS order_items (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT NOT NULL,
    product_id            INT NOT NULL,
    product_name          VARCHAR(200),
    product_barcode       VARCHAR(100),
    unit_price            DECIMAL(12,2) DEFAULT 0.00,
    ordered_qty           INT DEFAULT 0,
    picked_qty            INT DEFAULT 0,
    delivered_qty         INT DEFAULT 0,
    line_total            DECIMAL(12,2) DEFAULT 0.00,
    note                  VARCHAR(255),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- ========================
-- ORDER MEDIA
-- ========================
CREATE TABLE IF NOT EXISTS order_media (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT NOT NULL,
    media_type            VARCHAR(20),
    file_url              VARCHAR(500),
    uploaded_at           DATETIME DEFAULT NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

-- ========================
-- DELIVERIES
-- ========================
CREATE TABLE IF NOT EXISTS deliveries (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT NOT NULL,
    assigned_to_user_id   INT NOT NULL,
    assigned_by_user_id   INT NOT NULL,
    status                VARCHAR(30) DEFAULT 'pending',
    scheduled_date        DATETIME,
    actual_delivery_date  DATETIME,
    notes                 TEXT,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
    FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
);

-- ========================
-- DELIVERY ITEMS
-- ========================
CREATE TABLE IF NOT EXISTS delivery_items (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    delivery_id           INT NOT NULL,
    order_item_id         INT NOT NULL,
    delivered_qty         INT DEFAULT 0,
    returned_qty          INT DEFAULT 0,
    notes                 TEXT,
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id)
);

-- ========================
-- DELIVERY PROOF (POD)
-- ========================
CREATE TABLE IF NOT EXISTS delivery_proof (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    delivery_id           INT NOT NULL,
    signature_image_url   VARCHAR(500),
    photo_urls            JSON,
    voice_url             VARCHAR(500),
    customer_feedback     TEXT,
    created_at            DATETIME DEFAULT NOW(),
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE
);

-- ========================
-- PAYMENTS
-- ========================
CREATE TABLE IF NOT EXISTS payments (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT,
    customer_id           INT NOT NULL,
    user_id               INT NOT NULL,
    amount                DECIMAL(12,2) NOT NULL,
    payment_method        VARCHAR(30) NOT NULL,
    reference             VARCHAR(100),
    transaction_date      DATETIME DEFAULT NOW(),
    status                VARCHAR(20) DEFAULT 'completed',
    notes                 TEXT,
    created_at            DATETIME DEFAULT NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ========================
-- CASH SETTLEMENTS
-- ========================
CREATE TABLE IF NOT EXISTS cash_settlements (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    user_id               INT NOT NULL,
    amount                DECIMAL(12,2) NOT NULL,
    settlement_date       DATETIME DEFAULT NOW(),
    status                VARCHAR(20) DEFAULT 'pending',
    cashier_id            INT,
    finance_verifier_id   INT,
    notes                 TEXT,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (cashier_id) REFERENCES users(id),
    FOREIGN KEY (finance_verifier_id) REFERENCES users(id)
);

-- ========================
-- SETTLEMENT ITEMS
-- ========================
CREATE TABLE IF NOT EXISTS settlement_items (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    settlement_id         INT NOT NULL,
    order_id              INT,
    payment_id            INT,
    amount                DECIMAL(12,2) NOT NULL,
    payment_method        VARCHAR(30),
    reference             VARCHAR(100),
    FOREIGN KEY (settlement_id) REFERENCES cash_settlements(id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (payment_id) REFERENCES payments(id)
);

-- ========================
-- STOCK TRANSFERS (ENHANCED with inter-store support)
-- ========================
CREATE TABLE IF NOT EXISTS stock_transfers (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    from_user_id          INT NULL,
    to_user_id            INT NULL,
    captain_approved_by   INT,
    sender_warehouse_id   INT NULL,
    receiver_warehouse_id INT NULL,
    requested_by_user_id  INT NULL,
    transfer_barcode      VARCHAR(50) UNIQUE NULL,
    status                VARCHAR(50) DEFAULT 'requested',
    meeting_location      VARCHAR(255),
    scheduled_time        DATETIME,
    transfer_date         DATETIME,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (from_user_id) REFERENCES users(id),
    FOREIGN KEY (to_user_id) REFERENCES users(id),
    FOREIGN KEY (captain_approved_by) REFERENCES users(id),
    FOREIGN KEY (sender_warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL,
    FOREIGN KEY (receiver_warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL,
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id)
);

-- ========================
-- STOCK TRANSFER ITEMS
-- ========================
CREATE TABLE IF NOT EXISTS stock_transfer_items (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    stock_transfer_id     INT NOT NULL,
    product_id            INT NOT NULL,
    requested_qty         INT DEFAULT 0,
    transferred_qty       INT DEFAULT 0,
    scan_confirm_time     DATETIME,
    FOREIGN KEY (stock_transfer_id) REFERENCES stock_transfers(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- ========================
-- FINANCE TRANSACTIONS
-- ========================
CREATE TABLE IF NOT EXISTS finance_transactions (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT,
    customer_id           INT,
    user_id               INT NOT NULL,
    transaction_type      VARCHAR(30) NOT NULL,
    amount                DECIMAL(12,2) NOT NULL,
    reference             VARCHAR(100),
    description           TEXT,
    transaction_date      DATETIME DEFAULT NOW(),
    created_at            DATETIME DEFAULT NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ========================
-- ACTIVITY LOGS
-- ========================
CREATE TABLE IF NOT EXISTS activity_logs (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    user_id               INT NOT NULL,
    order_id              INT,
    action                VARCHAR(100),
    table_name            VARCHAR(50),
    record_id             INT,
    old_value             TEXT,
    new_value             TEXT,
    timestamp             DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

-- ========================
-- NOTIFICATIONS
-- ========================
CREATE TABLE IF NOT EXISTS notifications (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    user_id               INT NOT NULL,
    title                 VARCHAR(200) NOT NULL,
    body                  TEXT NOT NULL,
    data                  TEXT,
    `read`                BOOLEAN DEFAULT FALSE,
    created_at            DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ========================
-- RETURNS
-- ========================
CREATE TABLE IF NOT EXISTS returns (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    order_id              INT,
    product_id            INT NOT NULL,
    user_id               INT NOT NULL,
    return_type           VARCHAR(30) NOT NULL,
    quantity              INT NOT NULL,
    reason                VARCHAR(255),
    status                VARCHAR(20) DEFAULT 'pending',
    media_urls            JSON,
    approved_by           INT,
    approved_at           DATETIME,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (approved_by) REFERENCES users(id)
);

-- ========================
-- PRICE LISTS & DISCOUNT RULES
-- ========================
CREATE TABLE IF NOT EXISTS price_lists (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    name                  VARCHAR(100) NOT NULL,
    city_id               INT,
    effective_from        DATETIME,
    effective_to          DATETIME,
    is_active             BOOLEAN DEFAULT TRUE,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS price_list_items (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    price_list_id         INT NOT NULL,
    product_id            INT NOT NULL,
    unit_price            DECIMAL(12,2) NOT NULL,
    discount_percent      DECIMAL(5,2) DEFAULT 0.00,
    created_at            DATETIME DEFAULT NOW(),
    updated_at            DATETIME DEFAULT NOW() ON UPDATE NOW(),
    FOREIGN KEY (price_list_id) REFERENCES price_lists(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS customer_price_lists (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    customer_id           INT NOT NULL,
    price_list_id         INT NOT NULL,
    assigned_at           DATETIME DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (price_list_id) REFERENCES price_lists(id) ON DELETE CASCADE
);

-- ========================
-- INVENTORY TRANSACTIONS (ENHANCED)
-- ========================
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    product_id            INT NOT NULL,
    warehouse_id          INT NULL,
    agent_user_id         INT NULL,
    quantity              INT NOT NULL,
    type                  VARCHAR(20) NOT NULL,
    status                VARCHAR(20) DEFAULT 'pending',
    requested_by          INT NOT NULL,
    approved_by           INT NULL,
    notes                 TEXT,
    created_at            DATETIME DEFAULT NOW(),
    approved_at           DATETIME NULL,
    order_id              INT NULL,
    return_id             INT NULL,
    po_number             VARCHAR(100) NULL,
    po_date               DATETIME NULL,
    attachment_url        VARCHAR(500) NULL,
    ordered_qty           INT NULL,
    before_qty            INT NULL,
    after_qty             INT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL,
    FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (requested_by) REFERENCES users(id),
    FOREIGN KEY (approved_by) REFERENCES users(id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
    FOREIGN KEY (return_id) REFERENCES returns(id) ON DELETE SET NULL
);

-- ============================================================
-- NEW TABLES FOR OFFLINE-FIRST SECURITY & MEDIA MANAGEMENT
-- ============================================================

-- ========================
-- DEVICE API KEYS
-- ========================
CREATE TABLE IF NOT EXISTS api_keys (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    uuid          VARCHAR(36) UNIQUE NOT NULL DEFAULT (UUID()),
    device_uuid   VARCHAR(64) NOT NULL UNIQUE,
    api_key_hash  VARCHAR(128) NOT NULL,
    user_id       INT NOT NULL,
    status        VARCHAR(20) DEFAULT 'ACTIVE',
    created_at    DATETIME DEFAULT NOW(),
    last_used_at  DATETIME NULL,
    expires_at    DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_api_keys_status (status),
    INDEX idx_api_keys_user (user_id)
);

-- ========================
-- ONE-TIME CIPHER TOKENS
-- ========================
CREATE TABLE IF NOT EXISTS token_pools (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    uuid            VARCHAR(36) UNIQUE NOT NULL DEFAULT (UUID()),
    user_id         INT NOT NULL,
    session_id      VARCHAR(64) NOT NULL,
    cipher_token    VARCHAR(64) UNIQUE NOT NULL,
    token_status    VARCHAR(20) DEFAULT 'UNUSED',
    expiry_timestamp DATETIME NOT NULL,
    created_at      DATETIME DEFAULT NOW(),
    used_at         DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_token_pools_status_expiry (token_status, expiry_timestamp),
    INDEX idx_token_pools_user (user_id)
);

-- ========================
-- MEDIA FILES (uploaded from mobile)
-- ========================
CREATE TABLE IF NOT EXISTS media (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    uuid                VARCHAR(36) UNIQUE NOT NULL DEFAULT (UUID()),
    user_id             INT NOT NULL,
    order_id            INT NULL,
    product_id          INT NULL,
    file_name           VARCHAR(255) NOT NULL,
    file_path           VARCHAR(500) NOT NULL,
    file_size           INT NULL,
    file_hash           VARCHAR(64) NULL,
    mime_type           VARCHAR(100) NULL,
    encryption_key_ref  VARCHAR(64) NULL,
    upload_status       VARCHAR(20) DEFAULT 'PENDING',
    uploaded_at         DATETIME NULL,
    deleted_from_device BOOLEAN DEFAULT FALSE,
    created_at          DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    INDEX idx_media_upload_status (upload_status),
    INDEX idx_media_user (user_id)
);

-- ========================
-- MEDIA UPLOAD STATUS (tracking per media file sync attempts)
-- ========================
CREATE TABLE IF NOT EXISTS media_upload_status (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    media_id        INT NOT NULL,
    upload_attempt  INT DEFAULT 0,
    last_attempt_at DATETIME NULL,
    status_message  TEXT NULL,
    success         BOOLEAN DEFAULT FALSE,
    completed_at    DATETIME NULL,
    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
    INDEX idx_media_upload_status_media (media_id)
);

-- ========================
-- DEVICE COMMAND QUEUE
-- ========================
CREATE TABLE IF NOT EXISTS device_commands (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    uuid            VARCHAR(36) UNIQUE NOT NULL DEFAULT (UUID()),
    user_id         INT NOT NULL,
    command_type    VARCHAR(50) NOT NULL,
    payload         JSON NULL,
    status          VARCHAR(20) DEFAULT 'PENDING',
    created_at      DATETIME DEFAULT NOW(),
    sent_at         DATETIME NULL,
    acknowledged_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_device_commands_status (status),
    INDEX idx_device_commands_user (user_id)
);

-- ============================================================
-- INDEXES (for performance)
-- ============================================================
CREATE INDEX idx_messages_user_id ON messages(user_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_orders_sales_person ON orders(sales_person_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_agent_inventory_user ON agent_inventory(user_id);
CREATE INDEX idx_agent_inventory_product ON agent_inventory(product_id);
CREATE INDEX idx_stock_transfers_from_user ON stock_transfers(from_user_id);
CREATE INDEX idx_stock_transfers_to_user ON stock_transfers(to_user_id);
CREATE INDEX idx_stock_transfers_status ON stock_transfers(status);
CREATE INDEX idx_products_updated_at ON products(updated_at);
CREATE INDEX idx_deliveries_assigned_to ON deliveries(assigned_to_user_id);
CREATE INDEX idx_deliveries_status ON deliveries(status);
CREATE INDEX idx_payments_customer ON payments(customer_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_settlements_user ON cash_settlements(user_id);
CREATE INDEX idx_settlements_status ON cash_settlements(status);
CREATE INDEX idx_finance_transactions_type ON finance_transactions(transaction_type);
CREATE INDEX idx_finance_transactions_date ON finance_transactions(transaction_date);
CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);
CREATE INDEX idx_returns_status ON returns(status);
CREATE INDEX idx_price_lists_city ON price_lists(city_id);
CREATE INDEX idx_inventory_transactions_status ON inventory_transactions(status);
CREATE INDEX idx_inventory_transactions_type ON inventory_transactions(type);
CREATE INDEX idx_inventory_transactions_created ON inventory_transactions(created_at);