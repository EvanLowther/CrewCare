"""Hazard rules (rules-v2): every hazard on one 0-10 scale anchored to published work rules.

Pure functions, no I/O. Used by the scorer (planit/ml/score.py), the NWS ingest (badge severity) and the API
(the heat index it shows). Levels: low < 2.5 <= moderate < 5 <= high < 7.5 <= extreme.

    0 - 2.4   low       normal operations
    2.5 - 4.9 moderate  work with precautions
    5 - 7.4   high      restricted work
    7.5 - 10  extreme   stop non-essential work

Each hazard's severity is linear between anchors:

    heat index (NWS)  <80°F 0 · 91 2.5 · 103 5 · 108 6 · 115 9 · 125 10   OSHA heat index bands; at >=115°F
                      "strenuous work should not be conducted"; FL Heat Advisory ~108°F; NWS extreme danger 125°F
    lightning         10 (strike within 10 mi)                          OSHA/NOAA: shelter until 30 min after
    thunderstorm      8 forecast that hour, 9 with hail (WMO 95 / 96, 99)  "don't begin tasks you can't stop"
    storm potential   CAPE 1000 0 -> 3500 5, x rain chance (max 5)
    wind gusts        <15 mph 0 · 20 2.5 · 28 5 · 40 7.5 · 58 10        OSHA 1926.1431(k)(8) 20 mph personnel
                      lifts; MEWP outdoor rating 28 mph; NWS severe / high-wind criteria 58 mph
    rain rate         0.1 in/h 1 · 0.3 3 · 1.0 7 · 2.0 9                heavy >=0.3 in/h; flash floods >=1 in/h
    rain, 24 h        1 in 2 · 3 5 · 5 7.5 · 8 9
    saturated ground  soil 25% 0 · 35% 3 · 45% 6, or 3-day rain 2 in 2.5 · 4 in 5 (max 6)   stuck vehicles;
                      same kind as rain, so it shows up when the ground stays soft after the rain stops
    NWS alerts        by event (NWS_EVENTS), e.g. Tornado Warning 10, Wind Advisory 4.5

Site score = worst hazard + 0.25 x second + 0.10 x third, capped at 10 (combine()); the second and third only add
when they're high (>= 5) on their own. Compounding is across kinds of hazard (heat, wind, storms, water): a Wind
Advisory and the gusts it warns about are the same wind, so only the worse of the two counts.

This is the 'rules' scorer (the dashboard's Real-time view); the ML model is scored separately ('ml', Predictive).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SEVERITY = 0.05  # below this a hazard isn't shown at all

LEVEL_GUIDANCE = {
    "low": "Normal operations",
    "moderate": "Work with precautions",
    "high": "Restricted work",
    "extreme": "Stop non-essential work",
}


@dataclass(frozen=True)
class Hazard:
    key: str
    severity: float  # 0-10
    label: str
    action: str | None = None

    def factor(self) -> dict:
        """The RiskFactor shape stored in hazard_scores.factors and sent to the frontend."""
        return {"key": self.key, "label": self.label, "contribution": round(self.severity, 1), "action": self.action}


def piecewise(value: float, anchors: list[tuple[float, float]]) -> float:
    """Linear interpolation through (x, y) anchors sorted by x; flat beyond both ends."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:], strict=False):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return anchors[-1][1]


def _hazard(key: str, severity: float, label: str, action: str | None) -> Hazard | None:
    severity = max(0.0, min(10.0, severity))
    return Hazard(key, severity, label, action) if severity >= MIN_SEVERITY else None


# --- Heat ---------------------------------------------------------------------------------------------------

HEAT_ANCHORS = [(80, 0.0), (91, 2.5), (103, 5.0), (108, 6.0), (115, 9.0), (125, 10.0)]


def nws_heat_index(temp_f: float | None, rh: float | None) -> float | None:
    """NWS heat index (°F) from air temperature and relative humidity: Rothfusz regression + NWS adjustments.

    This is the shade heat index OSHA's bands are defined on (https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml).
    """
    if temp_f is None or rh is None or math.isnan(temp_f) or math.isnan(rh):
        return None
    t = float(temp_f)
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        return round(simple, 1)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
          - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round(hi, 1)


