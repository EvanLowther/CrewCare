"""Owner: Person A. Hours 4-8.

Active NWS alerts per site -> `nws_alerts`, then create/clear matching rows in `alerts`
(type='nws' or a specific type such as 'heat'/'flood', dedupe_key = NWS alert id).
API: https://api.weather.gov/alerts/active?point={lat},{lon}. A User-Agent header is required
(settings.nws_user_agent).
"""


def poll() -> None:
    raise NotImplementedError
