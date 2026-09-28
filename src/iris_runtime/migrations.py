"""Ordered, checksum-verified SQL migrations committed together under an advisory lock."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from pydantic import SecretStr

from iris_runtime.config import DatabaseSettings
from iris_runtime.database import connect_database, verify_database_versions
from iris_runtime.errors import RuntimeContractError

MIGRATION_DIRECTORY = Path(__file__).with_name("sql")
MIGRATION_LOCK_ID = 690009


@dataclass(frozen=True)
class Migration:
    name: str
    statement: str
    sha256: str


def read_migrations(directory: Path = MIGRATION_DIRECTORY) -> list[Migration]:
    paths = sorted(directory.glob("*.sql"))
    if not paths:
        raise RuntimeContractError("No packaged SQL migrations were found")
    migrations = []
    for sequence, path in enumerate(paths, start=1):
        if not re.fullmatch(rf"{sequence:03d}_[a-z0-9_]+\.sql", path.name):
            raise RuntimeContractError("SQL migrations must have consecutive three-digit prefixes")
        content = path.read_bytes()
        migrations.append(
            Migration(path.name, content.decode(), hashlib.sha256(content).hexdigest())
        )
    return migrations


def apply_migrations(
    connection: psycopg.Connection[dict[str, Any]],
    directory: Path = MIGRATION_DIRECTORY,
) -> int:
    migrations = read_migrations(directory)
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
    connection.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    verify_database_versions(connection)
    connection.execute("CREATE SCHEMA IF NOT EXISTS iris")
    connection.execute("REVOKE ALL ON SCHEMA iris FROM PUBLIC")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS iris.schema_migrations ("
        "name text PRIMARY KEY, sha256 text NOT NULL, "
        "applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {
        row["name"]: row["sha256"]
        for row in connection.execute("SELECT name, sha256 FROM iris.schema_migrations")
    }
    expected = {migration.name: migration.sha256 for migration in migrations}
    if any(
        name not in expected or expected[name] != checksum for name, checksum in applied.items()
    ):
        raise RuntimeContractError(
            "Migration history differs from packaged SQL; refusing to proceed"
        )
    if set(applied) != {migration.name for migration in migrations[: len(applied)]}:
        raise RuntimeContractError("Migration history has a gap; refusing to proceed")
    applied_count = 0
    for migration in migrations:
        if migration.name in applied:
            continue
        connection.execute(migration.statement)
        connection.execute(
            "INSERT INTO iris.schema_migrations (name, sha256) VALUES (%s, %s)",
            (migration.name, migration.sha256),
        )
        applied_count += 1
    return applied_count


def provision_worker_role(
    connection: psycopg.Connection[dict[str, Any]], username: str, password: SecretStr
) -> None:
    existing = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = %s",
        (username,),
    ).fetchone()
    if existing and any(existing.values()):
        raise RuntimeContractError("Refusing to use a privileged role as the worker account")
    inherited_role = connection.execute(
        "SELECT 1 FROM pg_auth_members AS membership "
        "JOIN pg_roles AS member_role ON membership.member = member_role.oid "
        "WHERE member_role.rolname = %s LIMIT 1",
        (username,),
    ).fetchone()
    if inherited_role:
        raise RuntimeContractError("The worker account must not inherit other database roles")
    if existing is None:
        connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(username)))
    connection.execute(
        sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(username), sql.Literal(password.get_secret_value())
        )
    )
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA iris TO {}").format(sql.Identifier(username)))
    connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON iris.source_datasets, iris.sites TO {}"
        ).format(sql.Identifier(username))
    )


def migrate_database(settings: DatabaseSettings, username: str, password: SecretStr) -> int:
    # The connection context commits everything or rolls everything back, including role grants.
    with connect_database(settings) as connection:
        applied_count = apply_migrations(connection)
        provision_worker_role(connection, username, password)
    return applied_count
