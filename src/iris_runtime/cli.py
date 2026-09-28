"""Small reproducible CLI with machine-readable, credential-safe status messages."""

import argparse
import json
import sys
from collections.abc import Sequence

import psycopg
from pydantic import ValidationError

from iris_runtime.config import DatabaseSettings, RuntimeSettings, worker_credentials
from iris_runtime.errors import RuntimeContractError
from iris_runtime.migrations import migrate_database
from iris_runtime.smoke import run_smoke_test
from iris_runtime.source import load_source
from iris_runtime.worker import run_worker


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portable IRIS pilot runtime")
    parser.add_argument("command", choices=("migrate", "run", "smoke", "check-config"))
    args = parser.parse_args(arguments)
    try:
        if args.command == "migrate":
            username, password = worker_credentials()
            count = migrate_database(DatabaseSettings.from_environment(), username, password)
            print(json.dumps({"event": "migrations_applied", "count": count}))
            return 0
        settings = RuntimeSettings.from_environment()
        if args.command == "check-config":
            source = load_source(settings)
            print(json.dumps({"event": "configuration_valid", "sha256": source.sha256}))
        elif args.command == "smoke":
            print(json.dumps(run_smoke_test(settings), sort_keys=True))
        else:
            result = run_worker(settings)
            print(
                json.dumps(
                    {
                        "event": "worker_completed",
                        "country_code": settings.country_code,
                        "region_code": settings.region_code,
                        "feature_count": result.feature_count,
                        "output_file": str(result.output_file),
                        "source_sha256": result.source_sha256,
                    }
                )
            )
        return 0
    except ValidationError as error:
        # Pydantic's default text includes original input; do not expose passwords or source data.
        problems = [
            {"field": ".".join(map(str, item["loc"])), "reason": item["type"]}
            for item in error.errors(include_input=False, include_context=False)
        ]
        print(json.dumps({"event": "validation_failed", "problems": problems}), file=sys.stderr)
    except psycopg.Error as error:
        print(json.dumps({"event": "database_failed", "sqlstate": error.sqlstate}), file=sys.stderr)
    except RuntimeContractError as error:
        print(json.dumps({"event": "contract_failed", "reason": str(error)}), file=sys.stderr)
    except (OSError, ValueError) as error:
        print(
            json.dumps({"event": "input_or_output_failed", "reason": type(error).__name__}),
            file=sys.stderr,
        )
    return 1
