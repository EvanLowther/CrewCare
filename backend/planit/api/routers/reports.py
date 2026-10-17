"""Owner: Person B. Crew hazard reports (photo + map pin)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from planit.api import mock
from planit.api.deps import not_built, use_mock
from planit.models import HazardReport, HazardType, ReportList, ReportSeverity
from planit.storage.photos import load_photo

router = APIRouter(prefix="/api", tags=["reports"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.get("/reports", response_model=ReportList)
def list_reports(site_id: int | None = None) -> ReportList:
    if use_mock():
        return ReportList(reports=mock.reports(site_id))
    raise not_built("GET /api/reports")


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
    """multipart/form-data. The API picks the nearest site and resizes the photo."""
    if photo is not None and photo.size and photo.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo too large (15 MB max)")
    # TODO (hours 12-15): save_photo(), find nearest site with ST_Distance, insert hazard_reports
    raise not_built("POST /api/reports")


@router.get("/photos/{photo_id}")
def get_photo(photo_id: UUID) -> Response:
    found = load_photo(photo_id)
    if found is None:
        raise HTTPException(404, "Photo not found")
    data, content_type = found
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
