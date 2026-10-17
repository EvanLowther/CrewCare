"""Load the ~60 demo sites (Florida power plants) from EIA-860M into `sites`.

    python scripts/load_sites.py                 # dry run: print the selection, write nothing
    python scripts/load_sites.py --write         # upsert into Tiger
    python scripts/load_sites.py --write --prune # ...and delete sites that aren't in SELECTED_SITES
    python scripts/load_sites.py path/to/file.xlsx [--write]

Get the latest monthly file from https://www.eia.gov/electricity/data/eia860m/ and save it in
data/raw/ (git-ignored). With no path, the newest data/raw/*generator*.xlsx is used.

EIA-860M lists generators, not plants: rows are grouped by Plant ID, capacity is summed, and the
largest generator's technology becomes the plant type. Safe to re-run (upsert on id).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"

# West of the Apalachicola River is Central time. Every selected site east of the river sits
# east of -85.0 and every one west of it sits west of -85.0, so a longitude cut is enough here.
CENTRAL_TIME_WEST_OF_LON = -85.0

# Plant ID -> why it's in the demo. Picked from the August 2026 file for a mix of size, technology
# and hazards; keep near-duplicate sites out (e.g. Lauderdale shares a location with Dania Beach 7).
SELECTED_SITES: dict[int, str] = {
    # Largest plants: where most crews and equipment are
    56407: "largest plant in Florida",
    628: "coal + gas, Gulf coast storm surge",
    621: "nuclear, next to Biscayne Bay and the Everglades",
    6042: "large gas plant, Tampa Bay area",
    612: "on the Caloosahatchee River",
    6043: "large gas plant next to the Everglades",
    620: "on Lake Monroe / St. Johns River",
    7873: "Tampa Bay waterfront",
    7302: "large gas plant, central Florida",
    6045: "nuclear, barrier island on the Atlantic",
    136: "coal, on the St. Johns River",
    645: "Tampa Bay waterfront",
    60345: "north of Lake Okeechobee",
    634: "Tampa Bay waterfront",
    7242: "large gas plant, central Florida",
    65978: "Fort Lauderdale, dense urban site",
    667: "Jacksonville, St. Johns River mouth",
    617: "Port Everglades, Atlantic coast",
    619: "Riviera Beach, Atlantic coast",
    609: "Cape Canaveral, Atlantic coast",
    564: "coal + gas, Orlando",
    8049: "peaking plant, central Florida",
    8048: "Gulf coast, Pasco County",
    55286: "Brevard County, near the Indian River Lagoon",
    7380: "near the Peace River",
    7846: "Jacksonville, inland",
    6046: "peaking plant near the St. Johns River",
    55415: "near the Peace River",
    7238: "central Florida, Kissimmee",
    688: "Tallahassee",
    676: "Lakeland",
    663: "Gainesville",
    55318: "Indian River Lagoon",
    55412: "central Florida, Polk County",
    55414: "Pasco County, inland",
    56400: "Fort Pierce, Atlantic coast",
    56799: "Jacksonville, south",
    # Panhandle (Central time)
    641: "panhandle, Pensacola (Central time)",
    643: "panhandle, Panama City bay (Central time)",
    55242: "panhandle, Santa Rosa County (Central time)",
    65433: "panhandle solar on the Blackwater River (Central time)",
    65888: "panhandle solar, Okaloosa County (Central time)",
    65432: "panhandle solar near the Apalachicola basin (Central time)",
    # Rivers (flood warnings; USGS gauges get attached later)
    638: "on the Suwannee River",
    690: "Jim Woodruff Dam on the Apalachicola River",
    65871: "solar on the Caloosahatchee River",
    10611: "Palatka, on the St. Johns River",
    62750: "solar on the Little Manatee River",
    63518: "solar where the Suwannee and Withlacoochee meet",
    # South Florida / Everglades solar (heat, wildlife, swamp access roads)
    65423: "Everglades Solar Energy Center, Miami-Dade",
    65038: "Ghost Orchid solar, Big Cypress edge",
    65037: "Sawgrass solar, Big Cypress edge",
    68823: "Goldenrod solar, Collier County",
    62631: "Blue Heron solar, Hendry County",
    59993: "Babcock Ranch solar, Charlotte County",
    63110: "Sabal Palm solar, western Palm Beach County",
    62922: "solar on the Lake Okeechobee shore",
    # Everglades Agricultural Area and the Keys
    54627: "sugar-cane biomass, Everglades Agricultural Area",
    6584: "Key West: hurricanes and storm surge",
    10202: "biomass mill on the Amelia River, Fernandina Beach",
}


@dataclass(frozen=True)
class Plant:
    id: int
    name: str
    utility: str
    county: str
    plant_type: str
    capacity_mw: float
    latitude: float
    longitude: float

    @property
    def timezone(self) -> str:
        return timezone_for(self.longitude)


def timezone_for(longitude: float) -> str:
    return "America/Chicago" if longitude < CENTRAL_TIME_WEST_OF_LON else "America/New_York"


def find_header_row(rows: Iterable[Sequence[object]]) -> int:
    """Index of the first row containing a 'Plant ID' cell (the sheet has title rows above it)."""
    for i, row in enumerate(rows):
        if any(isinstance(c, str) and c.strip() == "Plant ID" for c in row):
            return i
    raise ValueError("No 'Plant ID' header row found. Is this an EIA-860M generator file?")


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def plants_from_generators(
    header: Sequence[object], rows: Iterable[Sequence[object]], state: str = "FL"
) -> dict[int, Plant]:
    """Group generator rows into plants for one state."""
    col = {str(name).strip(): i for i, name in enumerate(header) if name is not None}
    needed = ["Plant ID", "Plant Name", "Entity Name", "Plant State", "County", "Technology",
              "Nameplate Capacity (MW)", "Latitude", "Longitude"]
    missing = [n for n in needed if n not in col]
    if missing:
        raise ValueError(f"Missing columns in EIA file: {missing}")

    totals: dict[int, float] = {}
    largest: dict[int, tuple[float, Sequence[object]]] = {}
    for row in rows:
        if row[col["Plant State"]] != state:
            continue
        plant_id = _num(row[col["Plant ID"]])
        if plant_id is None:
            continue
        pid = int(plant_id)
        mw = _num(row[col["Nameplate Capacity (MW)"]]) or 0.0
        totals[pid] = totals.get(pid, 0.0) + mw
        if pid not in largest or mw > largest[pid][0]:
            largest[pid] = (mw, row)

    plants = {}
    for pid, (_, row) in largest.items():
        lat, lon = _num(row[col["Latitude"]]), _num(row[col["Longitude"]])
        if lat is None or lon is None:
            continue
        plants[pid] = Plant(
            id=pid,
            name=str(row[col["Plant Name"]]).strip(),
            utility=str(row[col["Entity Name"]]).strip(),
            county=str(row[col["County"]]).strip(),
            plant_type=str(row[col["Technology"]]).strip(),
            capacity_mw=round(totals[pid], 1),
            latitude=lat,
            longitude=lon,
        )
    return plants


def read_florida_plants(path: Path) -> dict[int, Plant]:
    from openpyxl import load_workbook  # only needed when reading the real file

    wb = load_workbook(path, read_only=True, data_only=True)
    rows = wb["Operating"].iter_rows(values_only=True)
    head = []
    for row in rows:  # consume title rows up to and including the header
        head.append(row)
        try:
            find_header_row([row])
            break
        except ValueError:
            continue
    return plants_from_generators(head[-1], rows)


def select(plants: dict[int, Plant]) -> tuple[list[Plant], list[int]]:
    """The selected plants (in SELECTED_SITES order) and any selected ids missing from the file."""
    found = [plants[pid] for pid in SELECTED_SITES if pid in plants]
    missing = [pid for pid in SELECTED_SITES if pid not in plants]
    return found, missing


UPSERT_SQL = """
INSERT INTO sites (id, name, utility, county, state, plant_type, capacity_mw, latitude, longitude, geom, timezone)
VALUES (%(id)s, %(name)s, %(utility)s, %(county)s, 'FL', %(plant_type)s, %(capacity_mw)s, %(latitude)s,
        %(longitude)s, ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography, %(timezone)s)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, utility = EXCLUDED.utility, county = EXCLUDED.county,
    plant_type = EXCLUDED.plant_type, capacity_mw = EXCLUDED.capacity_mw,
    latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, geom = EXCLUDED.geom,
    timezone = EXCLUDED.timezone
