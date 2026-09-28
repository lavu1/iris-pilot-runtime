import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from iris_runtime.cli import main
from iris_runtime.config import DatabaseSettings, RuntimeSettings, worker_credentials
from iris_runtime.errors import RuntimeContractError
from iris_runtime.source import MAX_SOURCE_BYTES, load_source
from iris_runtime.worker import write_snapshot


def test_missing_environment_fails_clearly() -> None:
    with pytest.raises(RuntimeContractError, match="DB_HOST"):
        DatabaseSettings.from_environment({})


@pytest.mark.parametrize("endpoint", ["https://example.com/data", "relative.json", "file://host/a"])
def test_unsupported_endpoints_fail(runtime_settings: RuntimeSettings, endpoint: str) -> None:
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(
            {**runtime_settings.model_dump(), "source_endpoint": endpoint}
        )


def test_relative_output_path_fails(runtime_settings: RuntimeSettings) -> None:
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate({**runtime_settings.model_dump(), "output_path": "out"})


def test_password_is_redacted(runtime_settings: RuntimeSettings) -> None:
    assert "test-only" not in repr(runtime_settings)


def test_worker_cannot_reuse_admin_role() -> None:
    with pytest.raises(RuntimeContractError, match="differ"):
        worker_credentials({"APP_DB_USER": "admin", "DB_USER": "admin"})


def test_source_scope_must_match_configuration(runtime_settings: RuntimeSettings) -> None:
    with pytest.raises(RuntimeContractError, match="scope"):
        load_source(runtime_settings.model_copy(update={"country_code": "ZM"}))


def test_source_size_is_bounded(runtime_settings: RuntimeSettings, tmp_path: Path) -> None:
    source_file = tmp_path / "large.json"
    source_file.write_bytes(b" " * (MAX_SOURCE_BYTES + 1))
    settings = runtime_settings.model_copy(update={"source_endpoint": source_file.as_uri()})
    with pytest.raises(RuntimeContractError, match="5 MiB"):
        load_source(settings)


def test_duplicate_json_keys_are_rejected(
    runtime_settings: RuntimeSettings, tmp_path: Path
) -> None:
    source_file = tmp_path / "duplicate.json"
    source_file.write_text('{"contract": {}, "contract": {}}')
    settings = runtime_settings.model_copy(update={"source_endpoint": source_file.as_uri()})
    with pytest.raises(RuntimeContractError, match="duplicate object keys"):
        load_source(settings)


def test_invalid_output_preserves_existing_file(tmp_path: Path) -> None:
    output_file = tmp_path / "snapshot.json"
    output_file.write_text("existing")
    with pytest.raises(ValueError):
        write_snapshot(output_file, {"number": float("nan")})
    assert output_file.read_text() == "existing"
    assert list(tmp_path.glob(".iris-*")) == []


def test_cli_validation_does_not_echo_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key, value in {
        "COUNTRY_CODE": "secret-invalid-country",
        "REGION_CODE": "NW",
        "SOURCE_ENDPOINT": "file:///fixtures/data.json",
        "OUTPUT_PATH": "/output",
        "DB_HOST": "db",
        "DB_NAME": "iris",
        "DB_USER": "worker",
        "DB_PASSWORD": "sensitive-password",
    }.items():
        monkeypatch.setenv(key, value)
    assert main(["check-config"]) == 1
    output = capsys.readouterr().err
    assert "secret-invalid-country" not in output
    assert "sensitive-password" not in output
    assert json.loads(output)["event"] == "validation_failed"


def test_source_hash_is_stable(runtime_settings: RuntimeSettings) -> None:
    assert load_source(runtime_settings).sha256 == load_source(runtime_settings).sha256


def test_valid_source_is_loaded_without_inventing_fields(
    runtime_settings: RuntimeSettings, source_payload: dict[str, Any]
) -> None:
    assert load_source(runtime_settings).dataset.model_dump(mode="json") == source_payload
