"""Owner: Person A. Test bench for the hazard model.

    python -m planit.ml.evaluate

Leave-one-year-out over 2023-2025 (2023 is Florida only; every state from 2024): each year is scored by a model
trained on the other two, so every number is out of sample. Results are also split by region. For each year the
model is compared with rules-v2 run on the same daily weather, on what the
dashboard shows: how often "high"/"extreme" days were real hazard days (precision), how many real hazard days
were flagged high or above (recall), recall per hazard group, calibration, and named case studies. Finally it
compares live forecast weather with observed weather for the same days (train/serve skew).

rules-v2 here sees what history has: the day's peak NWS heat index, rain, peak hourly rain, soil and gusts. Live it
also gets CAPE, thunderstorm codes and alerts, so this comparison is about the weather part of the score.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from planit.ml.features import FEATURES, build_frame, label_days, load_inputs, utc_day
from planit.ml.model import fit_scale, heat_floor, score_on_scale
from planit.ml.score import HourInputs, level_for, score_hour
from planit.ml.train import fit
from planit.states import REGION_OF

LEVELS = ["low", "moderate", "high", "extreme"]
SCORERS = ["model", "model_heat", "rules"]  # ML alone, ML + OSHA heat floor (Predictive), rules-v2 (Real-time)
FLAG_AT = 5.0  # "high" or above: what a supervisor would act on

HAZARD_GROUPS = {
    "storm": {"Thunderstorm Wind", "Lightning", "Hail", "Tornado", "Funnel Cloud"},
    "flood": {"Heavy Rain", "Flash Flood", "Flood"},
    "heat": {"Excessive Heat", "Heat"},
    "tropical": {"Tropical Storm", "Tropical Depression", "Hurricane (Typhoon)", "Storm Surge/Tide"},
    "wind": {"Strong Wind", "High Wind"},
    "cold": {"Extreme Cold/Wind Chill", "Cold/Wind Chill"},
    "winter": {"Winter Storm", "Winter Weather", "Heavy Snow", "Blizzard", "Ice Storm", "Lake-Effect Snow", "Sleet"},
    "fire_dust": {"Wildfire", "Dust Storm"},
}

# (name, site id, UTC day, expectation): "high" = scores >= 5, "low" = scores < 2.5
CASES = [
    ("Hurricane Idalia, Suwannee River", 638, "2023-08-30", "high"),
    ("Tropical Storm Debby, Suwannee River", 638, "2024-08-05", "high"),
    ("Hurricane Helene, Crystal River", 628, "2024-09-26", "high"),
    ("Hurricane Milton landfall, Bayside (Tampa)", 7873, "2024-10-09", "high"),
    ("Calm January day, Bayside (Tampa)", 7873, "2024-01-15", "low"),
    ("Arctic outbreak, Coal Creek (ND)", 6030, "2024-01-14", "high"),
    ("Gulf Coast snowstorm, Nine Mile Point (New Orleans)", 1403, "2025-01-21", "high"),
    ("Hughes Fire, Castaic (CA)", 392, "2025-01-22", "high"),
    ("Mild spring day, Diablo Canyon (CA)", 6099, "2024-05-01", "low"),
]

SKEW_SQL = """
WITH daily AS (
    SELECT site_id, is_forecast, time_bucket('1 day', ts) AS day, count(*) AS hours,
           max(heat_index_f) AS max_heat_index_f, sum(precip_in) AS total_precip_in,
           max(precip_in) AS max_hourly_precip_in, avg(soil_moisture) AS avg_soil_moisture,
           max(gust_mph) AS max_gust_mph
    FROM weather WHERE ts >= now() - interval '30 days'
    GROUP BY 1, 2, 3
)
SELECT f.site_id, f.day,
       f.max_heat_index_f AS f_heat, o.max_heat_index_f AS o_heat,
       f.total_precip_in AS f_rain, o.total_precip_in AS o_rain,
       f.max_hourly_precip_in AS f_peak, o.max_hourly_precip_in AS o_peak,
       f.avg_soil_moisture AS f_soil, o.avg_soil_moisture AS o_soil,
       f.max_gust_mph AS f_gust, o.max_gust_mph AS o_gust
