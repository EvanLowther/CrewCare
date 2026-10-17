"""Pure-function tests for scripts/load_sites.py (no network, no database, no Excel file)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from load_sites import (  # noqa: E402
    MIN_SPACING_MI,
    SELECTED_SITES,
    Plant,
    allocate,
    find_header_row,
    miles,
    plants_from_generators,
    select,
    select_national,
    timezone_for,
)

HEADER = ["Entity ID", "Entity Name", "Plant ID", "Plant Name", "Plant State", "County",
          "Nameplate Capacity (MW)", "Technology", "Latitude", "Longitude"]


def gen(plant_id, mw, tech, state="FL", lat=27.0, lon=-81.0):
    return [1, "Utility Co", plant_id, f"Plant {plant_id}", state, "Polk", mw, tech, lat, lon]


def test_find_header_row_skips_title_rows():
    rows = [["Inventory of Operating Generators"], ["", ""], HEADER, gen(1, 10, "Solar")]
    assert find_header_row(rows) == 2
    with pytest.raises(ValueError):
        find_header_row([["no header here"]])


def test_generators_grouped_into_plants():
    rows = [
        gen(7, 100.0, "Natural Gas Steam Turbine"),
        gen(7, 400.0, "Natural Gas Fired Combined Cycle"),  # largest generator sets the type
        gen(7, 50.5, "Batteries"),
        gen(8, 20.0, "Solar Photovoltaic"),
        gen(9, 999.0, "Nuclear", state="GA"),
        gen("", 5.0, "Solar"),  # blank plant id ignored
    ]
    plants = plants_from_generators(HEADER, rows)
    assert set(plants) == {7, 8, 9}
    assert plants[7].capacity_mw == 550.5
    assert plants[7].plant_type == "Natural Gas Fired Combined Cycle"
    assert plants[9].state == "GA"
    assert set(plants_from_generators(HEADER, rows, states={"FL"})) == {7, 8}


def test_plants_without_coordinates_are_skipped():
    plants = plants_from_generators(HEADER, [gen(1, 10, "Solar", lat=" "), gen(2, 10, "Solar")])
    assert set(plants) == {2}


def test_missing_columns_raise():
    with pytest.raises(ValueError, match="Missing columns"):
        plants_from_generators(["Plant ID"], [])


def test_florida_timezone_split_at_apalachicola():
    assert timezone_for("FL", 30.57, -87.2) == "America/Chicago"  # Pensacola
    assert timezone_for("FL", 30.66, -85.07) == "America/Chicago"  # Jackson County
    assert timezone_for("FL", 30.71, -84.86) == "America/New_York"  # Gadsden County (Jim Woodruff Dam)
    assert timezone_for("FL", 25.44, -80.3) == "America/New_York"  # Turkey Point


def test_timezones_outside_florida():
    assert timezone_for("AZ", 33.39, -112.86) == "America/Phoenix"  # Palo Verde: no daylight saving
    assert timezone_for("HI", 21.36, -158.13) == "Pacific/Honolulu"
    assert timezone_for("AK", 61.22, -149.72) == "America/Anchorage"
    assert timezone_for("CA", 35.21, -120.85) == "America/Los_Angeles"
    assert timezone_for("TX", 31.76, -106.48) == "America/Denver"  # El Paso is Mountain time
    with pytest.raises(ValueError, match="No timezone"):
        timezone_for("CA", 33.0, -125.0)  # Pacific Ocean


def test_select_reports_missing_ids():
    some_id = next(iter(SELECTED_SITES))
    plants = plants_from_generators(HEADER, [gen(some_id, 10, "Solar")])
    found, missing = select(plants)
    assert [p.id for p in found] == [some_id]
    assert len(missing) == len(SELECTED_SITES) - 1


def test_selection_size():
    assert 55 <= len(SELECTED_SITES) <= 65


def test_allocate_one_per_state_then_by_share():
    alloc = allocate({"TX": 600, "CA": 400, "VT": 2, "RI": 5}, total=10)
    assert alloc == {"TX": 5, "CA": 3, "VT": 1, "RI": 1}
    assert sum(allocate({"A": 1, "B": 1, "C": 50}, total=3).values()) == 3


def test_allocate_never_gives_a_state_more_than_it_has():
    assert allocate({"A": 2, "B": 3}, total=5) == {"A": 2, "B": 3}
    assert allocate({"A": 2, "B": 2}, total=9) == {"A": 2, "B": 2}  # asks for more than exist
    with pytest.raises(ValueError):
        allocate({"A": 5, "B": 5}, total=1)


def plant(pid, state, mw, lat, lon):
    return Plant(id=pid, name=f"P{pid}", utility="U", county="C", state=state, plant_type="Nuclear",
                 capacity_mw=mw, latitude=lat, longitude=lon)


def test_select_national_largest_first_spread_apart_and_skips_florida():
    plants = {p.id: p for p in [
        plant(1, "TX", 3000, 29.0, -95.0),
        plant(2, "TX", 2500, 29.1, -95.1),  # ~9 mi from 1: skipped
        plant(3, "TX", 2000, 32.0, -97.0),
        plant(4, "TX", 40, 33.0, -100.0),  # under 50 MW: never picked
        plant(5, "GA", 1000, 33.0, -82.0),
        plant(6, "FL", 9000, 27.0, -81.0),
    ]}
    chosen = select_national(plants, total=3)
    assert [p.id for p in chosen] == [5, 1, 3]
    assert miles(29.0, -95.0, 29.1, -95.1) < MIN_SPACING_MI