# (at least °F, label suffix, action), highest first
HEAT_BANDS = [
    (125, " · NWS extreme danger", "Stop outdoor work; heat stroke is likely"),
    (115, " · OSHA: no strenuous work", "Stop strenuous work; reschedule non-essential tasks"),
    (103, " · OSHA high risk", "Limit exertion; enforce work/rest cycles; watch crews at all times"),
    (91, " · OSHA moderate risk", "Water every 15-20 min, shaded breaks, buddy system"),
    (float("-inf"), "", "Provide water and shade"),
]


def _band(value: float, bands: list[tuple]) -> tuple:
    return next(b for b in bands if value >= b[0])


def heat(hi: float | None) -> Hazard | None:
    if hi is None:
        return None
    _, suffix, action = _band(hi, HEAT_BANDS)
    return _hazard("heat_index", piecewise(hi, HEAT_ANCHORS), f"Heat index {round(hi)}°F{suffix}", action)


# --- Storms -------------------------------------------------------------------------------------------------

LIGHTNING_ACTION = "Stop work; shelter in a building or hard-topped vehicle until 30 min after the last strike"
STORM_ACTION = "Don't start tasks you can't stop quickly; know where to shelter"


def lightning(nearest_mi: float | None = None) -> Hazard:
    where = f", nearest {nearest_mi:.1f} mi" if nearest_mi is not None else ""
    return Hazard("lightning", 10.0, f"Lightning within 10 miles{where}", LIGHTNING_ACTION)


def thunderstorm(weather_code: int | None, forecast: bool) -> Hazard | None:
    if weather_code is None or not 95 <= weather_code <= 99:
        return None
    hail = weather_code in (96, 99)
    label = ("Thunderstorms with hail" if hail else "Thunderstorms") + (" forecast" if forecast else "")
    return _hazard("thunderstorm", 9.0 if hail else 8.0, label, STORM_ACTION)


def storm_potential(cape: float | None, rain_chance_pct: float | None) -> Hazard | None:
    if cape is None or cape < 1000:
        return None
    chance = rain_chance_pct / 100 if rain_chance_pct is not None else 0.5
    severity = min(5.0, piecewise(cape, [(1000, 0.0), (3500, 5.0)]) * chance)
    pct = f", {round(rain_chance_pct)}% rain chance" if rain_chance_pct is not None else ""
    action = "Watch radar; plan shelter for afternoon storms" if severity >= 2.5 else None
    return _hazard("thunderstorm", severity, f"Storm energy (CAPE {round(cape):,}{pct})", action)


# --- Wind ---------------------------------------------------------------------------------------------------

WIND_ANCHORS = [(15, 0.0), (20, 2.5), (28, 5.0), (40, 7.5), (58, 10.0)]
WIND_BANDS = [
    (58, " · severe-storm strength", "Stop outdoor work; shelter from flying debris"),
    (40, " · too strong for elevated work", "Stop elevated work and crane lifts; secure loose material"),
    (28, " · above the 28 mph aerial-lift limit", "Ground aerial lifts and bucket trucks"),
    (20, " · personnel lifts need sign-off", "Qualified person must clear personnel lifts (OSHA 1926.1431)"),
    (float("-inf"), "", None),
]


def wind(gust_mph: float | None) -> Hazard | None:
    if gust_mph is None:
        return None
    _, suffix, action = _band(gust_mph, WIND_BANDS)
    return _hazard("wind", piecewise(gust_mph, WIND_ANCHORS), f"Gusts {round(gust_mph)} mph{suffix}", action)


# --- Rain, flooding, ground ---------------------------------------------------------------------------------

