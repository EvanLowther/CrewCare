"""Owner: Person A. Train the XGBoost hazard model on features.training_frame() and save it to ml/models/.

    python -m planit.ml.train

Measures on a time split (train 2023-2024, test 2025) so the numbers reflect a season the model hasn't seen,
then fits the saved model on all three years. Writes models/xgb-<date>.json and .meta.json (features, base rate,
test metrics).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

from planit.ml.features import FEATURES, training_frame
from planit.ml.model import MODELS_DIR

TEST_FROM = "2025-01-01"
PARAMS = {"n_estimators": 300, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
          "min_child_weight": 5, "eval_metric": "aucpr"}


def fit(frame: pd.DataFrame, seed: int = 0, features: list[str] = FEATURES) -> XGBClassifier:
    """Plain probabilities (no class weighting): the score needs calibrated chances, not just a ranking."""
    model = XGBClassifier(**PARAMS, random_state=seed)
    model.fit(frame[features], frame["label"])
    return model


def evaluate(model: XGBClassifier, test: pd.DataFrame, base_rate: float) -> dict:
    y, p = test["label"].to_numpy(), model.predict_proba(test[FEATURES])[:, 1]
    top = p >= np.quantile(p, 0.9)
    return {
        "test_rows": int(len(test)),
        "test_hazard_rate": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 3),
        "pr_auc": round(float(average_precision_score(y, p)), 3),
        "pr_auc_baseline": round(float(y.mean()), 3),  # what guessing the base rate gets
        "brier": round(float(brier_score_loss(y, p)), 4),
        "brier_baseline": round(float(brier_score_loss(y, np.full_like(p, base_rate))), 4),
        "hazard_rate_top_10pct": round(float(y[top].mean()), 3),  # how often the riskiest-scored days were real
    }


def save(model: XGBClassifier, meta: dict, folder: Path = MODELS_DIR) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{meta['version']}.json"
    model.get_booster().save_model(path)
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=MODELS_DIR)
    args = parser.parse_args()

    from planit.db import get_pool

    try:
        frame = training_frame()
    finally:
        get_pool().close()
    train, test = frame[frame["day"] < TEST_FROM], frame[frame["day"] >= TEST_FROM]
    metrics = evaluate(fit(train), test, base_rate=float(train["label"].mean()))
    print(f"train {len(train):,} rows, test {len(test):,} rows (from {TEST_FROM})")
    for name, value in metrics.items():
        print(f"  {name:24s} {value}")

    final = fit(frame)
    today = datetime.now(UTC).date().isoformat()
    meta = {
        "version": f"xgb-{today}",
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "features": FEATURES,
        "base_rate": round(float(frame["label"].mean()), 5),
        "rows": int(len(frame)),
        "days": [str(frame["day"].min().date()), str(frame["day"].max().date())],
        "params": PARAMS,
        "test_metrics": metrics,
        "importance": {k: round(float(v), 4) for k, v in zip(FEATURES, final.feature_importances_, strict=True)},
    }
    path = save(final, meta, args.out)
    print(f"saved {path} (base rate {meta['base_rate']:.3f})")


if __name__ == "__main__":
    main()
