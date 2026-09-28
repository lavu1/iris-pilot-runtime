# IRIS Pilot Runtime

**IRIS-CAND-09 — Portable Dockerized Pilot Runtime**

[![Runtime checks](https://github.com/lavu1/iris-pilot-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/lavu1/iris-pilot-runtime/actions/workflows/ci.yml)

A small, complete Python/PostGIS pilot: validate a synthetic source snapshot, persist
country-scoped polygons, and export the persisted result as deterministic JSON.
Country, region, source endpoint, database credentials, and output directory are configuration.

See [acceptance evidence](docs/ACCEPTANCE.md) for the requirement-to-test mapping and
the limits of the local verification.

## Quick start

From a clean checkout, with Docker running:

```sh
cp config/development.env.example .env
sh scripts/smoke.sh
```

Success ends with a JSON event containing `"event": "smoke_passed"`,
`"feature_count": 2`, and `"replay_identical": true`. The command builds the image,
waits for the database, applies migrations, runs ingestion twice, and verifies database
readback against the exported file. First run needs internet to download images and packages;
the running stack uses only committed local fixtures and an internal Docker network.

The ordinary worker follows the same dependency chain:

```sh
docker compose up --build -d worker
docker compose logs migrate worker
docker compose ps -a
```

`migrate` and `worker` are finite jobs: **Exited (0) is success**, not a crash.
Use the smoke script to deliberately reapply migrations and replay ingestion after changes.

Export the result from the named volume into a local folder:

```sh
mkdir -p outputs
docker compose cp worker:/output/DE/NW/pilot-fixture.json outputs/de-nw.json
```

The `worker` container is created by `docker compose up -d worker` above; copying works
after it exits. Files contain the source contract, exact input SHA-256, and sites read back
from PostGIS. There are no invented areas, ownership claims, scores, or wall-clock timestamps.

Stop containers while keeping database and output volumes:

```sh
docker compose down
```

Only for an intentional reset of this pilot's data, add `--volumes` to that command.
Do not use global Docker pruning commands.

## A second host or country

Copy the entire checkout to a compatible Docker host and run:

```sh
sh scripts/smoke.sh config/second-host.env.example
```

This uses **ZM / LSK**, another fixture, another database name, a different output
directory, and an independent Compose project. No Python or SQL edits are needed.
It can also run alongside DE / NW on the same machine, without host port conflicts.
The two supplied fixtures intentionally share source and site IDs to exercise country scoping.
To inspect or stop this stack, use the same `--env-file config/second-host.env.example`
argument on every `docker compose` command.

### Southern African examples

Ten runnable country examples cover Angola (`AO`), Botswana (`BW`), Eswatini (`SZ`),
Lesotho (`LS`), Malawi (`MW`), Mozambique (`MZ`), Namibia (`NA`), South Africa (`ZA`),
Zambia (`ZM`), and Zimbabwe (`ZW`). Germany (`DE/NW`) remains the assignment baseline.
For example, run South Africa using the same application image and business logic:

```sh
sh scripts/smoke.sh config/countries/za.env.example
```

Each file under `config/countries/` is a complete standalone env template. The new fixtures
use `DEMO` as an explicitly synthetic region label, not an official administrative code.
Coordinates and site names are invented, not verified parcels or boundary datasets.
The integration suite additionally gives **all eleven countries identical region, source,
and site identifiers** in one database and verifies that replacing one country leaves
every other country unchanged.

Run every Southern African configuration on fresh, automatically cleaned-up volumes:

```sh
sh scripts/test-countries.sh
```

## Host assumptions

- Docker Engine with **Compose v2.20+** (Compose v5 also works); Linux containers.
- A POSIX shell for the helper scripts (macOS/Linux terminal, or WSL on Windows).
- x86-64 Linux, or Docker Desktop on macOS/Windows. The pinned upstream PostGIS
  image is AMD64; Apple Silicon requires Docker Desktop's x86-64 emulation.
  Python runs natively on ARM64. Native ARM PostGIS is a future deployment option.
- Recommended development allocation: 4 CPU cores, 4 GB Docker memory, and 5 GB
  free disk for this small pilot and build cache. These are planning allowances,
  not a measured production capacity claim.
- Docker can read the checkout's `fixtures` directory. On Linux, retain its normal
  readable permissions. Named volumes avoid host-user ownership requirements for output.
- No host PostgreSQL, Python, paid API, cloud account, or production credentials are required.
- Docker must already be installed; the project never installs system packages on its host.

## Configuration

Compose reads `.env`, or the explicitly selected `--env-file`. Exported shell variables
take precedence over values in the env file; unset stale overrides when switching examples.
Python reads the explicitly passed process environment, not an implicit `.env` search.

| Variable | Meaning |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Container/network/volume namespace; use a different name for independent stacks |
| `COUNTRY_CODE` | Required uppercase two-letter country identifier, e.g. `DE` or `ZM` |
| `REGION_CODE` | Required configured region, e.g. `NW` or `LSK`; matches the source exactly |
| `SOURCE_ENDPOINT` | Absolute `file:///fixtures/...json` URI inside the container |
| `FIXTURE_PATH` | Host fixture directory; relative paths resolve against the Compose file |
| `OUTPUT_PATH` | Container output directory: `/output` or a directory below `/output` |
| `DB_NAME` | Database initialized in this Compose project's data volume |
| `DB_ADMIN_USER`, `DB_ADMIN_PASSWORD` | Database bootstrap/migration credentials |
| `APP_DB_USER`, `APP_DB_PASSWORD` | Separate restricted ingestion worker credentials |

Compose supplies `DB_HOST=db`, `DB_PORT=5432`, `DB_USER`, and `DB_PASSWORD` to each
Python service. Direct Python execution can configure all four through its environment.
`OUTPUT_PATH` must be absolute; the supplied container mounts writable storage at `/output`.
Other paths in the read-only container will fail. A missing fixture bind path fails immediately
instead of Docker silently creating an empty directory.

The example passwords are public, disposable **local demo values**, not secrets or
production credentials. Copy templates to ignored env files and replace passwords before
sharing a deployment. Passwords are runtime environment values, never image build arguments.
Changing the administrator password in an env file does **not** change an existing PostgreSQL
volume's password: rotate it in the database or intentionally recreate a disposable volume.
The migration job applies worker password updates using its existing admin credentials.

## Architecture and startup

```text
PostgreSQL/PostGIS healthy
          |
          v
migrate: advisory lock -> checksummed SQL -> worker grants -> commit
          | successful exit
          v
worker: validate fixture -> transactional replacement -> DB readback -> atomic JSON export
```

`service_healthy` gates database consumers; `service_completed_successfully` gates the
worker on migrations. The database health check uses TCP so the bootstrap-only local
PostgreSQL server cannot prematurely release consumers.

Python modules have one responsibility:

| Module | Responsibility |
| --- | --- |
| `config.py` | Explicit environment parsing and secret-redacted settings |
| `contracts.py` | Strict source metadata and polygon structure |
| `source.py` | Bounded local-file loading, scope matching, duplicate-key rejection, SHA-256 |
| `database.py` | Connections, timeouts, supported version checks |
| `migrations.py`, `sql/` | Ordered, immutable SQL and restricted worker provisioning |
| `repository.py` | Country-scoped snapshot replacement and readback |
| `worker.py` | Transaction orchestration and atomic file publication |
| `smoke.py`, `cli.py` | End-to-end verification and reproducible commands |

Names use PEP 8 `snake_case` functions and `PascalCase` classes. Public boundaries are typed;
Ruff, mypy, and pytest are executable checks rather than documentation-only conventions.

### Data contract

The JSON fixture envelope has `contract` and `sites` keys; it is not a complete GeoJSON
FeatureCollection. Each site's `geom` is a GeoJSON Polygon geometry fragment.

- Required metadata: country, region, source identifier/date, CRS, units, completeness,
  expected count, synthetic status, and an explicit uncertainty statement.
- Pilot adapter accepts complete synthetic snapshots, EPSG:4326, degrees, and 2D
  longitude/latitude polygons only. Missing fields, unknown attributes, duplicate JSON
  keys/IDs, empty datasets, unclosed rings, nonfinite/out-of-range coordinates, or more
  than 5 MiB of input fail. No automatic CRS assignment to unknown data, transformation,
  geocoding, geometry repair, or missing-attribute defaults are performed.
- PostGIS performs topology validation. Invalid polygons fail the entire transaction.
- `iris.source_datasets` uses `(country_code, region_code, source_id)` as its primary key.
  `iris.sites` adds `site_id`; its foreign key and every join carry the full source scope.
  Every business row has a non-null `country_code`. The migration ledger is infrastructure
  metadata, not a business entity.
- `geom geometry(Polygon,4326)` is canonical, non-null, nonempty, valid, and bounds-checked.
  Geometry has a GiST index. No area calculations are performed in angular degrees.
- A complete source snapshot replaces only its own country/region/source records, removing
  sites absent from the new snapshot. Other scopes remain intact. Source checksums identify
  input bytes; reformatting JSON changes the checksum even if its semantics are unchanged.
- Exported geometry is serialized by PostGIS to 15 decimal places; database geometry retains
  its stored precision. Output is sorted and deterministic for a fixed fixture/runtime.

### Reliability and security

SQL files are packaged with the application. All pending migrations run in one transaction
under a PostgreSQL advisory lock. The ledger records file names and SHA-256 checksums.
Changed/missing historical files and gaps fail explicitly; add a new numbered migration
instead of editing an applied file. Application tables are not initialized only through
`docker-entrypoint-initdb.d`, so migrations also work with an existing volume.

The worker uses a non-superuser role granted only schema usage and data manipulation on
the two business tables. It cannot create/alter tables or modify migration history. This is
a local trusted pilot: country-scoped keys prevent accidental cross-country association;
they are **not tenant authorization**. Production multi-tenant access needs separate roles
or row-level security. Bootstrap administration is confined to the database and migration job.

Application containers run as UID/GID 10001, with a read-only root filesystem, dropped
capabilities, and no privilege escalation. Fixtures are read-only, the database has no published
port, and runtime networking is internal. Build context is allowlisted; local env files,
IDE metadata, virtual environments, and outputs are excluded. Exceptions do not print
credentials, DSNs, or raw source values. Docker administrators can still inspect container
environment values; production should use an external secret manager and TLS.

Each snapshot is replaced in one transaction. The database commits before export; export uses
a temporary file and atomic rename so readers never see a partial file. Database and filesystem
are not a distributed transaction: an export failure returns nonzero and replay regenerates it.
An advisory lock serializes writers of the same scope through file publication, including
the interval after database commit. Closing the connection releases it even on failure.
Connection and SQL/lock timeouts bound failures. No background retries conceal an error.

## Tests and code checks

Docker-only integration suite, with a unique disposable Compose project and automatic cleanup:

```sh
sh scripts/test.sh
```

It covers country isolation, foreign keys, SRID, invalid-geometry rollback, snapshot replay,
restricted worker privileges, migration checksums/rollback/concurrency, source contracts,
and credential-safe CLI errors. It never targets the normal development database.

Test Compose startup ordering and a deliberately failed migration using disposable stacks:

```sh
sh scripts/test-startup.sh
```

For PyCharm/local Python development, select a Python 3.12+ interpreter and create `.venv`
if the IDE has not already done so:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest -m 'not integration' --cov=iris_runtime
```

Integration tests skip in a plain host run; `scripts/test.sh` runs them against real PostGIS.
The GitHub Actions workflow runs the same quality gates and both country smoke paths.
No workflow needs production secrets. Dependency hashes and image digests are pinned;
refresh them deliberately and rerun the checks when updating.

CLI commands: `python -m iris_runtime check-config`, `migrate`, `run`, and `smoke`.
`check-config` validates configuration and the source without connecting to PostgreSQL;
topological geometry validation still requires PostGIS. CLI failure exits with code 1,
argument misuse with 2, and success with 0. Database errors report SQLSTATE without
raw queries or input data; e.g. `23514` is a failed check constraint and `28P01` is authentication.

## Deliberate scope and next phase

This implements the portable runtime assignment, not the entire IRIS product. Source input
is a committed local mock adapter, not a live API. There is no HTTP service, UI, scheduler,
certified compensation estimate, spatial screening model, or prospecting PDF generator.
The fixtures are invented examples, not real parcels or verified country/region boundaries.

Production evolution: authenticated source adapters with retry/provenance rules; approved
CRS transformations and stronger country reference validation; tenant authorization; an
outbox/export worker; secret management and TLS; backup/restore testing; monitoring;
resource/load tests; and image/dependency vulnerability scanning. These need separate
requirements and do not change the pilot's business logic when moving hosts.

## Design references

- Assignment IRIS-CAND-09: Portable Dockerized Pilot Runtime, provided separately.
- [Docker Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)
- [Upstream PostGIS image support](https://github.com/postgis/docker-postgis)
- [PostGIS geometry parsing](https://postgis.net/docs/ST_GeomFromGeoJSON.html)
  and [validity checks](https://postgis.net/docs/ST_IsValid.html)
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [PEP 8 naming conventions](https://peps.python.org/pep-0008/#naming-conventions)
