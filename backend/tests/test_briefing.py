"""planit.worker.briefing.generate: when it's due, the facts, the template and the Gemini path (no network, no DB)."""

import json
from datetime import UTC, date, datetime, timedelta

from planit.worker import jobs
from planit.worker.briefing import generate as G

NY = "America/New_York"
DAY = date(2026, 10, 18)
START, END = G.work_window(DAY, NY)  # 6 AM - 6 PM EDT = 10:00 - 22:00 UTC


def hour(h_local: int) -> datetime:
    return START + timedelta(hours=h_local - G.WORK_START)


def test_due_after_6_pm_local_and_for_the_next_day():
    six_pm_ny = datetime(2026, 10, 17, 22, 0, tzinfo=UTC)
    assert G.is_due(six_pm_ny, NY) and not G.is_due(six_pm_ny - timedelta(minutes=1), NY)
    assert not G.is_due(six_pm_ny, "America/Los_Angeles")  # still 3 PM there
    assert G.next_work_day(six_pm_ny, NY) == DAY
    assert G.next_work_day(datetime(2026, 10, 18, 3, 30, tzinfo=UTC), "Pacific/Honolulu") == DAY  # 5:30 PM in HI
    assert (START.hour, END.hour) == (10, 22)


def facts(**over):
    scores = [{"scorer": "ml", "score": 6.2, "factors": []},
              {"scorer": "rules", "score": 8.0, "factors": [
                  {"key": "thunderstorm", "label": "Thunderstorms forecast", "contribution": 8.0,
                   "action": "Don't begin tasks you can't stop quickly"},
                  {"key": "heat_index", "label": "Heat index 106°F", "contribution": 5.4,
                   "action": "Water, rest, shade"},
                  {"key": "wind", "label": "Gusts 18 mph", "contribution": 1.5, "action": None}]}]
    nws = [{"ts": hour(h), "temp_f": 94.0, "humidity_pct": 60.0, "gust_mph": 30.0 if h == 15 else 12.0,
            "precip_in": 0.3 if h >= 14 else 0.0, "thunder_prob_pct": 60 if 14 <= h < 17 else 10} for h in range(6, 18)]
    args = {"scores": scores, "nws": nws, "open_meteo": [], "alerts": [], "tz": NY} | over
    return G.build_facts(**args)


def test_facts_peaks_storm_window_and_actions():
    f = facts()
    assert f["risk_score"] == 6.2 and f["level"] == "high" and f["real_time_peak"] == 8.0
    assert f["peak_heat_index_f"] >= 103 and f["peak_heat_time"]
    assert f["storm_window"] == "2 PM - 5 PM"
    assert f["max_gust_mph"] == 30 and f["max_gust_time"] == "3 PM"
    assert f["rain_in"] == 1.2
    assert f["top_hazards"] == ["Thunderstorms forecast", "Heat index 106°F"]  # gusts under 2.5 dropped
    assert f["recommendations"][0].startswith("Start early")
    assert "Don't begin tasks you can't stop quickly" in f["recommendations"]
    assert f["peak_smoke_aqi"] is None  # no smoke data: nothing said about it


def test_facts_with_warnings_and_cold():
    alerts = [{"type": "nws", "title": "Blizzard Warning issued", "meta": {"nws_event": "Blizzard Warning"}}]
    nws = [{"ts": hour(h), "temp_f": -5.0, "wind_mph": 30.0, "snowfall_in": 0.5} for h in range(6, 18)]
    f = facts(alerts=alerts, nws=nws)
    assert f["nws_alerts"] == ["Blizzard Warning"] and f["min_wind_chill_f"] < -25 and f["snowfall_in"] == 6.0
    assert any("whiteout" in r for r in f["recommendations"])


def test_facts_with_a_nearby_wildfire_and_smoke():
    fire = {"type": "wildfire", "title": "Creek Fire 4 mi away, 12,000 acres",
            "meta": {"source": "nifc", "rule_severity": 7.2, "action": "Set to leave: two exit routes"}}
    air = [{"ts": hour(h), "us_aqi_pm2_5": 120.0 + 10 * h} for h in range(6, 18)]  # peaks at 5 PM: AQI 290
    f = facts(alerts=[fire], air=air)
    assert f["nws_alerts"] == ["Creek Fire 4 mi away, 12,000 acres"]
    assert "Set to leave: two exit routes" in f["recommendations"]
    assert f["peak_smoke_aqi"] == 290 and f["peak_smoke_time"] == "5 PM"
    assert "Smoke: air quality index up to 290 around 5 PM." in G.template_summary(f)
    clean = facts(air=[{"ts": hour(9), "us_aqi_pm2_5": 60.0}])
    assert clean["peak_smoke_aqi"] is None  # below 101 it isn't a hazard


