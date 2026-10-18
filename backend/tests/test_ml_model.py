"""planit.ml.train + planit.ml.model on synthetic data: no database, no real model file."""

import json

import numpy as np
import pandas as pd
import pytest

from planit.ml.features import FEATURES
from planit.ml.model import (
    CALMEST_P,
    HazardModel,
    apply_heat_floor,
    fit_scale,
    heat_floor,
    latest_model_path,
    score_from_probability,
    score_on_scale,
)
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
        "min_temp_f": rng.normal(60, 15, n),
        "min_wind_chill_f": rng.normal(55, 18, n),
        "total_snowfall_in": rng.exponential(0.05, n),
        "max_snow_depth_ft": rng.exponential(0.05, n),
        "min_humidity_pct": rng.uniform(10, 90, n),
        "latitude": rng.uniform(25, 48, n),
        "longitude": rng.uniform(-124, -70, n),
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


def test_fit_scale_matches_real_time_hazard_rates_and_maps_back():
    rng = np.random.default_rng(1)
    rt = rng.uniform(0, 10, 20000)
    y = (rng.uniform(size=rt.size) < 0.002 + 0.03 * rt ** 1.5 / 10).astype(int)  # hazard rate rises with the score
    scale = fit_scale(rt, y)
    rates = np.array(scale["rates"])
    assert len(scale["scores"]) == 101 and np.all(np.diff(rates) >= 0)  # never falls as the score rises
    rate_at_5 = rates[scale["scores"].index(5.0)]
    assert score_on_scale(rate_at_5, scale) <= 5.0 <= score_on_scale(rate_at_5 + 1e-4, scale) + 0.2
    assert score_on_scale(0.0, scale) == 0.0 and score_on_scale(0.99, scale) == 10.0
    lower, higher = score_on_scale(0.02, scale), score_on_scale(0.06, scale)
    assert lower < higher  # a lower probability scores lower: the forecast can go down


def test_calm_days_spread_below_1_instead_of_all_scoring_0():
    # Like the US model's scale: Real-time 0 days were hazard days 0.34% of the time, Real-time 1.0 days 1.05%.
    scores = np.round(np.arange(0, 10.05, 0.1), 1).tolist()
    scale = {"scores": scores, "rates": np.interp(scores, [0, 1, 10], [0.00338, 0.01053, 0.55]).round(5).tolist()}
    assert score_on_scale(CALMEST_P, scale) == 0.0 and score_on_scale(0.0, scale) == 0.0
    calm = [score_on_scale(p, scale) for p in (0.0008, 0.0018, 0.0034)]  # quiet October sites, all 0.0 before
    assert calm == sorted(calm) and 0 < calm[0] < calm[-1] < 1.0
    assert score_on_scale(0.01053, scale) == 1.0  # meets the Real-time match at 1.0
    mapped = [score_on_scale(p, scale) for p in np.linspace(0, 0.6, 3000)]
    assert all(b >= a for a, b in zip(mapped, mapped[1:], strict=False))  # never falls as the odds rise


def test_model_uses_the_scale_when_its_meta_has_one():
    scale = {"scores": [0.0, 5.0, 10.0], "rates": [0.0, 0.05, 0.3]}
    m = HazardModel(booster=None, features=[], base_rate=0.05, version="t", scale=scale)
    assert m.score(0.05) == 5.0 and m.score(0.2) == 10.0 and m.score(0.01) == 5.0
    assert HazardModel(booster=None, features=[], base_rate=0.05, version="t").score(0.05) == score_from_probability(
        0.05, 0.05)  # no scale: the old mapping


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


def test_latest_model_is_the_newest_trained_not_the_last_name(tmp_path):
    for version, trained_at in [("xgb-2026-10-17", "2026-10-17T05:11:16+00:00"),
                                ("xgb-2026-10-17-us", "2026-10-17T20:57:02+00:00")]:
        (tmp_path / f"{version}.json").write_text("{}")
        (tmp_path / f"{version}.meta.json").write_text(json.dumps({"version": version, "trained_at": trained_at}))
    assert sorted(p.name for p in tmp_path.glob("*.json") if "meta" not in p.name)[-1] == "xgb-2026-10-17.json"
    assert latest_model_path(tmp_path).name == "xgb-2026-10-17-us.json"
