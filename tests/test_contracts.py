import json
from typing import Any

import pytest
from pydantic import ValidationError

from iris_runtime.contracts import SourceDataset


def validate(payload: dict[str, Any]) -> SourceDataset:
    return SourceDataset.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "field",
    [
        "country_code",
        "region_code",
        "source_date",
        "crs",
        "coordinate_units",
        "completeness",
        "expected_feature_count",
        "uncertainty",
        "synthetic",
    ],
)
def test_missing_contract_fields_are_rejected(source_payload: dict[str, Any], field: str) -> None:
    del source_payload["contract"][field]
    with pytest.raises(ValidationError):
        validate(source_payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crs", "EPSG:3857"),
        ("coordinate_units", "metres"),
        ("country_code", "de"),
        ("source_date", "2026-02-30"),
        ("completeness", "partial"),
        ("uncertainty", ""),
        ("synthetic", False),
        ("expected_feature_count", "2"),
    ],
)
def test_invalid_metadata_is_rejected(
    source_payload: dict[str, Any], field: str, value: Any
) -> None:
    source_payload["contract"][field] = value
    with pytest.raises(ValidationError):
        validate(source_payload)


def test_complete_snapshot_count_is_enforced(source_payload: dict[str, Any]) -> None:
    source_payload["sites"].pop()
    with pytest.raises(ValidationError, match="Feature count"):
        validate(source_payload)


def test_duplicate_site_ids_are_rejected(source_payload: dict[str, Any]) -> None:
    source_payload["sites"][1]["site_id"] = source_payload["sites"][0]["site_id"]
    with pytest.raises(ValidationError, match="Duplicate"):
        validate(source_payload)


@pytest.mark.parametrize("position", [[181, 51], [7, -91], [7, 51, 0], [float("nan"), 51]])
def test_invalid_coordinate_positions_are_rejected(
    source_payload: dict[str, Any], position: list[float]
) -> None:
    source_payload["sites"][0]["geom"]["coordinates"][0][1] = position
    with pytest.raises(ValidationError):
        validate(source_payload)


def test_missing_geometry_is_rejected(source_payload: dict[str, Any]) -> None:
    del source_payload["sites"][0]["geom"]
    with pytest.raises(ValidationError):
        validate(source_payload)


def test_unclosed_ring_is_not_silently_repaired(source_payload: dict[str, Any]) -> None:
    source_payload["sites"][0]["geom"]["coordinates"][0].pop()
    with pytest.raises(ValidationError, match="closed"):
        validate(source_payload)


def test_unknown_attributes_are_not_silently_discarded(source_payload: dict[str, Any]) -> None:
    source_payload["sites"][0]["area"] = 100
    with pytest.raises(ValidationError, match="Extra inputs"):
        validate(source_payload)
