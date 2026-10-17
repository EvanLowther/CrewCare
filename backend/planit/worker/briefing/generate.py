"""Owner: Person A. Hours 19-21.

At 6 PM in each site's own timezone (sites.timezone), write tomorrow's briefing to `briefings`.
Uses Gemini (settings.gemini_api_key / settings.gemini_model) to write `summary`; falls back to a
plain template when there is no key or the call fails (generated_by='template').
"""


def run_due() -> None:
    """Called every 5 min; generates briefings only for sites where it's just past 6 PM local."""
    raise NotImplementedError


def generate_all() -> int:
    """Generate tomorrow's briefing for every site now (demo button). Returns the count."""
    raise NotImplementedError
