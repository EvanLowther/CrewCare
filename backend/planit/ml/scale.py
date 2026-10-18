"""Owner: Person A. Put the Predictive score on the Real-time scale (see model.score_on_scale).

    python -m planit.ml.scale                     # add the scale to the latest model's .meta.json
    python -m planit.ml.scale --model PATH.json

Real-time (rules-v2) is scored on every historical site-day, from the same daily weather evaluate.py uses, and the
share of those days that were hazard days is fitted per score (isotonic). Writing it into the metadata changes how the
model's probabilities are shown, not the model: the probabilities, and ROC-AUC / PR-AUC, stay the same.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from planit.ml.evaluate import NWS_HEAT_SQL, rules_scores
from planit.ml.features import build_frame, load_inputs, utc_day
from planit.ml.model import fit_scale, latest_model_path


def scale_from_history() -> dict:
    """Needs the database; the caller closes the pool."""
    import pandas as pd

    from planit.db import connection

    daily, sites, events = load_inputs()
    with connection() as conn:
        heat = pd.DataFrame(conn.execute(NWS_HEAT_SQL, {"start": "2023-01-01", "end": "2026-01-01"}).fetchall())
    heat["day"] = utc_day(heat["day"])
    frame = build_frame(daily, sites, events).merge(heat, on=["site_id", "day"], how="left")
    return fit_scale(rules_scores(frame), frame["label"].to_numpy())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, help="Model .json (default: the latest)")
    args = parser.parse_args()
    meta_path = (args.model or latest_model_path()).with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text())
    from planit.db import get_pool

    try:
        meta["scale"] = scale_from_history()
    finally:
        get_pool().close()
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    rates = dict(zip(meta["scale"]["scores"], meta["scale"]["rates"], strict=True))
    print(f"wrote the scale into {meta_path.name}: hazard-day rate at Real-time "
          + ", ".join(f"{s} = {rates[s]:.3f}" for s in (2.5, 5.0, 7.5, 10.0)))


if __name__ == "__main__":
    main()
