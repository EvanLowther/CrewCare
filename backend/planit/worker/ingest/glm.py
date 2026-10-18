"""Owner: Person A. Live lightning from GOES GLM -> `lightning_strikes` (source 'glm').

NOAA's Geostationary Lightning Mapper sees every flash over the Americas from orbit and publishes them on AWS with no
key: buckets noaa-goes19 (GOES-East) and noaa-goes18 (GOES-West), product GLM-L2-LCFA, one NetCDF (HDF5) file every
20 s listing each flash's latitude, longitude and time, about 20 s after it happens. GLM counts all lightning (in
cloud and to ground) to within ~8 km, which suits the stop-work rule: NOAA's "when thunder roars" counts any flash.

Each poll lists the files of the last LOOKBACK on both satellites, reads the ones this process hasn't read, keeps
good-quality flashes within settings.lightning_radius_mi of a site, and writes them; rules/lightning.evaluate()
(every 15 s) turns them into the stop-work alert and its 30-minute countdown. GOES-West serves the sites west of
WEST_OF (the West, Alaska, Hawaii) and GOES-East the rest, so a flash both satellites see counts once. Inserts skip
flashes already stored, so a restart that reads a file again adds nothing. About 25 KB/s of downloads.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np

from planit.config import settings
from planit.db import connection

log = logging.getLogger(__name__)

SATELLITES = {"noaa-goes19": "east", "noaa-goes18": "west"}
WEST_OF = -105.0  # sites at or west of this longitude use GOES-West
PRODUCT = "GLM-L2-LCFA"
LOOKBACK = timedelta(minutes=3)
EARTH_RADIUS_MI = 3958.8
GOOD_QUALITY = 0  # flash_quality_flag
_START = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})(\d)_")

_read: dict[str, datetime] = {}  # file key -> its start time, for files this process has read

INSERT_SQL = """
INSERT INTO lightning_strikes (ts, latitude, longitude, geom, source)
SELECT %(ts)s, %(lat)s, %(lon)s, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, 'glm'
WHERE NOT EXISTS (SELECT 1 FROM lightning_strikes WHERE source = 'glm' AND ts = %(ts)s
                  AND latitude = %(lat)s AND longitude = %(lon)s)
"""


def file_start(key: str) -> datetime | None:
    """Scan start time from a GLM file name: ..._s20262910339000_e..._c....nc (year, day of year, h, m, s, tenths)."""
    m = _START.search(key)
    if not m:
        return None
    year, doy, h, mi, s, tenth = (int(g) for g in m.groups())
    return datetime(year, 1, 1, h, mi, s, tenth * 100_000, tzinfo=UTC) + timedelta(days=doy - 1)


def hour_prefixes(since: datetime, now: datetime) -> list[str]:
    """The S3 prefixes (one per UTC hour) that cover [since, now]."""
    out, hour = [], since.replace(minute=0, second=0, microsecond=0)
    while hour <= now:
        out.append(f"{PRODUCT}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/")
        hour += timedelta(hours=1)
    return out


def list_keys(client: httpx.Client, bucket: str, since: datetime, now: datetime) -> list[str]:
    """GLM files on `bucket` whose scan started at or after `since`, oldest first."""
    keys = []
    for prefix in hour_prefixes(since, now):
        resp = client.get(f"https://{bucket}.s3.amazonaws.com/", params={"list-type": "2", "prefix": prefix})
        resp.raise_for_status()
        keys += re.findall(r"<Key>([^<]+\.nc)</Key>", resp.text)
    return sorted(k for k in keys if (t := file_start(k)) is not None and t >= since)


def flashes(data: bytes) -> list[tuple[datetime, float, float]]:
    """(time, lat, lon) of each good-quality flash in one GLM file."""
    import h5py

    with h5py.File(io.BytesIO(data), "r") as f:
        lat, lon = f["flash_lat"][:].astype(float), f["flash_lon"][:].astype(float)
        if lat.size == 0:
            return []
        offset_var = f["flash_time_offset_of_first_event"]
        raw = offset_var[:].astype(np.int64)
        if offset_var.attrs.get("_Unsigned") in (b"true", "true"):
            raw %= 65536  # stored as int16 but meant unsigned
        seconds = raw * float(offset_var.attrs.get("scale_factor", [1.0])[0]) + float(
            offset_var.attrs.get("add_offset", [0.0])[0])
        quality = f["flash_quality_flag"][:]
        start = f.attrs["time_coverage_start"]
        start = datetime.fromisoformat((start.decode() if isinstance(start, bytes) else start).replace("Z", "+00:00"))
    good = quality == GOOD_QUALITY
    return [(start + timedelta(seconds=float(s)), float(a), float(o))
            for s, a, o in zip(seconds[good], lat[good], lon[good], strict=True)]


def near_sites(found: list[tuple[datetime, float, float]], sites: list[dict],
               radius_mi: float) -> list[tuple[datetime, float, float]]:
    """The flashes within `radius_mi` of any of `sites` ({"latitude", "longitude"})."""
    if not found or not sites:
        return []
    lat = np.radians([f[1] for f in found])[:, None]
    lon = np.radians([f[2] for f in found])[:, None]
    slat = np.radians([s["latitude"] for s in sites])[None, :]
    slon = np.radians([s["longitude"] for s in sites])[None, :]
    a = np.sin((slat - lat) / 2) ** 2 + np.cos(lat) * np.cos(slat) * np.sin((slon - lon) / 2) ** 2
    miles = 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a)).min(axis=1)
    return [f for f, m in zip(found, miles, strict=True) if m <= radius_mi]


def sites_for(bucket: str, sites: list[dict]) -> list[dict]:
    west = SATELLITES[bucket] == "west"
    return [s for s in sites if (s["longitude"] <= WEST_OF) == west]


def poll(now: datetime | None = None) -> int:
    """Read new GLM files from both satellites; store the flashes near a site. Returns flashes stored."""
    now = now or datetime.now(UTC)
    with connection() as conn:
        sites = conn.execute("SELECT id, latitude, longitude FROM sites").fetchall()
    rows = []
    with httpx.Client(timeout=30) as client:
        for bucket in SATELLITES:
            served = sites_for(bucket, sites)
            try:
                keys = [k for k in list_keys(client, bucket, now - LOOKBACK, now) if k not in _read]
            except httpx.HTTPError as exc:
                log.warning("GLM listing failed for %s: %s", bucket, exc)
                continue
            for key in keys:
                try:
                    resp = client.get(f"https://{bucket}.s3.amazonaws.com/{key}")
                    resp.raise_for_status()
                    found = flashes(resp.content)
                except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
                    log.warning("GLM file %s unreadable: %s", key, exc)
                    continue
                _read[key] = file_start(key) or now
                rows += [{"ts": t, "lat": la, "lon": lo}
                         for t, la, lo in near_sites(found, served, settings.lightning_radius_mi)]
    for key in [k for k, t in _read.items() if t < now - 2 * LOOKBACK]:  # forget old files
        del _read[key]
    if rows:
        with connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(INSERT_SQL, rows)
        log.info("glm: %d flashes within %g mi of a site", len(rows), settings.lightning_radius_mi)
    return len(rows)
