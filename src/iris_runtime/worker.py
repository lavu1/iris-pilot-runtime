"""Execute one finite ingestion job and publish a deterministic JSON snapshot."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_runtime.config import RuntimeSettings
from iris_runtime.database import connect_database, verify_database_versions
from iris_runtime.repository import replace_source_snapshot
from iris_runtime.source import load_source


@dataclass(frozen=True)
class RunResult:
    output_file: Path
    feature_count: int
    source_sha256: str


def write_snapshot(output_file: Path, snapshot: dict[str, Any]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_file.parent, prefix=".iris-", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(snapshot, temporary_file, indent=2, sort_keys=True, allow_nan=False)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_file)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run_worker(settings: RuntimeSettings) -> RunResult:
    source = load_source(settings)
    with connect_database(settings.database) as connection:
        contract = source.dataset.contract
        scope = (contract.country_code, contract.region_code, contract.source_id)
        # Hold the same writer lock through file publication, even after the database commit.
        # Closing the connection releases this session lock on success and failure alike.
        connection.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (json.dumps(scope),))
        verify_database_versions(connection)
        snapshot = replace_source_snapshot(connection, source)
        connection.commit()
        output_file = (
            settings.output_path
            / settings.country_code
            / settings.region_code
            / f"{source.dataset.contract.source_id}.json"
        )
        # Database commits first. A failed export returns nonzero; replay safely regenerates it.
        write_snapshot(output_file, snapshot)
    return RunResult(output_file, len(source.dataset.sites), source.sha256)