def test_template_summary_reads_the_facts():
    text = G.template_summary(facts())
    assert text.startswith("High risk tomorrow (Predictive 6.2 · Real-time peak 8.0 out of 10).")
    assert "Thunderstorms likely 2 PM - 5 PM." in text and "Gusts to 30 mph." in text
    assert G.template_summary({**facts(), "risk_score": None}).startswith("No forecast scores")


def test_site_label_without_a_state():
    assert G._site_label({"name": "Turkey Point", "state": "FL"}) == "Turkey Point, FL"
    assert G._site_label({"name": "New yard", "state": None}) == "New yard"


def test_gemini_numbers_must_come_from_the_facts():
    f = facts()
    assert G.valid_summary("High risk: storms 2 PM - 5 PM, gusts to 30 mph. Start early.", f)
    assert not G.valid_summary("High risk: gusts to 75 mph tomorrow afternoon, take care.", f)  # 75 isn't a fact
    assert not G.valid_summary("Short", f)


class ApiError(Exception):
    """Like google.genai.errors.APIError: carries the HTTP status as `code`."""

    def __init__(self, code):
        super().__init__(f"{code} error")
        self.code = code


class FakeModels:
    """`replies`: model name -> list of replies (an Exception is raised), consumed in order."""

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        queue = self.replies.get(model) or [ApiError(404)]
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return type("Resp", (), {"text": reply})()


def fake_client(replies):
    return type("Client", (), {"models": FakeModels(replies if isinstance(replies, dict) else
                                                    {G.settings.gemini_model: [replies]})})()


GOOD = "High risk tomorrow: storms 2 PM - 5 PM, gusts to 30 mph."


def test_gemini_keeps_valid_summaries_and_drops_the_rest():
    f = facts()
    batch = [{"site_id": 1, "site": "A, FL", "facts": f}, {"site_id": 2, "site": "B, TX", "facts": f}]
    reply = json.dumps([{"site_id": 1, "summary": GOOD},
                        {"site_id": 2, "summary": "Gusts to 99 mph, evacuate the county."},
                        {"site_id": 3, "summary": "Not in this batch, so ignored entirely."}])
    assert G.gemini_summaries(batch, fake_client(reply)) == ({1: GOOD}, G.settings.gemini_model)


def test_a_retired_model_hands_over_and_a_busy_one_is_retried(monkeypatch):
    monkeypatch.setattr(G, "RETRY_WAIT_S", 0)
    monkeypatch.setattr(G.settings, "gemini_model", "gemini-2.5-flash")  # what the server's .env still pins
    monkeypatch.setattr(G.settings, "gemini_fallback_models", "gemini-flash-latest, gemini-3.8-flash")
    batch = [{"site_id": 1, "site": "A, FL", "facts": facts()}]
    ok = json.dumps([{"site_id": 1, "summary": GOOD}])
    client = fake_client({"gemini-2.5-flash": [ApiError(404)], "gemini-flash-latest": [ApiError(503), ok]})
    assert G.gemini_summaries(batch, client) == ({1: GOOD}, "gemini-flash-latest")
    assert client.models.calls == ["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-latest"]

    down = fake_client({"gemini-flash-latest": [ApiError(503)], "gemini-3.8-flash": ["not json"]})
    assert G.gemini_summaries(batch, down) == ({}, None)  # nobody answered: the template covers it
    assert down.models.calls == ["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-latest", "gemini-3.8-flash"]


def test_without_a_key_gemini_is_skipped(monkeypatch):
    monkeypatch.setattr(G.settings, "gemini_api_key", None)
    assert G.gemini_summaries([{"site_id": 1, "site": "A, FL", "facts": facts()}]) == ({}, None)  # all template


def test_generate_now_job_is_registered(monkeypatch):
    seen = []
    monkeypatch.setattr(G, "generate_all", lambda: seen.append(True) or 160)
    jobs.HANDLERS["generate_briefings"]({})
    assert seen == [True]
