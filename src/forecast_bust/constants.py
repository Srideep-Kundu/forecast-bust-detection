import os
from pathlib import Path

DATASET_VERSION = "wb2-ifs-mean-india-v2"
FEATURE_CONTRACT_VERSION = "mean-only-mvp-v2"
LEAD_HOURS = (24, 48, 72, 96, 120, 144, 168, 192, 216, 240)
MONSOON_MONTHS = (6, 7, 8, 9)
INDIA_BOUNDS = {"latitude_min": 6.0, "latitude_max": 38.0, "longitude_min": 68.0, "longitude_max": 98.0}
G0 = 9.80665
EARTH_RADIUS_M = 6_371_008.8
GRID_TOLERANCE_DEG = 1e-6
WEIGHT_SUM_TOLERANCE = 1e-8

ENS_URL = "gs://weatherbench2/datasets/ifs_ens/2018-2022-240x121_equiangular_with_poles_conservative.zarr"
ENS_MEAN_URL = "gs://weatherbench2/datasets/ifs_ens/2018-2022-240x121_equiangular_with_poles_conservative_mean.zarr"
HRES_URL = "gs://weatherbench2/datasets/hres_t0/2016-2022-6h-240x121_equiangular_with_poles_conservative.zarr"
WB2_GUIDE = "https://weatherbench2.readthedocs.io/en/latest/data-guide.html"
GEOMETRY_REPO = "https://github.com/India-Meteorological-Department/Indian_met_zones"
GEOMETRY_COMMIT = "bba99daee85e9742d205c66af92a651a42cf42cd"

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("FORECAST_BUST_DATA_ROOT", str(ROOT / "data"))).resolve()
CACHE = DATA / "cache"
GEOMETRY = DATA / "geometry"
WEIGHTS = DATA / "weights"
PROCESSED = DATA / "processed"
MANIFESTS = DATA / "manifests"
ARTIFACTS = DATA / "artifacts"
REPORTS = DATA / "reports"
DIAGNOSTICS = DATA / "diagnostics"
WEATHERBENCH_CACHE = CACHE / "weatherbench"

TRAIN_YEARS = (2018, 2019, 2020)
VALIDATION_YEAR = 2021
TEST_YEAR = 2022
MIN_GROUP_SAMPLES = 30
ROBUST_EPSILON = 1e-6
ROBUST_CLIP = (-8.0, 8.0)

ENS_REQUIRED = {
    "mean_sea_level_pressure": ("Pa",),
    "2m_temperature": ("K",),
    "10m_u_component_of_wind": ("m s**-1",),
    "10m_v_component_of_wind": ("m s**-1",),
    "u_component_of_wind": ("m s**-1",),
    "v_component_of_wind": ("m s**-1",),
    "geopotential": ("m**2 s**-2",),
    "total_precipitation": ("m",),
    "total_precipitation_24hr": (),
}
HRES_REQUIRED = {
    "mean_sea_level_pressure": ("Pa",),
    "2m_temperature": ("K",),
    "10m_u_component_of_wind": ("m s**-1",),
    "10m_v_component_of_wind": ("m s**-1",),
    "total_precipitation_6hr": ("m",),
}