RAIN_RATE_ANCHORS = [(0.05, 0.0), (0.1, 1.0), (0.3, 3.0), (1.0, 7.0), (2.0, 9.0)]
RAIN_24H_ANCHORS = [(0.5, 0.0), (1.0, 2.0), (3.0, 5.0), (5.0, 7.5), (8.0, 9.0)]
SOIL_ANCHORS = [(0.25, 0.0), (0.35, 3.0), (0.45, 6.0)]
RAIN_72H_ANCHORS = [(1.0, 0.0), (2.0, 2.5), (4.0, 5.0), (6.0, 6.0)]
GROUND_CAP = 6.0


RAIN_RATE_BANDS = [
    (1.0, "Downpour {:.1f} in/h · flash flooding likely",
     "Move crews and equipment off low ground; avoid low-water crossings"),
    (0.3, "Heavy rain {:.1f} in/h", "Slow down on access roads; watch for ponding"),
    (float("-inf"), "Rain {:.2f} in/h", None),
]


def rain_rate(inches_per_hour: float | None) -> Hazard | None:
    if inches_per_hour is None:
        return None
    _, label, action = _band(inches_per_hour, RAIN_RATE_BANDS)
    return _hazard("downpour", piecewise(inches_per_hour, RAIN_RATE_ANCHORS), label.format(inches_per_hour), action)


def rain_24h(inches: float | None) -> Hazard | None:
    if inches is None:
        return None
    if inches >= 3:
        action = "Check access roads for washouts before mobilizing"
    elif inches >= 1:
        action = "Expect soft, slick access roads"
    else:
        action = None
    return _hazard("rain_24h", piecewise(inches, RAIN_24H_ANCHORS), f"{inches:.1f} in of rain in 24 h", action)


def ground(soil_moisture: float | None, rain_72h_in: float | None) -> Hazard | None:
    soil = piecewise(soil_moisture, SOIL_ANCHORS) if soil_moisture is not None else 0.0
    rain = piecewise(rain_72h_in, RAIN_72H_ANCHORS) if rain_72h_in is not None else 0.0
    severity = min(GROUND_CAP, max(soil, rain))
    if severity < MIN_SEVERITY:
        return None
    if soil >= rain:
        label = f"Saturated ground (soil moisture {round(soil_moisture * 100)}%)"
    else:
        label = f"{rain_72h_in:.1f} in of rain in 3 days · soft ground"
    action = "Use matting or tracked equipment on unpaved access" if severity >= 3 else None
    return _hazard("soil_moisture", severity, label, action)


# --- Alerts -------------------------------------------------------------------------------------------------

# NWS event (lowercase) -> (severity, action). Anything not listed falls back to NWS_SEVERITY_FALLBACK.
NWS_EVENTS: dict[str, tuple[float, str]] = {
    "tornado warning": (10.0, "Shelter immediately in a sturdy building, away from windows"),
    "extreme wind warning": (10.0, "Shelter immediately; stop all outdoor work"),
    "hurricane warning": (10.0, "Stop work, secure the site, and move crews out as directed"),
    "storm surge warning": (9.0, "Move crews and equipment out of the surge zone"),
    "flash flood warning": (9.0, "Move to higher ground; never drive through flooded roads"),
    "severe thunderstorm warning": (9.0, "Stop work and shelter; expect damaging gusts and lightning"),
    "extreme heat warning": (8.5, "Stop strenuous work; reschedule non-essential tasks"),
    "excessive heat warning": (8.5, "Stop strenuous work; reschedule non-essential tasks"),
    "tropical storm warning": (8.0, "Secure the site; stop elevated work and crane lifts"),
    "high wind warning": (8.0, "Stop elevated work and crane lifts; secure loose material"),
    "flood warning": (6.5, "Avoid flooded roads and low areas near rivers"),
    "tornado watch": (6.0, "Be ready to shelter quickly; keep a weather radio on"),
    "hurricane watch": (5.0, "Prepare to secure the site within 48 hours"),
    "tropical storm watch": (5.0, "Prepare to secure the site"),
    "severe thunderstorm watch": (5.0, "Don't start tasks you can't stop quickly"),
    "heat advisory": (5.0, "Enforce water, rest and shade; watch for heat illness"),
    "wind advisory": (4.5, "Ground aerial lifts if gusts pass 28 mph; secure loose material"),
    "flood watch": (4.5, "Watch low-lying access roads; plan routes to high ground"),
    "flash flood watch": (4.5, "Watch low-lying access roads; plan routes to high ground"),
    "extreme heat watch": (4.0, "Plan early starts and extra rest breaks"),
    "excessive heat watch": (4.0, "Plan early starts and extra rest breaks"),
    "red flag warning": (4.0, "No hot work or open flames; keep extinguishers ready"),
    "dense fog advisory": (3.0, "Delay equipment moves until visibility improves"),
    "fire weather watch": (2.5, "Limit hot work"),
}
NWS_SEVERITY_FALLBACK = {"Extreme": 8.0, "Severe": 6.0, "Moderate": 4.0, "Minor": 2.0}
OTHER_ALERT_SEVERITY = {"danger": 8.0, "warning": 5.0, "info": 2.0}  # crew reports, future USGS rule, ...