"""


def write(plants: list[Plant], prune: bool = False) -> list[str]:
    """Upsert the plants. With prune, also delete other sites and return their names.

    Pruning fails (and nothing is deleted) if weather, scores, alerts etc. already reference a site.
    """
    from planit.db import connection

    params = [{**p.__dict__, "timezone": p.timezone} for p in plants]
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, params)
        if not prune:
            return []
        cur.execute("DELETE FROM sites WHERE NOT (id = ANY(%s)) RETURNING name", ([p.id for p in plants],))
        return [r["name"] for r in cur.fetchall()]


def newest_raw_file() -> Path:
    files = sorted(RAW_DIR.glob("*generator*.xlsx"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"No EIA-860M file in {RAW_DIR}. Download one from https://www.eia.gov/electricity/data/eia860m/")
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", type=Path, help="EIA-860M .xlsx (default: newest in data/raw/)")
    parser.add_argument("--write", action="store_true", help="Upsert into the database (default: dry run)")
    parser.add_argument("--prune", action="store_true", help="With --write: delete sites not in SELECTED_SITES")
    args = parser.parse_args()

    path = args.file or newest_raw_file()
    print(f"Reading {path.name} ...")
    plants, missing = select(read_florida_plants(path))
    for i, p in enumerate(plants, 1):
        tz = "CT" if p.timezone == "America/Chicago" else "ET"
        print(f"{i:>2}. {p.id:>6}  {p.name[:34]:34} {p.plant_type[:30]:30} {p.capacity_mw:>7.1f} MW  "
              f"{p.county[:12]:12} {tz}  {SELECTED_SITES[p.id]}")
    print(f"\n{len(plants)} sites; Central time: {sum(p.timezone == 'America/Chicago' for p in plants)}")
    if missing:
        print(f"WARNING: selected plant ids not in this file (retired or renumbered?): {missing}")

    if args.write:
        removed = write(plants, prune=args.prune)
        print(f"Upserted {len(plants)} sites.")
        if removed:
            print(f"Pruned {len(removed)} sites not in the selection: {', '.join(removed)}")
    else:
        print("Dry run: nothing written. Re-run with --write to load into the database.")


if __name__ == "__main__":
    main()
