"""Owner: Person A. Why XGBoost: four model types on identical inputs, scored out of sample.

    python -m planit.ml.compare

Logistic regression, random forest, scikit-learn's gradient boosting and XGBoost each get the same site-days, first
with the 7 Florida-era features, then with all 14. Leave-one-year-out like evaluate.py: each year is scored by a
model trained on the other years. Robustness only: it doesn't change the saved model. Writes
docs/model_comparison.csv.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from planit.config import REPO_ROOT
from planit.ml.features import FEATURES, training_frame
from planit.ml.train import fit

FLORIDA_FEATURES = FEATURES[:7]  # what xgb-2026-10-17 used: heat, rain, 3-day rain, soil, gusts, peak rain, month
OUT = REPO_ROOT / "docs" / "model_comparison.csv"

MODELS = {
    "logistic regression": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                                 LogisticRegression(max_iter=2000)),
    "random forest": lambda: make_pipeline(SimpleImputer(strategy="median"),
                                           RandomForestClassifier(n_estimators=200, min_samples_leaf=20, n_jobs=-1,
                                                                  random_state=0)),
    "gradient boosting (sklearn)": lambda: HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05,
                                                                          max_iter=300, random_state=0),
}


def out_of_sample(frame: pd.DataFrame, name: str, features: list[str]) -> tuple[np.ndarray, float]:
    """Leave-one-year-out probabilities for every row, and the total fit time in seconds."""
    p = np.full(len(frame), np.nan)
    years = frame["day"].dt.year.to_numpy()
    seconds = 0.0
    for year in np.unique(years):
        train, test = frame[years != year], years == year
        start = time.perf_counter()
        if name == "XGBoost":
            model = fit(train, features=features)
        else:
            model = MODELS[name]()
            model.fit(train[features], train["label"])
        seconds += time.perf_counter() - start
        p[test] = model.predict_proba(frame.loc[test, features])[:, 1]
    return p, seconds


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    top = p >= np.quantile(p, 0.9)
    return {"roc_auc": round(float(roc_auc_score(y, p)), 3), "pr_auc": round(float(average_precision_score(y, p)), 3),
            "brier": round(float(brier_score_loss(y, p)), 4), "hazard_rate_top10%": round(float(y[top].mean()), 3)}


def main() -> None:
    from planit.db import get_pool

    try:
        frame = training_frame()
    finally:
        get_pool().close()
    y = frame["label"].to_numpy()
    print(f"{len(frame):,} site-days, {100 * y.mean():.1f}% hazard days, leave-one-year-out\n")
    rows = []
    for inputs, features in (("7 Florida features", FLORIDA_FEATURES), ("all 14 features", FEATURES)):
        for name in [*MODELS, "XGBoost"]:
            p, seconds = out_of_sample(frame, name, features)
            rows.append({"inputs": inputs, "model": name, **scores(y, p), "fit_seconds": round(seconds, 1)})
            print(rows[-1])
    table = pd.DataFrame(rows)
    print("\n" + table.to_string(index=False))
    table.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
