import json
import os
from pathlib import Path
from typing import Any

import pytest

from iris_runtime.config import DatabaseSettings, RuntimeSettings, worker_credentials
from iris_runtime.database import connect_database
from iris_runtime.migrations import migrate_database

FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def source_payload() -> dict[str, Any]:
    return json.loads((FIXTURE_DIRECTORY / "de-nw.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def runtime_settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        country_code="DE",
        region_code="NW",
        source_endpoint=(FIXTURE_DIRECTORY / "de-nw.json").as_uri(),
        output_path=tmp_path / "output",
        database=DatabaseSettings(
            host="unused", name="unused", user="test_worker", password="test-only"
        ),
    )


@pytest.fixture(scope="session")
def admin_database() -> DatabaseSettings:
    if os.environ.get("IRIS_TEST_DATABASE") != "1":
        pytest.skip("Run sh scripts/test.sh for isolated PostGIS integration tests")
    settings = DatabaseSettings.from_environment()
    if not settings.name.startswith("iris_test"):
        pytest.fail("Integration tests require a disposable database named iris_test*")
    username, password = worker_credentials()
    migrate_database(settings, username, password)
    return settings


@pytest.fixture
def clean_database(admin_database: DatabaseSettings) -> DatabaseSettings:
    with connect_database(admin_database) as connection:
        connection.execute("TRUNCATE iris.sites, iris.source_datasets")
    return admin_database


@pytest.fixture
def worker_settings(
    clean_database: DatabaseSettings, runtime_settings: RuntimeSettings
) -> RuntimeSettings:
    username, password = worker_credentials()
    return runtime_settings.model_copy(
        update={
            "database": clean_database.model_copy(update={"user": username, "password": password})
        }
    )
