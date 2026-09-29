from __future__ import annotations

import re
from datetime import datetime

from .exceptions import ValidationError


_PREDICTION_RE = re.compile(r"^(?P<model>[a-zA-Z0-9-]+)__(?P<stamp>\d{8}T\d{6}Z)__(?P<region>imd-\d{2})__d(?P<lead>\d{2})$")


def _stamp(value: str) -> str:
    normalized = value[:19]
    return datetime.fromisoformat(normalized).strftime("%Y%m%dT%H%M%SZ")


def run_id(source_forecast_time: str) -> str:
    return f"run-{_stamp(source_forecast_time)}"


def prediction_id(model_version: str, source_forecast_time: str, region_id: str, lead_day: int) -> str:
    if not 1 <= int(lead_day) <= 10:
        raise ValidationError("lead_day must be between 1 and 10")
    return f"{model_version}__{_stamp(source_forecast_time)}__{region_id}__d{int(lead_day):02d}"


def parse_run_id(value: str) -> str:
    if not re.fullmatch(r"run-\d{8}T\d{6}Z", value):
        raise ValidationError("Unknown run ID format")
    return datetime.strptime(value[4:], "%Y%m%dT%H%M%SZ").isoformat(timespec="seconds") + ".000000000"


def parse_prediction_id(value: str) -> dict:
    match = _PREDICTION_RE.fullmatch(value)
    if not match:
        raise ValidationError("Unknown prediction ID format")
    parts = match.groupdict()
    return {
        "model_version": parts["model"],
        "source_forecast_time": datetime.strptime(parts["stamp"], "%Y%m%dT%H%M%SZ").isoformat(timespec="seconds") + ".000000000",
        "region_id": parts["region"],
        "lead_day": int(parts["lead"]),
    }
