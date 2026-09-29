from pathlib import Path

from forecast_bust.acquisition import normalize_spread_features
from forecast_bust.constants import DATASET_VERSION, FEATURE_CONTRACT_VERSION


def test_production_defaults_and_four_documents_are_mean_only():
    assert normalize_spread_features(None) == ()
    assert DATASET_VERSION == "wb2-ifs-mean-india-v2"
    assert FEATURE_CONTRACT_VERSION == "mean-only-mvp-v2"
    root = Path(__file__).resolve().parents[1]
    for name in ("prd.md", "tech.md", "flow.md", "agents.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert "mean-only" in text.lower() or "official IFS ENS mean" in text
        assert "post-MVP" in text or "post-mvp" in text
        assert "raw-member" in text or "raw member" in text