FROM daily f JOIN daily o USING (site_id, day)
WHERE f.is_forecast AND NOT o.is_forecast AND f.hours = 24 AND o.hours = 24
"""


# Daily peak NWS heat index from hourly temperature + humidity (Rothfusz regression; the small NWS humidity
# adjustments in hazards.nws_heat_index are left out here, they move the peak by well under 1°F in Florida).
NWS_HEAT_SQL = """
WITH h AS (
    SELECT site_id, time_bucket('1 day', ts) AS day, temp_f AS t, humidity_pct AS rh,
           0.5 * (temp_f + 61.0 + (temp_f - 68.0) * 1.2 + humidity_pct * 0.094) AS simple
    FROM weather
    WHERE NOT is_forecast AND ts >= %(start)s AND ts < %(end)s AND temp_f IS NOT NULL AND humidity_pct IS NOT NULL
)
SELECT site_id, day, max(CASE WHEN (simple + t) / 2 < 80 THEN simple ELSE
    -42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
    - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh
    END) AS max_nws_heat_index_f
FROM h GROUP BY 1, 2
"""


def _value(v: float) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def rules_scores(frame: pd.DataFrame) -> np.ndarray:
    """rules-v2 on daily weather (no CAPE, thunderstorm codes or alerts in history)."""
    def col(r, name):
        return _value(getattr(r, name, None))

    return np.array([score_hour(HourInputs(
        heat_index_f=col(r, "max_nws_heat_index_f"), rain_1h_in=col(r, "max_hourly_precip_in"),
        rain_24h_in=col(r, "total_precip_in"),
        rain_72h_in=(col(r, "total_precip_in") or 0) + (col(r, "precip_prev_3d_in") or 0),
        soil_moisture=col(r, "avg_soil_moisture"), gust_mph=col(r, "max_gust_mph"),
        humidity_pct=col(r, "min_humidity_pct"), snow_24h_in=col(r, "total_snowfall_in")))[0]
        for r in frame.itertuples()])


def summary(y: np.ndarray, scores: np.ndarray) -> dict:
    flagged = scores >= FLAG_AT
    top = scores >= np.quantile(scores, 0.9)
    return {
        "roc_auc": round(float(roc_auc_score(y, scores)), 3),
        "pr_auc": round(float(average_precision_score(y, scores)), 3),
        "flagged_pct": round(100 * float(flagged.mean()), 1),
        "precision_high+": round(float(y[flagged].mean()), 3) if flagged.any() else float("nan"),
        "recall_high+": round(float(flagged[y == 1].mean()), 3) if (y == 1).any() else float("nan"),
        "hazard_rate_top10%": round(float(y[top].mean()), 3),
    }


def level_table(y: np.ndarray, scores: np.ndarray) -> pd.DataFrame:
    """Per dashboard level: share of days, how often they were hazard days, share of all hazard days."""
    levels = np.array([level_for(s) for s in scores])
    rows = []
    for level in LEVELS:
        m = levels == level
        rows.append({"level": level, "days_pct": round(100 * m.mean(), 1),
                     "hazard_rate": round(float(y[m].mean()), 3) if m.any() else float("nan"),
                     "share_of_hazards_pct": round(100 * float(y[m].sum() / max(1, y.sum())), 1)})
    return pd.DataFrame(rows)


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Predicted vs observed hazard rate per probability decile."""
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), bins, labels=False)
    out = df.groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"), days=("y", "size"))
    return out.round(4).reset_index(drop=True)


def group_recall(frame: pd.DataFrame, sites: pd.DataFrame, events: pd.DataFrame, scorers: dict) -> pd.DataFrame:
    """Share of each hazard group's days that each scorer flagged high or above."""
    rows = []
    for group, types in HAZARD_GROUPS.items():
        days = label_days(sites, events[events["event_type"].isin(types)])
        hit = frame.reset_index().merge(days, on=["site_id", "day"])["index"]
        row = {"group": group, "days": len(hit)}
        for name, col in scorers.items():
            row[f"{name}_recall"] = round(float((frame.loc[hit, col] >= FLAG_AT).mean()), 3) if len(hit) else None
        rows.append(row)
    return pd.DataFrame(rows)


def leave_one_year_out(frame: pd.DataFrame, features: list[str] = FEATURES) -> pd.DataFrame:
    """Adds out-of-sample columns: p_model, model (0-10 score), model_heat (with the OSHA heat floor), rules."""
    frame = frame.copy()
    frame["p_model"] = np.nan
    frame["model"] = np.nan
    frame["rules"] = rules_scores(frame)
    years = frame["day"].dt.year
    for year in sorted(years.unique()):
        train, test = frame[years != year], years == year
        model = fit(train, features=features)
        p = model.predict_proba(frame.loc[test, features])[:, 1]
        # The Real-time scale from the training years only, like the saved model's (planit/ml/scale.py).
        scale = fit_scale(train["rules"].to_numpy(), train["label"].to_numpy())
        frame.loc[test, "p_model"] = p
        frame.loc[test, "model"] = [score_on_scale(float(x), scale) for x in p]
    floors = np.array([heat_floor(h)[0] for h in frame["max_heat_index_f"]])
    frame["model_heat"] = np.maximum(frame["model"].to_numpy(), floors)
    return frame


