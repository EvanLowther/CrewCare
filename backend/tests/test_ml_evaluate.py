"""Pure parts of the ML test bench (planit.ml.evaluate): no database."""

import numpy as np
import pandas as pd

from planit.ml.evaluate import calibration_table, level_table, rules_scores, summary


def test_rules_scores_treat_missing_values_as_unknown():
    frame = pd.DataFrame({"max_heat_index_f": [float("nan"), 115.0], "total_precip_in": [0.0, 0.0],
                          "avg_soil_moisture": [0.1, 0.1], "max_gust_mph": [10.0, 10.0]})
    calm, hot = rules_scores(frame)
    assert calm == 0.0  # a NaN heat index must not count as extreme heat
    assert hot == 3.5


def test_summary_and_level_table():
    y = np.array([0, 0, 0, 1, 1])
    scores = np.array([0.5, 1.0, 6.0, 8.0, 3.0])
    s = summary(y, scores)
    assert s["precision_high+"] == 0.5  # 6.0 and 8.0 flagged, one was a hazard day
    assert s["recall_high+"] == 0.5
    table = level_table(y, scores).set_index("level")
    assert table.loc["low", "days_pct"] == 40.0
    assert table.loc["extreme", "share_of_hazards_pct"] == 50.0


def test_calibration_table_bins():
    p = np.linspace(0, 1, 100)
    y = (p > 0.5).astype(int)
    table = calibration_table(y, p, bins=4)
    assert len(table) == 4 and table["days"].sum() == 100
    assert table["observed"].is_monotonic_increasing
