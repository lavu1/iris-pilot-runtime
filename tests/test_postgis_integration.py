import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
import pytest

from iris_runtime.config import DatabaseSettings, RuntimeSettings, worker_credentials
from iris_runtime.database import connect_database
from iris_runtime.errors import RuntimeContractError
from iris_runtime.migrations import MIGRATION_DIRECTORY, apply_migrations, migrate_database
from iris_runtime.repository import read_source_snapshot
from iris_runtime.smoke import run_smoke_test
from iris_runtime.worker import run_worker

pytestmark = pytest.mark.integration
FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "fixtures"


def test_migrations_are_repeatable_and_concurrency_safe(admin_database: DatabaseSettings) -> None:
    username, password = worker_credentials()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: migrate_database(admin_database, username, password), [1, 2])
        )
    assert results == [0, 0]
    with connect_database(admin_database) as connection:
        assert connection.execute(
            "SELECT count(*) AS count FROM iris.schema_migrations"
        ).fetchone() == {"count": 2}


def test_changed_migration_checksum_is_rejected(admin_database: DatabaseSettings) -> None:
    with (
        pytest.raises(RuntimeContractError, match="history differs"),
        connect_database(admin_database) as connection,
    ):
        connection.execute(
            "UPDATE iris.schema_migrations SET sha256 = 'changed' WHERE name LIKE '001%'"
        )
        apply_migrations(connection)
    # The failed context rolled back the simulated tampering.
    assert migrate_database(admin_database, *worker_credentials()) == 0


def test_failed_migration_rolls_back_ddl_and_tracking(
    admin_database: DatabaseSettings, tmp_path: Path
) -> None:
    for original in MIGRATION_DIRECTORY.glob("*.sql"):
        (tmp_path / original.name).write_bytes(original.read_bytes())
    (tmp_path / "003_failure.sql").write_text(
        "CREATE TABLE iris.should_not_exist (id integer); SELECT 1 / 0;"
    )
    with (
        pytest.raises(psycopg.errors.DivisionByZero),
        connect_database(admin_database) as connection,
    ):
        apply_migrations(connection, tmp_path)
    with connect_database(admin_database) as connection:
        assert connection.execute(
            "SELECT to_regclass('iris.should_not_exist') AS name"
        ).fetchone() == {"name": None}
        assert connection.execute(
            "SELECT count(*) AS count FROM iris.schema_migrations"
        ).fetchone() == {"count": 2}


def test_smoke_verifies_postgis_output_and_replay(worker_settings: RuntimeSettings) -> None:
    result = run_smoke_test(worker_settings)
    assert result["event"] == "smoke_passed"
    assert result["feature_count"] == 2
    assert result["replay_identical"] is True


def test_same_site_ids_in_two_countries_remain_isolated(worker_settings: RuntimeSettings) -> None:
    de_result = run_worker(worker_settings)
    zm_settings = worker_settings.model_copy(
        update={
            "country_code": "ZM",
            "region_code": "LSK",
            "source_endpoint": (FIXTURE_DIRECTORY / "zm-lsk.json").as_uri(),
        }
    )
    zm_result = run_worker(zm_settings)
    assert de_result.output_file != zm_result.output_file
    with connect_database(worker_settings.database) as connection:
        rows = connection.execute(
            "SELECT country_code, count(*) AS count FROM iris.sites "
            "GROUP BY country_code ORDER BY country_code"
        ).fetchall()
    assert rows == [{"country_code": "DE", "count": 2}, {"country_code": "ZM", "count": 2}]
    assert json.loads(de_result.output_file.read_text())["sites"][0]["name"] == "Rhine Demo Site A"
    assert json.loads(zm_result.output_file.read_text())["sites"][0]["name"] == "Mwansa Demo Site A"


def test_invalid_geometry_rolls_back_entire_snapshot(
    worker_settings: RuntimeSettings, source_payload: dict[str, Any], tmp_path: Path
) -> None:
    initial = run_worker(worker_settings)
    original_output = initial.output_file.read_bytes()
    # A self-intersecting bow-tie passes structural validation but PostGIS must reject it.
    source_payload["sites"][1]["geom"]["coordinates"] = [
        [[7, 51], [8, 52], [7, 52], [8, 51], [7, 51]]
    ]
    source_payload["sites"][0]["name"] = "Must be rolled back"
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text(json.dumps(source_payload))
    with pytest.raises(psycopg.errors.CheckViolation):
        run_worker(worker_settings.model_copy(update={"source_endpoint": invalid_file.as_uri()}))
    assert initial.output_file.read_bytes() == original_output
    with connect_database(worker_settings.database) as connection:
        persisted = read_source_snapshot(connection, "DE", "NW", "pilot-fixture")
    assert persisted == json.loads(original_output)


def test_snapshot_replacement_removes_only_stale_records_in_its_scope(
    worker_settings: RuntimeSettings, source_payload: dict[str, Any], tmp_path: Path
) -> None:
    run_worker(worker_settings)
    run_worker(
        worker_settings.model_copy(
            update={
                "country_code": "ZM",
                "region_code": "LSK",
                "source_endpoint": (FIXTURE_DIRECTORY / "zm-lsk.json").as_uri(),
            }
        )
    )
    source_payload["sites"].pop()
    source_payload["contract"]["expected_feature_count"] = 1
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps(source_payload))
    result = run_worker(
        worker_settings.model_copy(update={"source_endpoint": replacement.as_uri()})
    )
    assert len(json.loads(result.output_file.read_text())["sites"]) == 1
    with connect_database(worker_settings.database) as connection:
        other_country = read_source_snapshot(connection, "ZM", "LSK", "pilot-fixture")
    assert len(other_country["sites"]) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE iris.forbidden (id integer)",
        "DELETE FROM iris.schema_migrations",
        "ALTER TABLE iris.sites ADD COLUMN forbidden text",
    ],
)
def test_worker_cannot_modify_schema_or_migration_history(
    worker_settings: RuntimeSettings, statement: str
) -> None:
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect_database(worker_settings.database) as connection,
    ):
        connection.execute(statement)


def test_cross_country_foreign_key_is_rejected(worker_settings: RuntimeSettings) -> None:
    run_worker(worker_settings)
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        connect_database(worker_settings.database) as connection,
    ):
        connection.execute("UPDATE iris.sites SET country_code = 'ZM' WHERE country_code = 'DE'")


def test_missing_country_is_rejected_by_database(worker_settings: RuntimeSettings) -> None:
    run_worker(worker_settings)
    with (
        pytest.raises(psycopg.errors.NotNullViolation),
        connect_database(worker_settings.database) as connection,
    ):
        connection.execute("UPDATE iris.sites SET country_code = NULL")


def test_canonical_geometry_has_explicit_srid(worker_settings: RuntimeSettings) -> None:
    run_worker(worker_settings)
    with connect_database(worker_settings.database) as connection:
        geometries = connection.execute(
            "SELECT DISTINCT ST_SRID(geom) AS srid, ST_IsValid(geom) AS valid, "
            "ST_NDims(geom) AS dimensions FROM iris.sites"
        ).fetchall()
    assert geometries == [{"srid": 4326, "valid": True, "dimensions": 2}]
