"""planit.ml.train + planit.ml.model on synthetic data: no database, no real model file."""

import numpy as np
import pandas as pd
import pytest

from planit.ml.features import FEATURES
from planit.ml.model import HazardModel, apply_heat_floor, heat_floor, latest_model_path, score_from_probability
from planit.ml.train import evaluate, fit, save


@pytest.fixture(scope="module")
def frame():
    """Hazard days are driven by downpours and gusts; the other features are noise."""
    rng = np.random.default_rng(0)
    n = 3000
    df = pd.DataFrame({
        "max_heat_index_f": rng.normal(88, 8, n),
        "total_precip_in": rng.exponential(0.2, n),
        "precip_prev_3d_in": rng.exponential(0.5, n),
        "avg_soil_moisture": rng.uniform(0.05, 0.45, n),
        "max_gust_mph": rng.normal(22, 8, n).clip(5),
        "max_hourly_precip_in": rng.exponential(0.08, n),
        "month": rng.integers(1, 13, n),
    })
    risk = -4 + 6 * df["max_hourly_precip_in"] + 0.08 * (df["max_gust_mph"] - 22)
    df["label"] = (rng.uniform(size=n) < 1 / (1 + np.exp(-risk))).astype(int)
    return df


def test_score_scale():
    base = 0.04
    assert score_from_probability(0.0, base) == 0.0
    assert 2.5 <= score_from_probability(base, base) < 5  # a normal day is moderate
    assert score_from_probability(0.10, base) >= 5  # 2.5x normal is high
    assert score_from_probability(0.40, base) == 10.0
    assert score_from_probability(0.99, base) == 10.0


def test_heat_floor_bands():
    assert heat_floor(102.9) == (0.0, None)
    assert heat_floor(103.0) == (5.0, "high")
    assert heat_floor(115.0) == (7.5, "extreme")
    assert heat_floor(None) == (0.0, None)
    assert heat_floor(float("nan")) == (0.0, None)


def test_apply_heat_floor_raises_score_and_factors_still_add_up():
    rain = {"key": "rain_24h", "label": "0.3 in of rain today", "contribution": 0.8}
    score, factors = apply_heat_floor(2.0, [rain], 106.4)
    assert score == 5.0
    assert factors[0] == {"key": "heat_index", "label": "Heat index 106°F (OSHA high risk)", "contribution": 4.2}
    assert round(sum(f["contribution"] for f in factors), 1) == score
    assert apply_heat_floor(6.0, [rain], 106.4) == (6.0, [rain])  # already above the floor: unchanged
    assert apply_heat_floor(2.0, [rain], 95.0) == (2.0, [rain])


def test_train_save_load_explain(frame, tmp_path):
    model = fit(frame)
    metrics = evaluate(model, frame, base_rate=float(frame["label"].mean()))
    assert metrics["roc_auc"] > 0.7
    assert metrics["pr_auc"] > metrics["pr_auc_baseline"]

    meta = {"version": "xgb-test", "features": FEATURES, "base_rate": float(frame["label"].mean())}
    path = save(model, meta, tmp_path)
    assert latest_model_path(tmp_path) == path

    loaded = HazardModel.load(path)
    expected = model.predict_proba(frame.head(50)[FEATURES])[:, 1]
    np.testing.assert_allclose(loaded.probabilities(frame.head(50)), expected, rtol=1e-5)

    storm = frame.head(1).assign(max_hourly_precip_in=1.5, max_gust_mph=60.0)
    calm = frame.head(1).assign(max_hourly_precip_in=0.0, max_gust_mph=8.0, total_precip_in=0.0)
    (storm_score, storm_factors), (calm_score, _) = loaded.explain(pd.concat([storm, calm]))
    assert 0 <= calm_score < storm_score <= 10
    assert 1 <= len(storm_factors) <= 3
    assert {f["key"] for f in storm_factors} & {"downpour", "wind"}
    assert all(set(f) == {"key", "label", "contribution"} and f["contribution"] > 0 for f in storm_factors)
    assert sum(f["contribution"] for f in storm_factors) <= storm_score + 0.15  # shares of the score
