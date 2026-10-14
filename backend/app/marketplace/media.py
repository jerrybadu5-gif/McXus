"""Listing photos: validate, strip metadata (phone photos carry GPS), resize for PNG data costs, store.

Storage is a local folder for now (a Docker volume). An S3/SeaweedFS adapter with the same two methods
replaces it before launch.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.errors import AppError

Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True)
class ProcessedPhoto:
    full: bytes
    thumb: bytes
    width: int
    height: int


def process(data: bytes) -> ProcessedPhoto:
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"Photos must be under {settings.max_upload_mb} MB", code="photo_too_large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise AppError("Upload a JPEG, PNG or WebP photo", code="photo_format")
        with Image.open(io.BytesIO(data)) as source:
            img = ImageOps.exif_transpose(source).convert("RGB")  # apply rotation, then drop all metadata
            full = _encode(img, settings.photo_max_px, quality=75)
            thumb = _encode(img, settings.thumb_max_px, quality=70)
            width, height = _fit(img.size, settings.photo_max_px)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise AppError("That file is not a photo we can read", code="photo_invalid") from exc
    return ProcessedPhoto(full=full, thumb=thumb, width=width, height=height)


def _fit(size: tuple[int, int], max_px: int) -> tuple[int, int]:
    w, h = size
    scale = min(1.0, max_px / max(w, h))
    return max(1, round(w * scale)), max(1, round(h * scale))


def _encode(img: Image.Image, max_px: int, quality: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_px, max_px))
    out = io.BytesIO()
    copy.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)  # no exif= → metadata gone
    return out.getvalue()


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def save(self, key: str, data: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


def storage() -> LocalStorage:
    return LocalStorage(get_settings().media_dir)


def url(key: str) -> str:
    return f"{get_settings().media_url}/{key}"
