"""Owner: Person A. Why XGBoost, and why one national model: comparisons scored out of sample.

    python -m planit.ml.compare               # four model types on identical inputs -> docs/model_comparison.csv
    python -m planit.ml.compare --by-region   # one national model vs one per region -> docs/region_comparison.csv

Model types: logistic regression, random forest, scikit-learn's gradient boosting and XGBoost each get the same
site-days, first with the 7 Florida-era features, then with all 14. By region: XGBoost trained on every site vs
XGBoost trained only on that region's sites, both scored on that region. Leave-one-year-out like evaluate.py: each
year is scored by a model trained on the other years. Robustness only: neither changes the saved model.
"""

from __future__ import annotations

import argparse
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
from planit.states import REGION_OF

FLORIDA_FEATURES = FEATURES[:7]  # what xgb-2026-10-17 used: heat, rain, 3-day rain, soil, gusts, peak rain, month
OUT = REPO_ROOT / "docs" / "model_comparison.csv"
REGION_OUT = REPO_ROOT / "docs" / "region_comparison.csv"

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


def by_region(frame: pd.DataFrame, regions: pd.Series) -> pd.DataFrame:
    """National vs region-only XGBoost, leave-one-year-out, scored on each region's site-days."""
    years, region = frame["day"].dt.year.to_numpy(), regions.to_numpy()
    national, regional = np.full(len(frame), np.nan), np.full(len(frame), np.nan)
    for year in np.unique(years):
        test = years == year
        national[test] = fit(frame[~test]).predict_proba(frame.loc[test, FEATURES])[:, 1]
        for r in np.unique(region):
            train, scored = frame[~test & (region == r)], test & (region == r)
            if scored.any() and train["label"].nunique() == 2:
                regional[scored] = fit(train).predict_proba(frame.loc[scored, FEATURES])[:, 1]
    rows = []
    for r in np.unique(region):
        part = region == r
        y = frame.loc[part, "label"].to_numpy()
        base = {"region": r, "sites": frame.loc[part, "site_id"].nunique(), "site_days": int(part.sum()),
                "hazard_days": int(y.sum())}
        for name, p in (("national", national[part]), ("region only", regional[part])):
            ok = ~np.isnan(p)
            rows.append({**base, "model": name, **scores(y[ok], p[ok])})
    return pd.DataFrame(rows)


def main() -> None:
    from planit.db import connection, get_pool

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--by-region", action="store_true", help="national vs one model per region")
    args = parser.parse_args()
    try:
        frame = training_frame()
        with connection() as conn:
            states = {r["id"]: r["state"] for r in conn.execute("SELECT id, state FROM sites").fetchall()}
    finally:
        get_pool().close()
    y = frame["label"].to_numpy()
    print(f"{len(frame):,} site-days, {100 * y.mean():.1f}% hazard days, leave-one-year-out\n")
    if args.by_region:
        table = by_region(frame, frame["site_id"].map(states).map(REGION_OF))
        print(table.to_string(index=False))
        table.to_csv(REGION_OUT, index=False)
        print(f"\nwrote {REGION_OUT}")
        return
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
