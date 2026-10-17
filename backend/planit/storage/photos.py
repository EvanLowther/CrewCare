"""Photo storage. Photos live in the `photos` table in Tiger.

Everything goes through save_photo / load_photo, so moving to S3 later only
changes this file.
"""

from __future__ import annotations

import io
from uuid import UUID

from PIL import Image, ImageOps

from planit.db import connection

MAX_SIDE_PX = 1600
JPEG_QUALITY = 80


def resize_to_jpeg(raw: bytes) -> tuple[bytes, int, int]:
    """Fix phone rotation, shrink to MAX_SIDE_PX, re-encode as JPEG (strips location metadata)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), img.width, img.height


def save_photo(raw: bytes) -> UUID:
    data, width, height = resize_to_jpeg(raw)
    with connection() as conn:
        row = conn.execute(
            "INSERT INTO photos (content_type, data, width, height, size_bytes) "
            "VALUES ('image/jpeg', %s, %s, %s, %s) RETURNING id",
            (data, width, height, len(data)),
        ).fetchone()
    return row["id"]


def load_photo(photo_id: UUID) -> tuple[bytes, str] | None:
    with connection() as conn:
        row = conn.execute("SELECT data, content_type FROM photos WHERE id = %s", (photo_id,)).fetchone()
    return (bytes(row["data"]), row["content_type"]) if row else None
