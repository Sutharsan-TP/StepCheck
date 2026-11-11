import asyncio
import base64
import io
import os

import pytest
from fastapi import UploadFile
from PIL import Image

from app.services.image_service import MAX_UPLOAD_BYTES, prepare_image, read_upload
from app.utils.errors import APIError


def image_bytes(fmt="PNG", size=(400, 200), mode="RGB", **save):
    buf = io.BytesIO()
    Image.new(mode, size, "white").save(buf, format=fmt, **save)
    return buf.getvalue()


def decode(prepared):
    raw = base64.b64decode(prepared.data_url.split(",", 1)[1])
    return Image.open(io.BytesIO(raw))


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_supported_formats(fmt):
    p = prepare_image(image_bytes(fmt))
    assert p.source_format == fmt
    assert p.data_url.startswith("data:image/jpeg;base64,")
    assert (p.width, p.height) == (400, 200)


def test_transparency_is_flattened():
    p = prepare_image(image_bytes("PNG", mode="RGBA"))
    assert decode(p).mode == "RGB"


def test_large_images_are_downscaled():
    p = prepare_image(image_bytes("JPEG", size=(4000, 3000)))
    assert max(p.width, p.height) == 2000


def test_exif_metadata_is_stripped_and_orientation_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees
    exif[0x010F] = "SecretCameraMaker"
    p = prepare_image(image_bytes("JPEG", size=(400, 200), exif=exif.tobytes()))
    out = decode(p)
    assert (out.width, out.height) == (200, 400)  # rotated upright
    assert not out.getexif()


def test_oversized_file_is_413():
    with pytest.raises(APIError) as info:
        prepare_image(b"\x89PNG" + b"0" * MAX_UPLOAD_BYTES)
    assert info.value.status_code == 413 and info.value.code == "IMAGE_TOO_LARGE"


@pytest.mark.parametrize(
    "data",
    [
        image_bytes("GIF"),
        image_bytes("BMP"),
        b"just some text pretending to be a .png",
        b"%PDF-1.4 not an image",
    ],
)
def test_unsupported_formats_are_415(data):
    with pytest.raises(APIError) as info:
        prepare_image(data)
    assert info.value.status_code == 415 and info.value.code == "UNSUPPORTED_IMAGE_TYPE"


def test_corrupt_image_is_400():
    data = image_bytes("PNG")
    with pytest.raises(APIError) as info:
        prepare_image(data[:60])
    assert info.value.status_code in (400, 415)


def test_empty_file_is_400():
    with pytest.raises(APIError) as info:
        prepare_image(b"")
    assert info.value.code == "INVALID_IMAGE"


@pytest.mark.parametrize("size", [(20, 400), (8100, 100)])
def test_dimension_limits(size):
    with pytest.raises(APIError) as info:
        prepare_image(image_bytes("PNG", size=size, mode="1"))
    assert info.value.code == "IMAGE_DIMENSIONS_UNSUPPORTED"


def test_decompression_bomb_is_refused():
    # 9000 x 9000 1-bit PNG compresses to a tiny file but would decode to 81M pixels.
    bomb = image_bytes("PNG", size=(9000, 9000), mode="1")
    assert len(bomb) < MAX_UPLOAD_BYTES
    with pytest.raises(APIError) as info:
        prepare_image(bomb)
    assert info.value.status_code in (400, 413)


def test_read_upload_stops_at_limit_and_closes():
    big = UploadFile(io.BytesIO(b"0" * (MAX_UPLOAD_BYTES + 10)), filename="big.png")
    with pytest.raises(APIError) as info:
        asyncio.run(read_upload(big))
    assert info.value.status_code == 413
    assert big.file.closed


def test_nothing_written_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    upload = UploadFile(io.BytesIO(image_bytes("PNG")), filename="ok.png")
    data = asyncio.run(read_upload(upload))
    prepare_image(data)
    assert os.listdir(tmp_path) == []
