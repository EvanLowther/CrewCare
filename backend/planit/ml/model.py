"""Owner: Person A. The trained hazard model: probability of a hazard day -> 0-10 score + top factors.

The score is on the Real-time (rules-v2) scale: a Predictive 5 is as likely to be a hazard day as a Real-time 5.
The model's metadata carries that mapping (`scale`, from planit/ml/scale.py): for each Real-time score on a
0.1 grid, the share of historical site-days at that score that were hazard days. A probability scores as the lowest
Real-time score whose hazard-day rate reaches it, so the levels mean the same on both dashboard views. A model
without `scale` falls back to 10 * ln(1 + p / base_rate) / ln(11) (the base rate scores ~2.9).

Below 1.0 the match stops working: every calm day scores Real-time 0 (none of its rules apply), and those days were
hazard days 0.34% of the time, but the model tells calm days apart (from 0.03% to 1%). Matching would score a
quarter of all days exactly 0. So under 1.0 the score spreads the model's odds on a log scale instead, from
CALMEST_P (0.0) to the rate at Real-time 1.0 (1.0). All of it is "low" either way.

Factors come from XGBoost's own SHAP values (pred_contribs): each feature's push toward "hazard" is turned into a
share of the score, so the factors add up to the score. Labels state the fact behind them, like rules-v1.

Heat has an OSHA floor on top of the model: NOAA only logs "Excessive Heat" where a few panhandle offices file it
(every heat label is from August 2023), so the model can't learn heat danger. A heat index of 103°F or more keeps
the score at least 5.0 (high) and 115°F or more at least 7.5 (extreme), matching OSHA's heat index bands.
"""

from __future__ import annotations

import calendar
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

MODELS_DIR = Path(__file__).resolve().parent / "models"
TOP_FACTORS = 3


def score_from_probability(p: float, base_rate: float) -> float:
    return round(min(10.0, 10 * math.log1p(p / base_rate) / math.log(11)), 1)


def fit_scale(real_time_scores: np.ndarray, labels: np.ndarray, step: float = 0.1) -> dict:
    """The hazard-day rate at each Real-time score (isotonic, so it never falls as the score rises), on a grid."""
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(real_time_scores, labels)
    scores = np.round(np.arange(0, 10 + step / 2, step), 1)
    return {"scores": scores.tolist(), "rates": np.round(iso.predict(scores), 5).tolist()}


LOW_END_SCORE = 1.0  # below this the score spreads the odds on a log scale (see the module docstring)
CALMEST_P = 0.0003  # scores 0.0: about the calmest 0.5% of 2023-2025 site-days by the US model's odds


def score_on_scale(p: float, scale: dict) -> float:
    """The lowest Real-time score whose historical hazard-day rate reaches p; 10 above the top of the scale.
    Under LOW_END_SCORE, ln(p / CALMEST_P) / ln(rate at LOW_END_SCORE / CALMEST_P) of the way to it.
    `scale` = {"scores": [0.0, 0.1, ..., 10.0], "rates": [non-decreasing hazard-day rates]}."""
    rates = np.asarray(scale["rates"])
    low_rate = float(rates[scale["scores"].index(LOW_END_SCORE)]) if LOW_END_SCORE in scale["scores"] else 0.0
    if p < low_rate and low_rate > CALMEST_P:
        if p <= CALMEST_P:
            return 0.0
        return round(min(LOW_END_SCORE, LOW_END_SCORE * math.log(p / CALMEST_P) / math.log(low_rate / CALMEST_P)), 1)
    i = int(np.searchsorted(rates, p, side="left"))
    return 10.0 if i >= len(scale["scores"]) else round(float(scale["scores"][i]), 1)


# OSHA heat index bands: (at least this °F, score floor, band name), highest first
HEAT_FLOORS = [(115.0, 7.5, "extreme"), (103.0, 5.0, "high")]


def heat_floor(heat_index_f: float | None) -> tuple[float, str | None]:
    """(score floor, OSHA band) for a heat index; (0, None) below 103°F or when unknown."""
    if heat_index_f is None or pd.isna(heat_index_f):
        return 0.0, None
    for at_least, floor, band in HEAT_FLOORS:
        if heat_index_f >= at_least:
            return floor, band
    return 0.0, None


def apply_heat_floor(score: float, factors: list[dict], heat_index_f: float | None) -> tuple[float, list[dict]]:
    """Raise the score to the OSHA floor; the heat factor takes up the difference so factors still add up."""
    floor, band = heat_floor(heat_index_f)
    if floor <= score:
        return score, factors
    others = [f for f in factors if f["key"] != "heat_index"]
    heat = {"key": "heat_index", "label": f"Heat index {heat_index_f:.0f}°F (OSHA {band} risk)",
            "contribution": round(floor - sum(f["contribution"] for f in others), 1)}
    return floor, sorted([heat, *others], key=lambda f: f["contribution"], reverse=True)[:TOP_FACTORS]


