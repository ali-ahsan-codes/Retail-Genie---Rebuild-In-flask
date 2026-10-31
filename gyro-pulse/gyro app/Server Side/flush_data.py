#!/usr/bin/env python
"""
Standalone data flusher for Gyro Pulse.
Usage:
    python flush_data.py               # removes ALL data (including users)
    python flush_data.py --keep-users  # removes data but keeps users & role API keys
"""

import os
import re
import sys
import pymysql
from dotenv import load_dotenv

# Load .env
load_dotenv()

def get_db_credentials():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")
    # Remove scheme
    db_url = db_url.replace('mysql+pymysql://', '')
    # user:pass@host:port/db
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

def main():
    keep_users = '--keep-users' in sys.argv

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

        # Get all table names
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        # Exclude tables if keep_users
        exclude = ('users', 'role_api_keys') if keep_users else ()
        tables_to_flush = [t for t in tables if t not in exclude]

        if not tables_to_flush:
            print("No tables to flush.")
            return

        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        print(f"Flushing {len(tables_to_flush)} tables...")
        for table in tables_to_flush:
            try:
                cursor.execute(f"TRUNCATE TABLE {table}")
                print(f"  ✓ Truncated {table}")
            except Exception as e:
                # Fallback to DELETE if TRUNCATE fails
                try:
                    cursor.execute(f"DELETE FROM {table}")
                    print(f"  ✓ Deleted all rows from {table}")
                except Exception as e2:
                    print(f"  ✗ Failed to clear {table}: {e2}")

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        print("Data flush complete.")
        if keep_users:
            print("Users and role API keys were preserved.")
        else:
            print("All data has been removed.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        connection.close()

if __name__ == '__main__':
    main()