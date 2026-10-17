"""Owner: Person A. Hours 8-12.

Build one row per (site, day): features from `weather_daily` (+ month, prior-day rain, soil trend),
label = 1 if a hazardous `storm_events` row happened within ~25 mi or in the site's county that day.
Live scoring must use the same feature function on forecast data.
"""

FEATURES = [
    "max_heat_index_f",
    "total_precip_in",
    "precip_prev_3d_in",
    "avg_soil_moisture",
    "max_gust_mph",
    "max_cape_jkg",
    "month",
]


def training_frame():
    raise NotImplementedError
