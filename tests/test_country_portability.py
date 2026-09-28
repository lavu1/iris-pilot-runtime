"""Exercise every committed country fixture without country-specific business logic."""

import json
from pathlib import Path

import pytest

from iris_runtime.config import RuntimeSettings
from iris_runtime.contracts import SourceDataset
from iris_runtime.database import connect_database
from iris_runtime.repository import read_source_snapshot
from iris_runtime.smoke import run_smoke_test
from iris_runtime.source import load_source
from iris_runtime.worker import run_worker

FIXTURE_FILES = sorted((Path(__file__).resolve().parents[1] / "fixtures").glob("*.json"))


def settings_for_fixture(settings: RuntimeSettings, source_file: Path) -> RuntimeSettings:
    contract = SourceDataset.model_validate_json(source_file.read_bytes()).contract
    return RuntimeSettings.model_validate(
        {
            **settings.model_dump(),
            "country_code": contract.country_code,
            "region_code": contract.region_code,
            "source_endpoint": source_file.as_uri(),
        }
    )


@pytest.mark.parametrize("source_file", FIXTURE_FILES, ids=lambda path: path.stem)
def test_country_fixture_satisfies_explicit_source_contract(
    runtime_settings: RuntimeSettings, source_file: Path
) -> None:
    source = load_source(settings_for_fixture(runtime_settings, source_file))
    assert source.dataset.contract.synthetic is True
    assert len(source.dataset.sites) == source.dataset.contract.expected_feature_count == 2


@pytest.mark.integration
@pytest.mark.parametrize("source_file", FIXTURE_FILES, ids=lambda path: path.stem)
def test_country_runs_and_replays_with_configuration_only(
    worker_settings: RuntimeSettings, source_file: Path
) -> None:
    settings = settings_for_fixture(worker_settings, source_file)
    result = run_smoke_test(settings)
    assert result["event"] == "smoke_passed"
    assert result["country_code"] == settings.country_code
    assert result["region_code"] == settings.region_code
    assert result["feature_count"] == 2
    assert result["replay_identical"] is True


@pytest.mark.integration
def test_country_isolation_with_identical_region_source_and_site_ids(
    worker_settings: RuntimeSettings, tmp_path: Path
) -> None:
    snapshots: dict[str, dict[str, object]] = {}
    country_settings: dict[str, RuntimeSettings] = {}
    for source_file in FIXTURE_FILES:
        payload = json.loads(source_file.read_text())
        payload["contract"]["region_code"] = "SHARED_DEMO"
        country_code = payload["contract"]["country_code"]
        scoped_fixture = tmp_path / f"{country_code}.json"
        scoped_fixture.write_text(json.dumps(payload))
        settings = settings_for_fixture(worker_settings, scoped_fixture)
        result = run_worker(settings)
        snapshots[country_code] = json.loads(result.output_file.read_text())
        country_settings[country_code] = settings

    assert len(snapshots) == len(FIXTURE_FILES) == 11
    with connect_database(worker_settings.database) as connection:
        rows = connection.execute(
            "SELECT country_code, count(*) AS count FROM iris.sites "
            "GROUP BY country_code ORDER BY country_code"
        ).fetchall()
        assert {row["country_code"]: row["count"] for row in rows} == {
            country: 2 for country in snapshots
        }
        for country_code, expected in snapshots.items():
            assert (
                read_source_snapshot(connection, country_code, "SHARED_DEMO", "pilot-fixture")
                == expected
            )

    # Replacing one country's complete snapshot must leave every other country unchanged.
    replacement_file = country_settings["ZA"].source_path
    replacement = json.loads(replacement_file.read_text())
    replacement["sites"].pop()
    replacement["contract"]["expected_feature_count"] = 1
    replacement_file.write_text(json.dumps(replacement))
    run_worker(country_settings["ZA"])
    with connect_database(worker_settings.database) as connection:
        for country_code, expected in snapshots.items():
            actual = read_source_snapshot(connection, country_code, "SHARED_DEMO", "pilot-fixture")
            if country_code == "ZA":
                assert len(actual["sites"]) == 1
            else:
                assert actual == expected
