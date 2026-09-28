# IRIS-CAND-09 acceptance evidence

Rechecked against both pages of the supplied assignment on 28 September 2026.
Source PDF SHA-256: `708be4351d693f3a0afeb0ce122973240f7f913cd4c3fc98fcae2807ff6799c5`.

Verified locally on 28 September 2026 with Docker Engine 29.8.0, Compose 5.5.1,
Python 3.12.14 in containers, PostgreSQL 16.9, and PostGIS 3.5.2.
The host is an Apple Silicon Mac; the database uses AMD64 emulation.

| Assignment requirement | Implementation | Verification |
| --- | --- | --- |
| Portable Compose stack | Digest-pinned Python/PostGIS images; named volumes; relative fixture mount | Documented Docker smoke command passed |
| Configuration discipline | Validated environment settings; DE/NW and ten Southern African examples | All ten country smoke configurations passed on fresh volumes without business logic edits; output paths and database names vary |
| Healthy database before work | TCP health check and Compose dependency conditions | Normal worker completed after migrations; deliberately failing migration left worker unstarted |
| Deterministic migrations | Ordered SQL, transaction, advisory lock, checksum ledger | Replay, concurrent migrators, tampered history, and failed DDL tested |
| Geometry correctness | Required `geom`; 2D EPSG:4326 polygons; PostGIS checks | Invalid polygon rolls back the entire replacement; SRID and validity checked |
| Country-scoped business entities | Composite primary/foreign keys and scoped joins | All eleven countries coexist with identical region/source/site IDs; replacing ZA leaves all other countries unchanged; cross-country FK and null country rejected |
| Explicit source contracts | Required CRS, units, date, uncertainty, completeness and synthetic status | Missing/invalid metadata, duplicates and incomplete snapshots rejected |
| No baked-in secrets | Allowlisted build context, ignored local env, runtime credentials | Inspected image environment; no database credentials present |
| Restricted execution | Non-root UID 10001, read-only root, dropped capabilities; restricted DB role | Container settings inspected; schema/history mutations denied to worker |
| Local deterministic fixtures | Eleven small invented datasets (22 sites), no remote API | Byte-identical replay and database/output agreement checked |
| Documentation and CLI | README, `check-config`, `migrate`, `run`, `smoke` | Local editable installation, CLI and wheel packaging verified; wheel contains SQL migrations |

## Automated checks

- Real PostGIS suite: **76 tests passed**, including 25 integration cases.
- Host unit suite: **51 tests passed**.
- Ruff lint and formatting checks: passed.
- Strict mypy checks: passed for all 12 application source files.
- Installed Python dependency compatibility check: passed.
- Ten Southern African Docker smoke configurations: passed, each on fresh volumes.
- Compose startup success and deliberately failed migration gate: passed.
- Git staging scan: local credentials, private key/token patterns, virtualenv and IDE files excluded.

The local country matrix covers Angola, Botswana, Eswatini, Lesotho, Malawi, Mozambique,
Namibia, South Africa, Zambia, and Zimbabwe. Germany remains the original DE/NW baseline.
`DEMO` denotes a synthetic region, not a verified administrative boundary. These tests prove
configuration portability and isolation; they do not establish real-world geographic suitability.

Local second-host examples run as separate Compose projects on the Mac. The
[GitHub Actions workflow](https://github.com/lavu1/iris-pilot-runtime/actions/workflows/ci.yml)
reports the independent Ubuntu checks for each published commit. Production performance,
vulnerability scanning, live-source integration, and business suitability are not claimed.

The implementation covers the portable runtime assignment. The next phase remains the
broader IRIS product work described in the README.
