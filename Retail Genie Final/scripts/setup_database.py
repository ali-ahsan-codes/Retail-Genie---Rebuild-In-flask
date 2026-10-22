"""Create the isolated Retail Genie MySQL database and local app credentials."""

from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import pymysql
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = "retail_genie"
APP_USERNAME = "retail_genie_app"
APP_HOST = "127.0.0.1"
ADMIN_DATABASE_URL_FILE = ROOT / ".env"
APP_ENV_FILE = ROOT / ".env.retail-genie"
SCHEMA_FILE = ROOT / "database-schema.sql"
PRIVILEGE_ERRORS = {1044, 1045, 1142, 1227, 1698}


class SetupError(Exception):
    """A safe-to-display setup failure."""


def credentials_from_shared_env() -> dict[str, str | int] | None:
    raw_url = dotenv_values(ADMIN_DATABASE_URL_FILE).get("DATABASE_URL")
    if not raw_url:
        return None

    parsed = urlsplit(raw_url)
    if not parsed.scheme.startswith("mysql") or not parsed.hostname or not parsed.username or parsed.password is None:
        return None
    if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise SetupError("The existing MySQL URL is not for a local server. Supply a local MySQL administrator login.")

    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
    }


def prompt_for_admin_credentials(host: str = "127.0.0.1", port: int = 3306) -> dict[str, str | int]:
    username = input("MySQL administrator username [root]: ").strip() or "root"
    password = getpass.getpass("MySQL administrator password: ")
    if not password:
        raise SetupError("A MySQL administrator password is required.")
    return {"host": host, "port": port, "user": username, "password": password}


def connect_as_admin(credentials: dict[str, str | int]) -> pymysql.Connection:
    return pymysql.connect(
        host=str(credentials["host"]),
        port=int(credentials["port"]),
        user=str(credentials["user"]),
        password=str(credentials["password"]),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )


def expected_schema_tables() -> set[str]:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE\s+TABLE\s+[`]?([A-Za-z0-9_]+)[`]?", schema, re.IGNORECASE))


def install_schema_if_empty(connection: pymysql.Connection) -> None:
    expected_tables = expected_schema_tables()
    if not expected_tables:
        raise SetupError("No table definitions were found in database-schema.sql.")

    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS `retail_genie` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (DATABASE_NAME,),
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        if expected_tables.issubset(existing_tables):
            print("The Retail Genie schema is already installed; leaving its tables unchanged.")
            return
        if existing_tables:
            raise SetupError(
                "The retail_genie database contains a partial or different schema. "
                "No tables were changed; inspect it before continuing."
            )

        schema = SCHEMA_FILE.read_text(encoding="utf-8")
        for chunk in schema.split(";"):
            statement = "\n".join(
                line for line in chunk.splitlines() if not line.lstrip().startswith("--")
            ).strip()
            if statement:
                cursor.execute(statement)

    print("Created the Retail Genie tables in the dedicated database.")


def write_app_environment(database_port: int, app_password: str) -> None:
    encoded_password = quote(app_password, safe="")
    database_url = (
        f"mysql+pymysql://{APP_USERNAME}:{encoded_password}@{APP_HOST}:"
        f"{database_port}/{DATABASE_NAME}?charset=utf8mb4"
    )
    contents = "\n".join(
        [
            "# Generated for Retail Genie. Keep this file private and out of version control.",
            f"SECRET_KEY={secrets.token_urlsafe(48)}",
            f"DATABASE_URL={database_url}",
            "FLASK_HOST=127.0.0.1",
            "FLASK_PORT=5000",
            "FLASK_DEBUG=false",
            "SESSION_COOKIE_SECURE=false",
            "SESSION_LIFETIME_HOURS=8",
            "PUBLIC_BASE_URL=",
            "BACKUP_DIR=",
            "BACKUP_DATABASE_URL=",
            "MYSQLDUMP_PATH=mysqldump",
            "BACKUP_TIMEOUT_SECONDS=7200",
            "BACKUP_SCHEDULER_POLL_SECONDS=15",
            "RATELIMIT_STORAGE_URI=memory://",
            "SMTP_HOST=",
            "SMTP_PORT=587",
            "SMTP_SENDER=",
            "SMTP_USERNAME=",
            "SMTP_PASSWORD=",
            "SMTP_USE_TLS=true",
            "SMTP_USE_SSL=false",
            "SMTP_TIMEOUT_SECONDS=15",
            "",
        ]
    )
    APP_ENV_FILE.write_text(contents, encoding="utf-8")


def provision(credentials: dict[str, str | int]) -> None:
    connection = connect_as_admin(credentials)
    try:
        install_schema_if_empty(connection)
        app_password = secrets.token_urlsafe(36)
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE USER IF NOT EXISTS 'retail_genie_app'@'127.0.0.1' IDENTIFIED BY %s",
                (app_password,),
            )
            cursor.execute(
                "ALTER USER 'retail_genie_app'@'127.0.0.1' IDENTIFIED BY %s",
                (app_password,),
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON `retail_genie`.* "
                "TO 'retail_genie_app'@'127.0.0.1'"
            )
        write_app_environment(int(credentials["port"]), app_password)
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the isolated Retail Genie MySQL database.")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Fail instead of requesting administrator credentials if .env credentials lack privileges.",
    )
    args = parser.parse_args()

    try:
        credentials = credentials_from_shared_env()
        if credentials:
            print("Using the MySQL login from .env for provisioning; its configured database is ignored.")
            try:
                provision(credentials)
            except pymysql.MySQLError as error:
                error_code = error.args[0] if error.args and isinstance(error.args[0], int) else None
                if args.no_prompt or error_code not in PRIVILEGE_ERRORS:
                    raise SetupError(
                        "The MySQL login in .env could not provision Retail Genie. "
                        "Check that MySQL is running and the login can create databases and users."
                    ) from None
                print("That login lacks provisioning privileges; enter a MySQL administrator login.")
                credentials = prompt_for_admin_credentials(
                    str(credentials["host"]), int(credentials["port"])
                )
                provision(credentials)
        else:
            credentials = prompt_for_admin_credentials()
            provision(credentials)
    except SetupError as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1
    except pymysql.MySQLError as error:
        error_code = error.args[0] if error.args and isinstance(error.args[0], int) else None
        if error_code == 1045:
            message = "MySQL rejected the administrator login."
        elif error_code in {2003, 2006, 2013}:
            message = "Could not reach MySQL. Check that the local MySQL service is running."
        else:
            message = "MySQL provisioning failed. Check server permissions and database-schema.sql."
        print(f"Setup failed: {message}", file=sys.stderr)
        return 1

    print("Retail Genie database is ready; .env.retail-genie was created. The shared .env was not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())