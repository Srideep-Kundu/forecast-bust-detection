from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import polars as pl
from pyproj import Geod
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.validation import explain_validity

from .constants import GEOMETRY, GEOMETRY_COMMIT, WEIGHT_SUM_TOLERANCE
from .exceptions import ValidationError
from .hashing import sha256_file, write_json

SOURCE_FILES = ("indian_met_zones.v2.shp", "indian_met_zones.v2.shx", "indian_met_zones.v2.dbf", "indian_met_zones.v2.prj", "indian_met_zones.v2.qpj")
RAW_BASE = f"https://raw.githubusercontent.com/India-Meteorological-Department/Indian_met_zones/{GEOMETRY_COMMIT}"


def acquire_geometry(cache_dir: Path) -> tuple[Path, dict[str, str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in SOURCE_FILES:
        path = cache_dir / name
        if not path.exists():
            urllib.request.urlretrieve(f"{RAW_BASE}/{name}", path)
        hashes[name] = sha256_file(path)
    return cache_dir / SOURCE_FILES[0], hashes


def load_expected_manifest(path: Path | None = None) -> dict:
    path = path or GEOMETRY / "expected_regions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_and_canonicalize_geometry(
    source_path: Path,
    output_path: Path,
    report_path: Path,
    expected_manifest: dict,
    allow_make_valid: bool = True,
) -> tuple[gpd.GeoDataFrame, dict]:
    raw = gpd.read_file(source_path)
    required = {"cat", "ST_NM", "geometry"}
    if not required.issubset(raw.columns):
        raise ValidationError(f"Geometry columns={list(raw.columns)}; require={sorted(required)}")
    if raw.crs is None or raw.crs.to_epsg() != 4326:
        raise ValidationError(f"Geometry CRS={raw.crs}; expected EPSG:4326")
    expected = {int(item["id"]): item for item in expected_manifest["regions"]}
    actual = {int(row.cat): str(row.ST_NM) for row in raw.itertuples()}
    if len(raw) != expected_manifest["expected_count"] or len(actual) != len(raw):
        raise ValidationError(f"Geometry has {len(raw)} rows/{len(actual)} unique IDs; expected 36")
    if set(actual) != set(expected):
        raise ValidationError(f"Geometry IDs mismatch: actual={sorted(actual)}, expected={sorted(expected)}")
    name_mismatches = {rid: {"actual": actual[rid], "expected": expected[rid]["source_name"]} for rid in expected if actual[rid] != expected[rid]["source_name"]}
    if name_mismatches:
        raise ValidationError(f"Geometry source names mismatch: {name_mismatches}")

    invalid = [
        {"id": int(row.cat), "source_name": row.ST_NM, "reason": explain_validity(row.geometry)}
        for row in raw.itertuples()
        if not row.geometry.is_valid
    ]
    if invalid and not allow_make_valid:
        raise ValidationError(f"Invalid source geometry: {invalid}")
    canonical = raw.copy()
    if invalid:
        canonical.geometry = canonical.geometry.map(make_valid)
    if canonical.geometry.is_empty.any() or not canonical.geometry.is_valid.all():
        raise ValidationError("Canonical geometry remains empty or invalid after explicit make_valid")
    if not canonical.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValidationError(f"Unexpected geometry types: {canonical.geom_type.value_counts().to_dict()}")

    geod = Geod(ellps="WGS84")
    overlaps = []
    rows = list(canonical.itertuples())
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            intersection = left.geometry.intersection(right.geometry)
            if intersection.is_empty:
                continue
            area_km2 = abs(geod.geometry_area_perimeter(intersection)[0]) / 1_000_000.0
            if area_km2 > 1e-6:
                overlaps.append({"left_id": int(left.cat), "right_id": int(right.cat), "area_km2": area_km2})
    tolerance = float(expected_manifest["overlap_tolerance_km2"])
    excessive = [item for item in overlaps if item["area_km2"] > tolerance]
    if excessive:
        raise ValidationError(f"Subdivision overlap exceeds {tolerance} km2: {excessive}")

    canonical["region_id"] = canonical["cat"].astype(int)
    canonical["region_name"] = canonical["region_id"].map(lambda rid: expected[rid]["name"])
    canonical = canonical[["region_id", "region_name", "ST_NM", "geometry"]].sort_values("region_id")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_file(output_path, driver="GeoJSON")
    report = {
        "manifest_version": expected_manifest["manifest_version"],
        "source_commit": expected_manifest["source_commit"],
        "source_count": len(raw),
        "canonical_count": len(canonical),
        "crs": str(canonical.crs),
        "invalid_source_geometries": invalid,
        "repair_operation": "shapely.make_valid" if invalid else None,
        "topology_overlaps": overlaps,
        "overlap_tolerance_km2": tolerance,
        "canonical_geojson": str(output_path),
        "canonical_geojson_sha256": sha256_file(output_path),
    }
    write_json(report_path, report)
    return canonical, report


def _edges(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or np.any(np.diff(values) <= 0):
        raise ValidationError("Grid coordinates must contain at least two increasing values")
    mid = (values[:-1] + values[1:]) / 2
    return np.concatenate(([values[0] - (mid[0] - values[0])], mid, [values[-1] + (values[-1] - mid[-1])]))


def compute_region_weights(regions: gpd.GeoDataFrame, latitudes: np.ndarray, longitudes: np.ndarray) -> pl.DataFrame:
    lat_edges, lon_edges = _edges(latitudes), _edges(longitudes)
    geod = Geod(ellps="WGS84")
    rows: list[dict] = []
    for region in regions.itertuples():
        regional = []
        for yi, lat in enumerate(latitudes):
            for xi, lon in enumerate(longitudes):
                cell = Polygon(
                    [
                        (lon_edges[xi], lat_edges[yi]),
                        (lon_edges[xi + 1], lat_edges[yi]),
                        (lon_edges[xi + 1], lat_edges[yi + 1]),
                        (lon_edges[xi], lat_edges[yi + 1]),
                    ]
                )
                intersection = region.geometry.intersection(cell)
                if intersection.is_empty:
                    continue
                area_m2 = abs(geod.geometry_area_perimeter(intersection)[0])
                if np.isfinite(area_m2) and area_m2 > 0:
                    regional.append({"region_id": int(region.region_id), "region_name": region.region_name, "latitude": float(lat), "longitude": float(lon), "area_m2": area_m2})
        if not regional:
            raise ValidationError(f"Region {region.region_id} has no intersecting grid cells")
        total = sum(item["area_m2"] for item in regional)
        for item in regional:
            item["weight"] = item["area_m2"] / total
            rows.append(item)
    result = pl.DataFrame(rows).sort(["region_id", "latitude", "longitude"])
    sums = result.group_by("region_id").agg(pl.col("weight").sum().alias("weight_sum"))
    bad = sums.filter((pl.col("weight_sum") - 1.0).abs() > WEIGHT_SUM_TOLERANCE)
    if bad.height:
        raise ValidationError(f"Region weights do not sum to one: {bad.to_dicts()}")
    return result
