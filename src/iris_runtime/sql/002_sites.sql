CREATE TABLE iris.sites (
    country_code text NOT NULL,
    region_code text NOT NULL,
    source_id text NOT NULL,
    site_id text NOT NULL CHECK (site_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    geom geometry(Polygon, 4326) NOT NULL,
    PRIMARY KEY (country_code, region_code, source_id, site_id),
    FOREIGN KEY (country_code, region_code, source_id)
        REFERENCES iris.source_datasets (country_code, region_code, source_id),
    CONSTRAINT sites_geom_valid CHECK (ST_IsValid(geom)),
    CONSTRAINT sites_geom_nonempty CHECK (NOT ST_IsEmpty(geom)),
    CONSTRAINT sites_geom_bounds CHECK (
        ST_XMin(Box3D(geom)) >= -180 AND ST_XMax(Box3D(geom)) <= 180
        AND ST_YMin(Box3D(geom)) >= -90 AND ST_YMax(Box3D(geom)) <= 90
    )
);

CREATE INDEX sites_geom_gist ON iris.sites USING gist (geom);
