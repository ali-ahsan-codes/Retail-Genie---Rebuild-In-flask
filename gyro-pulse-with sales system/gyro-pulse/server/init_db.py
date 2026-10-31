import os
import sys
import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

def get_db_credentials():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")
    # Remove scheme
    db_url = db_url.replace('mysql+pymysql://', '')
    # user:pass@host:port/db
    import re
    match = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
    if not match:
        raise ValueError("Invalid DATABASE_URL format")
    user, password, host, port, database = match.groups()
    # URL-decode password
    password = password.replace('%40', '@')
    return {
        'user': user,
        'password': password,
        'host': host,
        'port': int(port),
        'database': database
    }

def drop_and_create_database():
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
        # Drop database if exists
        print(f"Dropping database {creds['database']} if exists...")
        cursor.execute(f"DROP DATABASE IF EXISTS {creds['database']}")
        # Create fresh database
        print(f"Creating database {creds['database']}...")
        cursor.execute(f"CREATE DATABASE {creds['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print("✅ Database created successfully.")
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        sys.exit(1)
    finally:
        connection.close()

def create_tables_with_sqlalchemy():
    # Now use SQLAlchemy to create all tables
    from app import create_app
    from models import db

    app = create_app()
    with app.app_context():
        # Set the database URI (already loaded from .env)
        print("Creating all tables using SQLAlchemy models...")
        db.create_all()
        print("✅ All tables created successfully.")

if __name__ == '__main__':
    drop_and_create_database()
    create_tables_with_sqlalchemy()
    print("\n🎉 Database initialization complete!")
    print("You can now run 'python app.py' to start the server.")
    print("Default admin user (admin/admin123) will be created automatically on first run.")