CREATE TABLE iris.source_datasets (
    country_code text NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    region_code text NOT NULL CHECK (region_code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    source_id text NOT NULL CHECK (source_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'),
    source_date date NOT NULL,
    crs text NOT NULL CHECK (crs = 'EPSG:4326'),
    coordinate_units text NOT NULL CHECK (coordinate_units = 'degrees'),
    completeness text NOT NULL CHECK (completeness = 'complete'),
    expected_feature_count integer NOT NULL CHECK (expected_feature_count BETWEEN 1 AND 10000),
    uncertainty text NOT NULL CHECK (length(btrim(uncertainty)) BETWEEN 20 AND 2000),
    synthetic boolean NOT NULL CHECK (synthetic),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (country_code, region_code, source_id)
);
