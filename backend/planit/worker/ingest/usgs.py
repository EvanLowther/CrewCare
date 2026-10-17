"""Owner: Person A. Hours 12-15.

River stage for gauges in `river_gauges` -> `river_levels`.
API: https://waterservices.usgs.gov/nwis/iv/?format=json&sites=<ids>&parameterCd=00065,00060
(00065 = gage height ft, 00060 = discharge cfs). Candidate Florida rivers: St. Johns,
Apalachicola, Suwannee, Peace, Caloosahatchee.
"""


def poll() -> None:
    raise NotImplementedError
