#!/bin/sh
# Integration tests get fresh project-scoped volumes, never the developer's pilot database.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DB_NAME=iris_tests
export DB_NAME
test_project="iris-test-$(date +%s)-$$"
compose() {
    docker compose --env-file config/development.env.example -p "$test_project" "$@"
}
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose build tests
compose up -d --wait db
compose run --rm --no-deps tests
