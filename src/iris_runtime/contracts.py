"""Strict source contract: missing values are errors, never inferred geospatial facts."""

import math
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceContract(ContractModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    region_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
    source_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    source_date: date
    crs: Literal["EPSG:4326"]
    coordinate_units: Literal["degrees"]
    completeness: Literal["complete"]
    expected_feature_count: int = Field(ge=1, le=10000)
    uncertainty: str = Field(min_length=20, max_length=2000)
    synthetic: Literal[True]


class PolygonGeometry(ContractModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, rings: list[list[list[float]]]) -> list[list[list[float]]]:
        if not rings:
            raise ValueError("Polygon must contain at least one ring")
        for ring in rings:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Polygon rings must be closed with at least four positions")
            for position in ring:
                if len(position) != 2 or not all(math.isfinite(value) for value in position):
                    raise ValueError("Positions must contain exactly two finite coordinates")
                longitude, latitude = position
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError("Coordinates are outside EPSG:4326 longitude/latitude bounds")
        return rings


class SourceSite(ContractModel):
    site_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    geom: PolygonGeometry

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Site name cannot be blank")
        return value


class SourceDataset(ContractModel):
    contract: SourceContract
    sites: list[SourceSite]

    @model_validator(mode="after")
    def validate_completeness(self) -> Self:
        if len(self.sites) != self.contract.expected_feature_count:
            raise ValueError("Feature count does not match the declared complete snapshot")
        if len({site.site_id for site in self.sites}) != len(self.sites):
            raise ValueError("Duplicate site identifiers in the same source snapshot")
        return self
