"""Pure-function tests for scripts/load_sites.py (no network, no database, no Excel file)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from load_sites import (  # noqa: E402
    SELECTED_SITES,
    find_header_row,
    plants_from_generators,
    select,
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
        gen(9, 999.0, "Nuclear", state="GA"),  # other states ignored
        gen("", 5.0, "Solar"),  # blank plant id ignored
    ]
    plants = plants_from_generators(HEADER, rows)
    assert set(plants) == {7, 8}
    assert plants[7].capacity_mw == 550.5
    assert plants[7].plant_type == "Natural Gas Fired Combined Cycle"


def test_plants_without_coordinates_are_skipped():
    plants = plants_from_generators(HEADER, [gen(1, 10, "Solar", lat=" "), gen(2, 10, "Solar")])
    assert set(plants) == {2}


def test_missing_columns_raise():
    with pytest.raises(ValueError, match="Missing columns"):
        plants_from_generators(["Plant ID"], [])


def test_timezone_split_at_apalachicola():
    assert timezone_for(-87.2) == "America/Chicago"  # Pensacola
    assert timezone_for(-85.07) == "America/Chicago"  # Jackson County
    assert timezone_for(-84.86) == "America/New_York"  # Gadsden County (Jim Woodruff Dam)
    assert timezone_for(-80.3) == "America/New_York"  # Turkey Point


def test_select_reports_missing_ids():
    some_id = next(iter(SELECTED_SITES))
    plants = plants_from_generators(HEADER, [gen(some_id, 10, "Solar")])
    found, missing = select(plants)
    assert [p.id for p in found] == [some_id]
    assert len(missing) == len(SELECTED_SITES) - 1


def test_selection_size():
    assert 55 <= len(SELECTED_SITES) <= 65
