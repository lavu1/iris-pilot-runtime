#!/bin/sh
# Exercise the actual Compose dependency graph, including the migration-failure gate.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
startup_prefix="iris-startup-$(date +%s)-$$"
active_project="$startup_prefix-success"
compose() {
    docker compose --env-file config/development.env.example -p "$active_project" "$@"
}
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose build worker
compose up -d worker
worker_id=$(compose ps --all --quiet worker)
test "$(docker wait "$worker_id")" = "0"
database_id=$(compose ps --all --quiet db)
test "$(docker inspect --format '{{.State.Health.Status}}' "$database_id")" = "healthy"
migration_id=$(compose ps --all --quiet migrate)
test "$(docker inspect --format '{{.State.ExitCode}}' "$migration_id")" = "0"
echo "Healthy database -> successful migrations -> successful worker: passed."
cleanup

active_project="$startup_prefix-blocked"
# Intentionally invalid role separation: migrations must fail and the worker must not start.
APP_DB_USER=${DB_ADMIN_USER:-iris_admin}
export APP_DB_USER
if compose up -d worker; then
    echo "ERROR: Startup unexpectedly succeeded with invalid migration configuration." >&2
    exit 1
fi
migration_id=$(compose ps --all --quiet migrate)
test "$(docker inspect --format '{{.State.ExitCode}}' "$migration_id")" != "0"
worker_id=$(compose ps --all --quiet worker)
if [ -n "$worker_id" ]; then
    test "$(docker inspect --format '{{.State.Status}}' "$worker_id")" = "created"
fi
echo "Failed migration prevents worker execution: passed."
