"""Read-only deployment preflight checks for Phase 6 acceptance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


class PreflightError(RuntimeError):
    """A deployment preflight cannot safely run for this database target."""


def mysql_deployment_preflight(
    engine: Engine,
    migration_config: Any,
    expected_tables: Iterable[str],
) -> list[PreflightCheck]:
    """Inspect MySQL version, schema migration state, engines, and FK checks.

    This function intentionally performs SELECT-only inspection. It never
    upgrades, alters, seeds, or writes to the configured database.
    """
    if engine.dialect.name != "mysql":
        raise PreflightError("Phase 6 preflight only accepts a MySQL connection; no SQL was run.")

    checks: list[PreflightCheck] = []
    try:
        with engine.connect() as connection:
            version, version_comment = connection.execute(
                text("SELECT VERSION(), @@version_comment")
            ).one()
            version = str(version)
            version_comment = str(version_comment or "")
            match = re.match(r"^(\d+)(?:\.(\d+))?", version)
            is_mysql8 = bool(match and int(match.group(1)) >= 8 and "mariadb" not in version.casefold() and "mariadb" not in version_comment.casefold())
            checks.append(
                PreflightCheck(
                    "MySQL 8 server",
                    is_mysql8,
                    f"{version} ({version_comment})" if version_comment else version,
                )
            )

            migration_context = MigrationContext.configure(connection)
            current_heads = set(migration_context.get_current_heads())
            expected_heads = set(ScriptDirectory.from_config(migration_config).get_heads())
            migrations_match = bool(expected_heads) and current_heads == expected_heads
            checks.append(
                PreflightCheck(
                    "Alembic revision",
                    migrations_match,
                    f"database={','.join(sorted(current_heads)) or 'none'}; code={','.join(sorted(expected_heads)) or 'none'}",
                )
            )

            tables = connection.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
                )
            ).all()
            engines = {str(name): str(storage_engine or "").casefold() for name, storage_engine in tables}
            missing = sorted(set(expected_tables) - set(engines))
            non_innodb = sorted(name for name, storage_engine in engines.items() if storage_engine != "innodb")
            checks.append(
                PreflightCheck(
                    "Application schema and InnoDB",
                    not missing and not non_innodb,
                    "all mapped tables exist and use InnoDB"
                    if not missing and not non_innodb
                    else f"missing tables={missing or 'none'}; non-InnoDB tables={non_innodb or 'none'}",
                )
            )

            fk_checks = int(connection.execute(text("SELECT @@SESSION.FOREIGN_KEY_CHECKS")).scalar_one())
            checks.append(
                PreflightCheck(
                    "Foreign-key enforcement",
                    fk_checks == 1,
                    f"@@SESSION.FOREIGN_KEY_CHECKS={fk_checks}",
                )
            )
    except PreflightError:
        raise
    except Exception as exc:
        # Avoid surfacing a URL, username, or server-specific driver error that
        # could include secrets in CLI output or deployment logs.
        raise PreflightError(
            f"Read-only MySQL inspection failed ({type(exc).__name__}); verify connectivity and database privileges."
        ) from None

    return checks
