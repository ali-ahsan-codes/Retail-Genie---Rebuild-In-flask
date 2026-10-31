#!/usr/bin/env python
"""
Database Migration Script for Gyro Pulse v4.0
Run this once on your existing database to upgrade it to the new schema.

Usage:
    python migrate.py
"""

import os
import pymysql
import re
from dotenv import load_dotenv

load_dotenv()

def get_db_credentials():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")
    db_url = db_url.replace('mysql+pymysql://', '')
    match = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
    if not match:
        raise ValueError("Invalid DATABASE_URL format")
    user, password, host, port, database = match.groups()
    password = password.replace('%40', '@')
    return {
        'user': user,
        'password': password,
        'host': host,
        'port': int(port),
        'database': database
    }

def column_exists(cursor, table, column):
    cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column}'")
    return cursor.fetchone() is not None

def table_exists(cursor, table):
    cursor.execute(f"SHOW TABLES LIKE '{table}'")
    return cursor.fetchone() is not None

def main():
    creds = get_db_credentials()
    print(f"Connecting to {creds['host']}:{creds['port']} as {creds['user']}")

    connection = pymysql.connect(
        host=creds['host'],
        port=creds['port'],
        user=creds['user'],
        password=creds['password'],
        autocommit=True,
        charset='utf8mb4'
    )
    try:
        cursor = connection.cursor()
        cursor.execute(f"USE {creds['database']}")

        # ============================================================
        # 1. Add is_active to cities (if not already)
        # ============================================================
        if not column_exists(cursor, 'cities', 'is_active'):
            print("Adding is_active to cities...")
            cursor.execute("ALTER TABLE cities ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
            print("✓ Added is_active to cities.")
        else:
            print("✓ 'is_active' already exists in cities.")

        # ============================================================
        # 2. Add updated_at to products (if missing)
        # ============================================================
        if not column_exists(cursor, 'products', 'updated_at'):
            print("Adding updated_at to products...")
            cursor.execute("ALTER TABLE products ADD COLUMN updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()")
            cursor.execute("CREATE INDEX idx_products_updated_at ON products(updated_at)")
            print("✓ Added updated_at to products.")
        else:
            print("✓ 'updated_at' already exists in products.")

        # ============================================================
        # 3. Add new columns to inventory_transactions (if not already)
        # ============================================================
        inv_cols = [
            ('po_number', 'VARCHAR(100) NULL'),
            ('po_date', 'DATETIME NULL'),
            ('attachment_url', 'VARCHAR(500) NULL'),
            ('ordered_qty', 'INT NULL'),
            ('before_qty', 'INT NULL'),
            ('after_qty', 'INT NULL')
        ]
        for col, col_def in inv_cols:
            if not column_exists(cursor, 'inventory_transactions', col):
                print(f"Adding {col} to inventory_transactions...")
                cursor.execute(f"ALTER TABLE inventory_transactions ADD COLUMN {col} {col_def}")
                print(f"✓ Added {col}.")
            else:
                print(f"✓ '{col}' already exists in inventory_transactions.")

        # ============================================================
        # 4. Add new columns to stock_transfers (inter-store support)
        # ============================================================
        st_cols = [
            ('sender_warehouse_id', 'INT NULL'),
            ('receiver_warehouse_id', 'INT NULL'),
            ('requested_by_user_id', 'INT NULL'),
            ('transfer_barcode', 'VARCHAR(50) UNIQUE NULL'),
        ]
        for col, col_def in st_cols:
            if not column_exists(cursor, 'stock_transfers', col):
                print(f"Adding {col} to stock_transfers...")
                cursor.execute(f"ALTER TABLE stock_transfers ADD COLUMN {col} {col_def}")
                print(f"✓ Added {col}.")
            else:
                print(f"✓ '{col}' already exists in stock_transfers.")

        # ============================================================
        # 5. Add new columns to stock_transfer_items
        # ============================================================
        sti_cols = [
            ('transferred_qty', 'INT DEFAULT 0'),
            ('scan_confirm_time', 'DATETIME NULL'),
        ]
        for col, col_def in sti_cols:
            if not column_exists(cursor, 'stock_transfer_items', col):
                print(f"Adding {col} to stock_transfer_items...")
                cursor.execute(f"ALTER TABLE stock_transfer_items ADD COLUMN {col} {col_def}")
                print(f"✓ Added {col}.")
            else:
                print(f"✓ '{col}' already exists in stock_transfer_items.")

        # ============================================================
        # 6. Add new columns to users (stock visibility toggle & last sync)
        # ============================================================
        user_cols = [
            ('show_stock_quantity', 'BOOLEAN DEFAULT TRUE'),
            ('last_sync_at', 'DATETIME NULL'),
        ]
        for col, col_def in user_cols:
            if not column_exists(cursor, 'users', col):
                print(f"Adding {col} to users...")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                print(f"✓ Added {col}.")
            else:
                print(f"✓ '{col}' already exists in users.")

        # ============================================================
        # 7. Create SERVER_CONFIG table
        # ============================================================
        if not table_exists(cursor, 'server_config'):
            print("Creating server_config table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_config (
                    `key` VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
                )
            """)
            # Seed default values
            cursor.execute("INSERT INTO server_config (`key`, value) VALUES ('MAX_TOKEN_CAP', '15')")
            cursor.execute("INSERT INTO server_config (`key`, value) VALUES ('TOKEN_RENEWAL_THRESHOLD', '2')")
            cursor.execute("INSERT INTO server_config (`key`, value) VALUES ('DEFAULT_EXPIRY_DAYS', '7')")
            print("✓ Created server_config with default values.")
        else:
            print("✓ 'server_config' already exists.")

        # ============================================================
        # 8. Create API_KEYS table
        # ============================================================
        if not table_exists(cursor, 'api_keys'):
            print("Creating api_keys table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    uuid VARCHAR(36) UNIQUE NOT NULL,
                    device_uuid VARCHAR(64) NOT NULL UNIQUE,
                    api_key_hash VARCHAR(128) NOT NULL,
                    user_id INT NOT NULL,
                    status VARCHAR(20) DEFAULT 'ACTIVE',
                    created_at DATETIME DEFAULT NOW(),
                    last_used_at DATETIME NULL,
                    expires_at DATETIME NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_api_keys_status (status),
                    INDEX idx_api_keys_user (user_id)
                )
            """)
            print("✓ Created api_keys table.")
        else:
            print("✓ 'api_keys' already exists.")

        # ============================================================
        # 9. Create TOKEN_POOLS table
        # ============================================================
        if not table_exists(cursor, 'token_pools'):
            print("Creating token_pools table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS token_pools (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    uuid VARCHAR(36) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    session_id VARCHAR(64) NOT NULL,
                    cipher_token VARCHAR(64) UNIQUE NOT NULL,
                    token_status VARCHAR(20) DEFAULT 'UNUSED',
                    expiry_timestamp DATETIME NOT NULL,
                    created_at DATETIME DEFAULT NOW(),
                    used_at DATETIME NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_token_pools_status_expiry (token_status, expiry_timestamp),
                    INDEX idx_token_pools_user (user_id)
                )
            """)
            print("✓ Created token_pools table.")
        else:
            print("✓ 'token_pools' already exists.")

        # ============================================================
        # 10. Create MEDIA table
        # ============================================================
        if not table_exists(cursor, 'media'):
            print("Creating media table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS media (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    uuid VARCHAR(36) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    order_id INT NULL,
                    product_id INT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_size INT NULL,
                    file_hash VARCHAR(64) NULL,
                    mime_type VARCHAR(100) NULL,
                    encryption_key_ref VARCHAR(64) NULL,
                    upload_status VARCHAR(20) DEFAULT 'PENDING',
                    uploaded_at DATETIME NULL,
                    deleted_from_device BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
                    INDEX idx_media_upload_status (upload_status),
                    INDEX idx_media_user (user_id)
                )
            """)
            print("✓ Created media table.")
        else:
            print("✓ 'media' already exists.")

        # ============================================================
        # 11. Create MEDIA_UPLOAD_STATUS table
        # ============================================================
        if not table_exists(cursor, 'media_upload_status'):
            print("Creating media_upload_status table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS media_upload_status (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    media_id INT NOT NULL,
                    upload_attempt INT DEFAULT 0,
                    last_attempt_at DATETIME NULL,
                    status_message TEXT NULL,
                    success BOOLEAN DEFAULT FALSE,
                    completed_at DATETIME NULL,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                    INDEX idx_media_upload_status_media (media_id)
                )
            """)
            print("✓ Created media_upload_status table.")
        else:
            print("✓ 'media_upload_status' already exists.")

        # ============================================================
        # 12. Create DEVICE_COMMANDS table
        # ============================================================
        if not table_exists(cursor, 'device_commands'):
            print("Creating device_commands table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_commands (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    uuid VARCHAR(36) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    command_type VARCHAR(50) NOT NULL,
                    payload JSON NULL,
                    status VARCHAR(20) DEFAULT 'PENDING',
                    created_at DATETIME DEFAULT NOW(),
                    sent_at DATETIME NULL,
                    acknowledged_at DATETIME NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_device_commands_status (status),
                    INDEX idx_device_commands_user (user_id)
                )
            """)
            print("✓ Created device_commands table.")
        else:
            print("✓ 'device_commands' already exists.")

        # ============================================================
        # 13. Summary
        # ============================================================
        print("\n" + "="*60)
        print("✅ All migrations completed successfully!")
        print("   The database has been upgraded to version 4.0.")
        print("   New tables: server_config, api_keys, token_pools, media, media_upload_status, device_commands")
        print("   New columns added to users, stock_transfers, stock_transfer_items, inventory_transactions.")
        print("="*60)

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        connection.close()

if __name__ == '__main__':
    main()