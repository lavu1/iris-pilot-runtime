"""Exercise source validation, ingestion, database readback, output, and idempotent replay."""

import json
from typing import Any

from iris_runtime.config import RuntimeSettings
from iris_runtime.database import connect_database, verify_database_versions
from iris_runtime.errors import RuntimeContractError
from iris_runtime.repository import read_source_snapshot
from iris_runtime.source import load_source
from iris_runtime.worker import run_worker


def run_smoke_test(settings: RuntimeSettings) -> dict[str, Any]:
    source = load_source(settings)
    first_run = run_worker(settings)
    first_output = first_run.output_file.read_bytes()
    second_run = run_worker(settings)
    if first_output != second_run.output_file.read_bytes():
        raise RuntimeContractError("Replaying the source changed the output")
    with connect_database(settings.database) as connection:
        versions = verify_database_versions(connection)
        persisted = read_source_snapshot(
            connection,
            settings.country_code,
            settings.region_code,
            source.dataset.contract.source_id,
        )
    if persisted != json.loads(first_output) or persisted["source_sha256"] != source.sha256:
        raise RuntimeContractError("Output does not match the persisted source snapshot")
    return {
        "event": "smoke_passed",
        "country_code": settings.country_code,
        "region_code": settings.region_code,
        "feature_count": second_run.feature_count,
        "source_sha256": source.sha256,
        "output_file": str(second_run.output_file),
        "replay_identical": True,
        **versions,
    }
