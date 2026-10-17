"""Owner: Person B. Crew hazard reports (photo + map pin)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from PIL import UnidentifiedImageError

from planit.api import mock, reports_store
from planit.api.deps import use_mock
from planit.models import HazardReport, HazardType, ReportList, ReportSeverity
from planit.storage.photos import load_photo

router = APIRouter(prefix="/api", tags=["reports"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.get("/reports", response_model=ReportList)
def list_reports(site_id: int | None = None) -> ReportList:
    if use_mock():
        return ReportList(reports=mock.reports(site_id))
    return ReportList(reports=reports_store.list_reports(site_id))


@router.post("/reports", response_model=HazardReport, status_code=201)
async def create_report(
    latitude: Annotated[float, Form()],
    longitude: Annotated[float, Form()],
    hazard_type: Annotated[HazardType, Form()],
    severity: Annotated[ReportSeverity, Form()],
    description: Annotated[str | None, Form()] = None,
    reporter_name: Annotated[str | None, Form()] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> HazardReport:
    """multipart/form-data. The API ties it to the nearest site and resizes the photo (dropping its metadata)."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(422, "Latitude/longitude out of range")
    data = await photo.read() if photo is not None and photo.filename else None
    if data is not None and len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo too large (15 MB max)")
    try:
        return reports_store.create_report(
            latitude=latitude, longitude=longitude, hazard_type=hazard_type, severity=severity,
            description=(description or "").strip() or None, reporter_name=(reporter_name or "").strip() or None,
            photo=data or None,
        )
    except UnidentifiedImageError as exc:
        raise HTTPException(422, "That file isn't an image we can read") from exc


@router.get("/photos/{photo_id}")
def get_photo(photo_id: UUID) -> Response:
    found = load_photo(photo_id)
    if found is None:
        raise HTTPException(404, "Photo not found")
    data, content_type = found
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
