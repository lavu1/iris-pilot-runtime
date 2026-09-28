"""Replace one declared complete snapshot atomically, with all joins scoped by country."""

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from iris_runtime.errors import RuntimeContractError
from iris_runtime.source import LoadedSource


def replace_source_snapshot(
    connection: psycopg.Connection[dict[str, Any]], source: LoadedSource
) -> dict[str, Any]:
    contract = source.dataset.contract
    scope = (contract.country_code, contract.region_code, contract.source_id)
    # Serialize writers of this snapshot; a hash collision only causes additional waiting.
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (json.dumps(scope),)
    )
    connection.execute(
        "INSERT INTO iris.source_datasets "
        "(country_code, region_code, source_id, source_date, crs, coordinate_units, "
        "completeness, expected_feature_count, uncertainty, synthetic, source_sha256) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (country_code, region_code, source_id) DO UPDATE SET "
        "source_date = EXCLUDED.source_date, crs = EXCLUDED.crs, "
        "coordinate_units = EXCLUDED.coordinate_units, completeness = EXCLUDED.completeness, "
        "expected_feature_count = EXCLUDED.expected_feature_count, "
        "uncertainty = EXCLUDED.uncertainty, synthetic = EXCLUDED.synthetic, "
        "source_sha256 = EXCLUDED.source_sha256",
        (
            *scope,
            contract.source_date,
            contract.crs,
            contract.coordinate_units,
            contract.completeness,
            contract.expected_feature_count,
            contract.uncertainty,
            contract.synthetic,
            source.sha256,
        ),
    )
    connection.execute(
        "DELETE FROM iris.sites WHERE country_code = %s AND region_code = %s AND source_id = %s",
        scope,
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO iris.sites (country_code, region_code, source_id, site_id, name, geom) "
            "VALUES (%s, %s, %s, %s, %s, ST_GeomFromGeoJSON(%s::jsonb))",
            [
                (*scope, site.site_id, site.name, Jsonb(site.geom.model_dump()))
                for site in source.dataset.sites
            ],
        )
    return read_source_snapshot(connection, *scope)


def read_source_snapshot(
    connection: psycopg.Connection[dict[str, Any]],
    country_code: str,
    region_code: str,
    source_id: str,
) -> dict[str, Any]:
    scope = (country_code, region_code, source_id)
    dataset = connection.execute(
        "SELECT * FROM iris.source_datasets "
        "WHERE country_code = %s AND region_code = %s AND source_id = %s",
        scope,
    ).fetchone()
    if dataset is None:
        raise RuntimeContractError("The requested source snapshot does not exist")
    sites = connection.execute(
        "SELECT s.site_id, s.name, ST_AsGeoJSON(s.geom, 15)::jsonb AS geom "
        "FROM iris.sites AS s JOIN iris.source_datasets AS d "
        "ON s.country_code = d.country_code AND s.region_code = d.region_code "
        "AND s.source_id = d.source_id "
        "WHERE d.country_code = %s AND d.region_code = %s AND d.source_id = %s "
        "ORDER BY s.site_id",
        scope,
    ).fetchall()
    if len(sites) != dataset["expected_feature_count"]:
        raise RuntimeContractError("Persisted feature count differs from the source contract")
    source_sha256 = dataset.pop("source_sha256")
    dataset["source_date"] = dataset["source_date"].isoformat()
    return {"contract": dataset, "source_sha256": source_sha256, "sites": sites}
