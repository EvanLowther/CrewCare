"""Owner: Person B. Crew hazard reports (photo + map pin)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from PIL import UnidentifiedImageError

from planit.api import mock, reports_store
from planit.api.access import photo_signature_ok
from planit.api.deps import use_mock
from planit.auth import OptionalUser, SignedInUser
from planit.models import HazardReport, HazardType, ReportList, ReportSeverity
from planit.storage.photos import load_photo

router = APIRouter(prefix="/api", tags=["reports"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.get("/reports", response_model=ReportList)
def list_reports(user: OptionalUser, site_id: int | None = None, include_past: bool = False) -> ReportList:
    """Active reports on sites the viewer may see. With `site_id` and `include_past=true`, that site's resolved and
    expired reports too (the My sites page)."""
    if include_past and site_id is None:
        raise HTTPException(422, "include_past needs a site_id")
    if use_mock():
        return ReportList(reports=mock.reports(site_id))
    return ReportList(reports=reports_store.list_reports(site_id, user, include_past))


@router.post("/reports", response_model=HazardReport, status_code=201)
async def create_report(
    user: SignedInUser,
    site_id: Annotated[int, Form()],
    latitude: Annotated[float, Form(description="The pin")],
    longitude: Annotated[float, Form(description="The pin")],
    hazard_type: Annotated[HazardType, Form()],
    severity: Annotated[ReportSeverity, Form()],
    gps_latitude: Annotated[float | None, Form(description="The phone's GPS fix")] = None,
    gps_longitude: Annotated[float | None, Form(description="The phone's GPS fix")] = None,
    gps_accuracy_m: Annotated[float | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> HazardReport:
    """multipart/form-data. Members of `site_id` only, with the phone's GPS fix and the pin within 5 miles of it
    (admins anywhere). The photo is resized and its metadata dropped; the reporter's name comes from their login."""
    coords = [(latitude, longitude)] + ([(gps_latitude, gps_longitude)] if gps_latitude is not None else [])
    if any(lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in coords):
        raise HTTPException(422, "Latitude/longitude out of range")
    gps = (gps_latitude, gps_longitude) if gps_latitude is not None and gps_longitude is not None else None
    data = await photo.read() if photo is not None and photo.filename else None
    if data is not None and len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo too large (15 MB max)")
    try:
        return reports_store.create_report(
            user=user, site_id=site_id, latitude=latitude, longitude=longitude, gps=gps,
            gps_accuracy_m=gps_accuracy_m, hazard_type=hazard_type, severity=severity,
            description=(description or "").strip() or None, photo=data or None,
        )
    except UnidentifiedImageError as exc:
        raise HTTPException(422, "That file isn't an image we can read") from exc


@router.patch("/reports/{report_id}/resolve", response_model=HazardReport)
def resolve_report(report_id: UUID, user: SignedInUser) -> HazardReport:
    """Mark a report resolved so it leaves the map. The site's managers and admins only."""
    return reports_store.resolve_report(report_id, user)


@router.get("/photos/{photo_id}")
def get_photo(photo_id: UUID, user: OptionalUser, exp: int | None = Query(None), sig: str | None = Query(None)
              ) -> Response:
    """Use `photo_url` from a report: it carries a signature, because <img> tags can't send the sign-in token."""
    signed = exp is not None and sig is not None and photo_signature_ok(photo_id, exp, sig)
    if not signed and not reports_store.photo_visible(photo_id, user):
        raise HTTPException(404, "Photo not found")
    found = load_photo(photo_id)
    if found is None:
        raise HTTPException(404, "Photo not found")
    data, content_type = found
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})
