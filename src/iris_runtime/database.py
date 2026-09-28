"""Short-lived database connections with bounded connection and statement timeouts."""

from typing import Any

import psycopg
from psycopg.rows import dict_row

from iris_runtime.config import DatabaseSettings
from iris_runtime.errors import RuntimeContractError


def connect_database(settings: DatabaseSettings) -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name,
        user=settings.user,
        password=settings.password.get_secret_value(),
        connect_timeout=settings.connect_timeout_seconds,
        application_name="iris-pilot-runtime",
        options="-c statement_timeout=60000 -c lock_timeout=15000",
        row_factory=dict_row,
    )


def verify_database_versions(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, str]:
    row = connection.execute(
        "SELECT current_setting('server_version_num') AS postgres_version, "
        "postgis_lib_version() AS postgis_version"
    ).fetchone()
    if row is None:
        raise RuntimeContractError("Database did not return its version")
    postgis_version = tuple(int(part) for part in row["postgis_version"].split(".")[:2])
    if int(row["postgres_version"]) < 160000 or postgis_version < (3, 4):
        raise RuntimeContractError("PostgreSQL 16+ and PostGIS 3.4+ are required")
    return {key: str(value) for key, value in row.items()}
