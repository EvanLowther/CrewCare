"""Owner: Person A. Hours 8-12.

Write current + forecast scores to `hazard_scores`. Probability -> 0-10 score, and the top 3
factors (e.g. from XGBoost SHAP values) -> `factors`. Until the model exists, use a rule-based
score (model_version='rules-v1') so the dashboard always has data.

Level bands (keep in sync with the frontend colours): low < 2.5 <= moderate < 5 <= high < 7.5 <= extreme
"""


def level_for(score: float) -> str:
    if score >= 7.5:
        return "extreme"
    if score >= 5:
        return "high"
    if score >= 2.5:
        return "moderate"
    return "low"


def score_all() -> None:
    raise NotImplementedError
