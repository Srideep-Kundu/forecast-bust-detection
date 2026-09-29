from pathlib import Path

import pytest

from forecast_bust.data_store import ArtifactStore
from forecast_bust.exceptions import ValidationError


def resolver(data_root: Path) -> ArtifactStore:
    store = object.__new__(ArtifactStore)
    store.data_root = data_root
    return store


def test_manifest_windows_path_relocates_below_configured_data_root(tmp_path):
    target = tmp_path / "artifacts" / "model.joblib"
    target.parent.mkdir()
    target.write_bytes(b"artifact")
    recorded = r"C:\previous\workspace\data\artifacts\model.joblib"
    assert resolver(tmp_path).resolve_recorded_path(recorded) == target.resolve()


def test_manifest_path_relocation_rejects_missing_data_root_and_escape(tmp_path):
    store = resolver(tmp_path)
    with pytest.raises(ValidationError, match="cannot be relocated"):
        store.resolve_recorded_path(r"C:\previous\workspace\artifacts\model.joblib")
    with pytest.raises(ValidationError, match="escapes configured data root"):
        store.resolve_recorded_path(r"C:\previous\workspace\data\..\secrets.txt")