# feature -> (factor key, label for the value). Keys match rules-v1 where they mean the same thing.
FACTOR_LABELS = {
    "max_heat_index_f": ("heat_index", lambda v: f"Heat index {v:.0f}°F"),
    "total_precip_in": ("rain_24h", lambda v: f"{v:.1f} in of rain in 24 h"),
    "precip_prev_3d_in": ("rain_3d", lambda v: f"{v:.1f} in of rain in the last 3 days"),
    "avg_soil_moisture": ("soil_moisture", lambda v: f"Wet ground (soil moisture {v * 100:.0f}%)"),
    "max_gust_mph": ("wind", lambda v: f"Gusts {v:.0f} mph"),
    "max_hourly_precip_in": ("downpour", lambda v: f"Downpours up to {v:.1f} in/h"),
    "month": ("season", lambda v: f"Hazard season ({calendar.month_name[int(v)]})"),
    "min_temp_f": ("cold", lambda v: f"Low of {v:.0f}°F"),
    "min_wind_chill_f": ("wind_chill", lambda v: f"Wind chill {v:.0f}°F"),
    "total_snowfall_in": ("snow", lambda v: f"{v:.1f} in of snow in 24 h"),
    "max_snow_depth_ft": ("snow_depth", lambda v: f"{v * 12:.0f} in of snow on the ground"),
    "min_humidity_pct": ("dry_air", lambda v: f"Dry air (humidity down to {v:.0f}%)"),
    "latitude": ("location", lambda v: "Local climate"),
    "longitude": ("location", lambda v: "Local climate"),
}


# Don't show a factor for an unremarkable value: SHAP rightly says a sprinkle is riskier than bone-dry, but
# "0.1 in of rain" reads as nonsense next to an extreme score. Features not listed always show.
FACTOR_MIN_VALUE = {
    "max_heat_index_f": 90.0,
    "total_precip_in": 0.25,
    "precip_prev_3d_in": 0.25,
    "avg_soil_moisture": 0.25,
    "max_gust_mph": 20.0,
    "max_hourly_precip_in": 0.2,
    "total_snowfall_in": 0.5,
    "max_snow_depth_ft": 0.25,
}
# The same for features where lower is worse: a factor only shows at or below these.
FACTOR_MAX_VALUE = {
    "min_temp_f": 32.0,
    "min_wind_chill_f": 15.0,
    "min_humidity_pct": 25.0,
}


@dataclass
class HazardModel:
    booster: xgb.Booster
    features: list[str]
    base_rate: float
    version: str
    scale: dict | None = None  # see score_on_scale(); None for models trained before it

    @classmethod
    def load(cls, path: Path) -> HazardModel:
        """`path` is the model .json; its metadata sits next to it as .meta.json."""
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        booster = xgb.Booster()
        booster.load_model(path)
        return cls(booster, meta["features"], meta["base_rate"], meta["version"], meta.get("scale"))

    def score(self, p: float) -> float:
        return score_on_scale(p, self.scale) if self.scale else score_from_probability(p, self.base_rate)

    def probabilities(self, rows: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(xgb.DMatrix(rows[self.features], feature_names=self.features))

    def explain(self, rows: pd.DataFrame) -> list[tuple[float, list[dict]]]:
        """(score, top factors) per row. Factors use the RiskFactor shape: key, label, contribution."""
        matrix = xgb.DMatrix(rows[self.features], feature_names=self.features)
        probs = self.booster.predict(matrix)
        contribs = self.booster.predict(matrix, pred_contribs=True)[:, :-1]  # last column is the bias
        out = []
        for values, p, push in zip(rows[self.features].itertuples(index=False), probs, contribs, strict=True):
            score = self.score(float(p))
            positive = np.clip(push, 0, None)
            total = positive.sum()
            factors = []
            if total > 0 and score > 0:
                for i in np.argsort(-positive):
                    if len(factors) == TOP_FACTORS:
                        break
                    points = round(float(score * positive[i] / total), 1)
                    value = values[i]
                    if points < 0.1 or value is None or pd.isna(value):
                        continue
                    name = self.features[i]
                    too_low = value < FACTOR_MIN_VALUE.get(name, float("-inf"))
                    if too_low or value > FACTOR_MAX_VALUE.get(name, float("inf")):
                        continue
                    key, label = FACTOR_LABELS[name]
                    same = next((f for f in factors if f["key"] == key), None)
                    if same:  # latitude and longitude are one "location" factor
                        same["contribution"] = round(same["contribution"] + points, 1)
                        continue
                    factors.append({"key": key, "label": label(value), "contribution": points})
            heat = values[self.features.index("max_heat_index_f")] if "max_heat_index_f" in self.features else None
            out.append(apply_heat_floor(score, factors, heat))
        return out


def latest_model_path(folder: Path = MODELS_DIR) -> Path:
    """The most recently trained model, by `trained_at` in its .meta.json. Not by file name: 'xgb-2026-10-17-us.json'
    sorts before 'xgb-2026-10-17.json' ('-' comes before '.')."""
    paths = [p for p in folder.glob("xgb-*.json") if not p.name.endswith(".meta.json")]
    if not paths:
        raise FileNotFoundError(f"No trained model in {folder}. Run: python -m planit.ml.train")

    def trained_at(p: Path) -> str:
        meta = p.with_suffix(".meta.json")
        return json.loads(meta.read_text()).get("trained_at", "") if meta.exists() else ""

    return max(paths, key=lambda p: (trained_at(p), p.name))


def load_latest() -> HazardModel:
    return HazardModel.load(latest_model_path())
