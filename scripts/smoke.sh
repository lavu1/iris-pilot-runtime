#!/bin/sh
# Usage: sh scripts/smoke.sh [config/development.env.example]
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
environment_file=${1:-.env}
if [ ! -f "$environment_file" ]; then
    echo "Missing env file. Copy config/development.env.example to .env first." >&2
    exit 1
fi
docker compose --env-file "$environment_file" build worker
docker compose --env-file "$environment_file" up -d --wait db
# Explicitly rerun migrations on every invocation, including existing database volumes.
docker compose --env-file "$environment_file" run --rm --no-deps migrate
docker compose --env-file "$environment_file" run --rm --no-deps smoke
