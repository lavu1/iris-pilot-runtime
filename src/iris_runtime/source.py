"""Bounded local fixture adapter; country and region must match the requested scope."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from iris_runtime.config import RuntimeSettings
from iris_runtime.contracts import SourceDataset
from iris_runtime.errors import RuntimeContractError

MAX_SOURCE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class LoadedSource:
    dataset: SourceDataset
    sha256: str


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeContractError("Source JSON contains duplicate object keys")
        result[key] = value
    return result


def load_source(settings: RuntimeSettings) -> LoadedSource:
    with settings.source_path.open("rb") as source_file:
        content = source_file.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise RuntimeContractError("Source exceeds the 5 MiB pilot limit")
    # Catch duplicate JSON keys before model validation can silently discard them.
    json.loads(content, object_pairs_hook=reject_duplicate_keys)
    dataset = SourceDataset.model_validate_json(content)
    if (dataset.contract.country_code, dataset.contract.region_code) != (
        settings.country_code,
        settings.region_code,
    ):
        raise RuntimeContractError("Source country/region differs from the configured scope")
    return LoadedSource(dataset=dataset, sha256=hashlib.sha256(content).hexdigest())
