import io
import pytest
from PIL import Image
from fastapi import HTTPException
from app.files import validate_image, is_dicom, dicom_to_png


def _png_bytes():
    buf = io.BytesIO()
    Image.new("L", (8, 8), 128).save(buf, format="PNG")
    return buf.getvalue()


def test_valid_jpeg_passes(sample_jpeg):
    validate_image(sample_jpeg)


def test_invalid_magic_bytes_raises():
    bad = b"\x00\x00\x00\x00garbage"
    with pytest.raises(HTTPException) as exc:
        validate_image(bad)
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "invalid_file"


def test_is_dicom_true_for_real_dicom(sample_dicom):
    assert is_dicom(sample_dicom) is True


def test_is_dicom_false_for_png_and_jpeg(sample_jpeg):
    assert is_dicom(_png_bytes()) is False
    assert is_dicom(sample_jpeg) is False
    assert is_dicom(b"too short") is False


def test_dicom_to_png_returns_valid_png(sample_dicom):
    out = dicom_to_png(sample_dicom)
    assert out[:8] == b"\x89PNG\r\n\x1a\n"          # PNG signature
    img = Image.open(io.BytesIO(out))               # decodes cleanly
    img.load()
    assert img.width > 0 and img.height > 0


def test_dicom_to_png_rejects_garbage_dicom():
    # 128-byte preamble + "DICM" magic but no parseable dataset.
    fake = b"\x00" * 128 + b"DICM" + b"\x00" * 64
    with pytest.raises(HTTPException) as exc:
        dicom_to_png(fake)
    assert exc.value.status_code == 422


def test_validate_image_message_mentions_dicom():
    with pytest.raises(HTTPException) as exc:
        validate_image(b"not an image at all")
    assert "DICOM" in exc.value.detail["message"]