def nws_event(event: str, nws_severity: str | None = None) -> tuple[float, str | None]:
    """(severity 0-10, action) for an NWS event name."""
    known = NWS_EVENTS.get(event.strip().lower())
    if known:
        return known
    return NWS_SEVERITY_FALLBACK.get(nws_severity or "", 2.0), "Check the NWS alert for details"


def badge_for(severity: float) -> str:
    """App alert badge for a 0-10 severity: danger / warning / info."""
    return "danger" if severity >= 7.5 else "warning" if severity >= 4 else "info"


def alert(a: dict) -> Hazard:
    """Hazard for an active app alert.

    `a` has "type", "severity", "title" and optionally "nws_event", "nws_severity", "nearest_mi".
    """
    if a["type"] == "lightning":
        return lightning(a.get("nearest_mi"))
    if a.get("nws_event"):
        severity, action = nws_event(a["nws_event"], a.get("nws_severity"))
        return Hazard(f"alert_{a['type']}", severity, a["nws_event"], action)
    return Hazard(f"alert_{a['type']}", OTHER_ALERT_SEVERITY.get(a["severity"], 2.0), a["title"], None)


# --- Combining ----------------------------------------------------------------------------------------------

COMPOUND = (1.0, 0.25, 0.10)  # weights for the worst, second and third kind of hazard
# A second or third hazard only adds when it's serious on its own (high). Otherwise ordinary Florida summer days
# (heat index ~100°F, OSHA "moderate", plus a breezy hour) would tip into "high" without anything being high.
COMPOUND_MIN = 5.0

# Hazard key -> kind. Hazards of one kind describe the same danger, so they don't compound with each other.
KINDS = {
    "heat_index": "heat", "alert_heat": "heat",
    "wind": "wind", "alert_wind": "wind",
    "lightning": "storm", "thunderstorm": "storm", "alert_storm": "storm",
    # Wet ground comes from the same rain, so it only matters when it's worse than the rain itself (days after).
    "downpour": "water", "rain_24h": "water", "alert_flood": "water", "soil_moisture": "water",
}


def combine(hazards: list[Hazard | None], top: int = 3) -> tuple[float, list[dict]]:
    """Site score from its hazards and the top factors.

    Score = worst kind of hazard + 0.25 x the second kind + 0.10 x the third (each only if it's high, >= 5),
    capped at 10. Factors are the `top` individual hazards, worst first.
    """
    present = sorted((h for h in hazards if h is not None), key=lambda h: h.severity, reverse=True)
    worst_per_kind: dict[str, float] = {}
    for h in present:
        worst_per_kind.setdefault(KINDS.get(h.key, h.key), h.severity)
    kinds = sorted(worst_per_kind.values(), reverse=True)
    counted = kinds[:1] + [s for s in kinds[1:] if s >= COMPOUND_MIN]
    score = min(10.0, sum(w * s for w, s in zip(COMPOUND, counted, strict=False)))
    return round(score, 1), [h.factor() for h in present[:top]]
