"""worker/ingest/glm.py: GOES GLM file names, flash parsing and the site filter (no network, no database)."""

import io
from datetime import UTC, datetime, timedelta

import h5py
import numpy as np
import pytest

from planit.worker.ingest import glm as G

KEY = "GLM-L2-LCFA/2026/291/03/OR_GLM-L2-LCFA_G19_s20262910339000_e20262910339200_c20262910339219.nc"
START = datetime(2026, 10, 18, 3, 39, 0, tzinfo=UTC)
TURKEY_POINT = {"id": 621, "latitude": 25.435, "longitude": -80.331}
CASTAIC = {"id": 392, "latitude": 34.49, "longitude": -118.62}


def glm_file(lats, lons, offsets_s, quality) -> bytes:
    """A small file laid out like a real GLM-L2-LCFA one: unsigned int16 time offsets with scale and offset."""
    scale, add = 0.00038147560553625226, -5.0
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["time_coverage_start"] = b"2026-10-18T03:39:00.0Z"
        f["flash_lat"] = np.array(lats, dtype=np.float32)
        f["flash_lon"] = np.array(lons, dtype=np.float32)
        raw = np.round((np.array(offsets_s) - add) / scale).astype(np.int64)
        off = f.create_dataset("flash_time_offset_of_first_event", data=raw.astype(np.uint16).view(np.int16))
        off.attrs["scale_factor"], off.attrs["add_offset"], off.attrs["_Unsigned"] = [scale], [add], b"true"
        f["flash_quality_flag"] = np.array(quality, dtype=np.int16)
    return buf.getvalue()


def test_file_start_and_hour_prefixes():
    assert G.file_start(KEY) == START
    assert G.file_start("GLM-L2-LCFA/2026/291/03/") is None
    prefixes = G.hour_prefixes(datetime(2026, 10, 18, 3, 58, tzinfo=UTC), datetime(2026, 10, 18, 4, 1, tzinfo=UTC))
    assert prefixes == ["GLM-L2-LCFA/2026/291/03/", "GLM-L2-LCFA/2026/291/04/"]  # across the hour


def test_flashes_read_times_and_drop_bad_quality():
    data = glm_file([25.5, 30.0, 25.4], [-80.3, -90.0, -80.4], [1.5, 12.0, 19.9], [0, 0, 1])
    found = G.flashes(data)
    assert len(found) == 2  # the third is flagged bad
    (t1, lat1, lon1), (t2, _, _) = found
    assert t1 == pytest.approx(START + timedelta(seconds=1.5), abs=timedelta(milliseconds=5))
    assert t2 == pytest.approx(START + timedelta(seconds=12), abs=timedelta(milliseconds=5))  # past int16's top
    assert (round(lat1, 1), round(lon1, 1)) == (25.5, -80.3)
    assert G.flashes(glm_file([], [], [], [])) == []


def test_only_flashes_within_the_radius_of_a_site_count():
    t = START
    near = (t, 25.50, -80.30)  # ~5 mi from Turkey Point
    far = (t, 25.45, -78.37)  # off the Bahamas, ~120 mi
    assert G.near_sites([near, far], [TURKEY_POINT], 10) == [near]
    assert G.near_sites([far], [TURKEY_POINT], 150) == [far]
    assert G.near_sites([], [TURKEY_POINT], 10) == [] and G.near_sites([near], [], 10) == []


def test_each_site_is_watched_by_one_satellite():
    assert G.sites_for("noaa-goes19", [TURKEY_POINT, CASTAIC]) == [TURKEY_POINT]  # GOES-East
    assert G.sites_for("noaa-goes18", [TURKEY_POINT, CASTAIC]) == [CASTAIC]  # GOES-West
