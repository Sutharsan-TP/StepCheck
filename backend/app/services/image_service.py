"""Safe handling of uploaded images for transcription.

Everything happens in memory: nothing is written to disk and image bytes are
never logged. The format is detected from the content (never the filename or
declared content type), decompression bombs are refused, orientation is applied
and metadata (EXIF, GPS, ...) is stripped by re-encoding.
"""

from __future__ import annotations

import base64
import io
import warnings
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.utils.errors import APIError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MIN_DIMENSION = 64
MAX_DIMENSION = 8000
MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION
OUTPUT_MAX_SIDE = 2000
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
_CHUNK = 64 * 1024

# Process-wide (set once, thread-safe): Pillow warns above this and refuses above 2x.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class PreparedImage:
    data_url: str
    width: int
    height: int
    source_format: str


async def read_upload(upload: UploadFile) -> bytes:
    """Read an upload in chunks, stopping as soon as it exceeds the size limit."""
    try:
        buffer = bytearray()
        while chunk := await upload.read(_CHUNK):
            buffer.extend(chunk)
            if len(buffer) > MAX_UPLOAD_BYTES:
                raise APIError(413, "IMAGE_TOO_LARGE", "Images must be 5 MB or smaller.")
        return bytes(buffer)
    finally:
        await upload.close()  # also removes any temporary spool file


def prepare_image(data: bytes) -> PreparedImage:
    if not data:
        raise APIError(400, "INVALID_IMAGE", "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise APIError(413, "IMAGE_TOO_LARGE", "Images must be 5 MB or smaller.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            try:
                image = Image.open(io.BytesIO(data), formats=list(ALLOWED_FORMATS))
            except UnidentifiedImageError:
                raise APIError(
                    415, "UNSUPPORTED_IMAGE_TYPE", "Only JPEG, PNG and WebP images are supported."
                ) from None
            source_format = image.format
            width, height = image.size
            if min(width, height) < MIN_DIMENSION or max(width, height) > MAX_DIMENSION:
                raise APIError(
                    400,
                    "IMAGE_DIMENSIONS_UNSUPPORTED",
                    f"Images must be between {MIN_DIMENSION} and {MAX_DIMENSION} pixels on each side.",
                )
            image.load()  # decode fully now so corrupt data fails here
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise APIError(413, "IMAGE_TOO_LARGE", "The image has too many pixels.") from None
        except APIError:
            raise
        except Exception:
            raise APIError(400, "INVALID_IMAGE", "The image could not be read.") from None

    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    image.thumbnail((OUTPUT_MAX_SIDE, OUTPUT_MAX_SIDE))

    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=90)  # no exif= argument: metadata dropped
    encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return PreparedImage(
        data_url=f"data:image/jpeg;base64,{encoded}",
        width=image.width,
        height=image.height,
        source_format=source_format,
    )
