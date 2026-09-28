#!/bin/sh
# Every country gets fresh database/output volumes; only this script's projects are removed.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
matrix_prefix="iris-countries-$(date +%s)-$$"
active_project=
active_environment=
cleanup() {
    if [ -n "$active_project" ]; then
        docker compose --env-file "$active_environment" -p "$active_project" \
            down --volumes --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for active_environment in config/countries/*.env.example; do
    country=$(basename "$active_environment" .env.example)
    active_project="$matrix_prefix-$country"
    echo "Checking country: $country"
    COMPOSE_PROJECT_NAME="$active_project" sh scripts/smoke.sh "$active_environment"
    cleanup
    active_project=
done
echo "All 10 Southern African country configurations passed."
