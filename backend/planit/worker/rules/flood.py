"""Owner: Person A. Hours 12-15.

Rule: for sites with a usgs_gauge_id, warn when 12 h rainfall (weather) is heavy AND the river is
rising toward action_stage_ft. Creates alerts type='flood', dedupe_key 'flood'.
"""


def evaluate() -> None:
    raise NotImplementedError
