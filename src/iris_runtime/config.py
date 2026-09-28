"""Read only named environment variables; never build or log credential-bearing URLs."""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from iris_runtime.errors import RuntimeContractError


def required_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value.strip():
        raise RuntimeContractError(f"Required environment variable is missing: {name}")
    return value


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: SecretStr
    connect_timeout_seconds: int = Field(default=10, ge=1, le=60)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "DatabaseSettings":
        environment = os.environ if environment is None else environment
        return cls.model_validate(
            {
                "host": required_value(environment, "DB_HOST"),
                "port": environment.get("DB_PORT", "5432"),
                "name": required_value(environment, "DB_NAME"),
                "user": required_value(environment, "DB_USER"),
                "password": required_value(environment, "DB_PASSWORD"),
            }
        )


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    region_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
    source_endpoint: str
    output_path: Path
    database: DatabaseSettings

    @field_validator("source_endpoint")
    @classmethod
    def validate_source_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "file"
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not Path(unquote(parsed.path)).is_absolute()
        ):
            raise ValueError("SOURCE_ENDPOINT must be an absolute file:/// URI")
        return value

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("OUTPUT_PATH must be an absolute directory path")
        return value

    @property
    def source_path(self) -> Path:
        return Path(unquote(urlsplit(self.source_endpoint).path))

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "RuntimeSettings":
        environment = os.environ if environment is None else environment
        return cls(
            country_code=required_value(environment, "COUNTRY_CODE"),
            region_code=required_value(environment, "REGION_CODE"),
            source_endpoint=required_value(environment, "SOURCE_ENDPOINT"),
            output_path=Path(required_value(environment, "OUTPUT_PATH")),
            database=DatabaseSettings.from_environment(environment),
        )


def worker_credentials(environment: Mapping[str, str] | None = None) -> tuple[str, SecretStr]:
    environment = os.environ if environment is None else environment
    username = required_value(environment, "APP_DB_USER")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", username) or username.startswith("pg_"):
        raise RuntimeContractError("APP_DB_USER must be a non-reserved lowercase SQL identifier")
    if username == required_value(environment, "DB_USER"):
        raise RuntimeContractError("APP_DB_USER must differ from the migration administrator")
    return username, SecretStr(required_value(environment, "APP_DB_PASSWORD"))
