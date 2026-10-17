"""Owner: Person A. The trained hazard model: probability of a hazard day -> 0-10 score + top factors.

The score is relative to a normal day, because hazard days are rare (~4% of site-days): a raw probability x 10
would almost never leave 'low'. score = 10 * ln(1 + p / base_rate) / ln(11), so the base rate scores ~2.9
(moderate), 2.7x the base rate ~5.5 (high), and 10x the base rate or more 10.

Factors come from XGBoost's own SHAP values (pred_contribs): each feature's push toward "hazard" is turned into a
share of the score, so the factors add up to the score. Labels state the fact behind them, like rules-v1.
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


# feature -> (factor key, label for the value). Keys match rules-v1 where they mean the same thing.
FACTOR_LABELS = {
    "max_heat_index_f": ("heat_index", lambda v: f"Heat index {v:.0f}°F"),
    "total_precip_in": ("rain_24h", lambda v: f"{v:.1f} in of rain today"),
    "precip_prev_3d_in": ("rain_3d", lambda v: f"{v:.1f} in of rain in the last 3 days"),
    "avg_soil_moisture": ("soil_moisture", lambda v: f"Wet ground (soil moisture {v * 100:.0f}%)"),
    "max_gust_mph": ("wind", lambda v: f"Gusts {v:.0f} mph"),
    "max_hourly_precip_in": ("downpour", lambda v: f"Downpours up to {v:.1f} in/h"),
    "month": ("season", lambda v: f"Storm season ({calendar.month_name[int(v)]})"),
}


@dataclass
class HazardModel:
    booster: xgb.Booster
    features: list[str]
    base_rate: float
    version: str

    @classmethod
    def load(cls, path: Path) -> HazardModel:
        """`path` is the model .json; its metadata sits next to it as .meta.json."""
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        booster = xgb.Booster()
        booster.load_model(path)
        return cls(booster, meta["features"], meta["base_rate"], meta["version"])

    def probabilities(self, rows: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(xgb.DMatrix(rows[self.features], feature_names=self.features))

    def explain(self, rows: pd.DataFrame) -> list[tuple[float, list[dict]]]:
        """(score, top factors) per row. Factors use the RiskFactor shape: key, label, contribution."""
        matrix = xgb.DMatrix(rows[self.features], feature_names=self.features)
        probs = self.booster.predict(matrix)
        contribs = self.booster.predict(matrix, pred_contribs=True)[:, :-1]  # last column is the bias
        out = []
        for values, p, push in zip(rows[self.features].itertuples(index=False), probs, contribs, strict=True):
            score = score_from_probability(float(p), self.base_rate)
            positive = np.clip(push, 0, None)
            total = positive.sum()
            factors = []
            if total > 0 and score > 0:
                for i in np.argsort(-positive)[:TOP_FACTORS]:
                    points = round(float(score * positive[i] / total), 1)
                    value = values[i]
                    if points < 0.1 or value is None or pd.isna(value):
                        continue
                    key, label = FACTOR_LABELS[self.features[i]]
                    factors.append({"key": key, "label": label(value), "contribution": points})
            out.append((score, factors))
        return out


def latest_model_path(folder: Path = MODELS_DIR) -> Path:
    paths = sorted(p for p in folder.glob("xgb-*.json") if not p.name.endswith(".meta.json"))
    if not paths:
        raise FileNotFoundError(f"No trained model in {folder}. Run: python -m planit.ml.train")
    return paths[-1]


def load_latest() -> HazardModel:
    return HazardModel.load(latest_model_path())