def case_studies(scored: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, site, day, expect in CASES:
        row = scored[(scored["site_id"] == site) & (scored["day"] == day)]
        if row.empty:
            rows.append({"case": name, "expect": expect, "label": None})
            continue
        r = row.iloc[0]
        ok = (lambda s: s >= FLAG_AT) if expect == "high" else (lambda s: s < 2.5)
        rows.append({"case": name, "expect": expect, "label": int(r["label"]),
                     **{k: v for s in SCORERS for k, v in ((s, r[s]), (f"{s}_ok", ok(r[s])))}})
    return pd.DataFrame(rows)


def skew_report(conn) -> pd.DataFrame | None:
    """Forecast vs observed daily features over the last 30 days, for site-days that have both."""
    pairs = pd.DataFrame(conn.execute(SKEW_SQL).fetchall())
    if pairs.empty:
        return None
    rows = []
    for key, label in [("heat", "max_heat_index_f"), ("rain", "total_precip_in"), ("peak", "max_hourly_precip_in"),
                       ("soil", "avg_soil_moisture"), ("gust", "max_gust_mph")]:
        f, o = pairs[f"f_{key}"].astype(float), pairs[f"o_{key}"].astype(float)
        rows.append({"feature": label, "forecast_mean": round(f.mean(), 3), "observed_mean": round(o.mean(), 3),
                     "mean_diff": round((f - o).mean(), 3), "corr": round(f.corr(o), 2)})
    out = pd.DataFrame(rows)
    out.attrs["site_days"] = len(pairs)
    return out


def main() -> None:
    from planit.db import connection, get_pool

    pd.set_option("display.width", 160)
    try:
        daily, sites, events = load_inputs()
        with connection() as conn:
            skew = skew_report(conn)
            heat = pd.DataFrame(conn.execute(NWS_HEAT_SQL, {"start": "2023-01-01", "end": "2026-01-01"}).fetchall())
    finally:
        get_pool().close()
    heat["day"] = utc_day(heat["day"])
    scored = leave_one_year_out(build_frame(daily, sites, events).merge(heat, on=["site_id", "day"], how="left"))
    y_all = scored["label"].to_numpy()

    print(f"{len(scored):,} site-days, {100 * y_all.mean():.1f}% hazard days. Each year scored by a model trained"
          " on the other two.\n")
    rows = []
    for year, part in scored.groupby(scored["day"].dt.year):
        y = part["label"].to_numpy()
        for name in SCORERS:
            rows.append({"year": year, "scorer": name, **summary(y, part[name].to_numpy())})
    for name in SCORERS:
        rows.append({"year": "all", "scorer": name, **summary(y_all, scored[name].to_numpy())})
    print("== Summary (flagged = score >= 5, high or extreme)")
    print(pd.DataFrame(rows).to_string(index=False), "\n")

    region = scored["site_id"].map(dict(zip(sites["id"], sites["state"].map(REGION_OF), strict=True)))
    rows = []
    for name_, part in scored.groupby(region):
        y = part["label"].to_numpy()
        for name in SCORERS:
            rows.append({"region": name_, "scorer": name, **summary(y, part[name].to_numpy())})
    print("== By region (all years)")
    print(pd.DataFrame(rows).to_string(index=False), "\n")

    for name in SCORERS:
        print(f"== {name}: per dashboard level (all years)")
        print(level_table(y_all, scored[name].to_numpy()).to_string(index=False), "\n")

    print("== Recall per hazard group (share of those days flagged high or above)")
    print(group_recall(scored, sites, events, {s: s for s in SCORERS}).to_string(index=False), "\n")

    print("== Model calibration (probability deciles, all years)")
    print(calibration_table(y_all, scored["p_model"].to_numpy()).to_string(index=False), "\n")

    print("== Case studies")
    print(case_studies(scored).to_string(index=False), "\n")

    print("== Live forecast vs observed weather, last 30 days (train/serve skew)")
    if skew is None:
        print("no site-days with both a full forecast and full observations yet")
    else:
        print(f"{skew.attrs['site_days']} site-days")
        print(skew.to_string(index=False))


if __name__ == "__main__":
    main()
