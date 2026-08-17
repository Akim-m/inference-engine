import io
import filetype
from fastapi import HTTPException

_ALLOWED = {"image/jpeg", "image/png"}


def is_dicom(content: bytes) -> bool:
    """True if `content` is a DICOM file (the ``DICM`` magic sits at byte 128,
    right after the 128-byte preamble)."""
    return len(content) > 132 and content[128:132] == b"DICM"


def validate_image(content: bytes) -> None:
    kind = filetype.guess(content)
    if kind is None or kind.mime not in _ALLOWED:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_file", "message": "File must be JPEG, PNG, or DICOM"},
        )


def dicom_to_png(content: bytes) -> bytes:
    """Render a DICOM file to 8-bit PNG bytes that MedGemma can consume.

    Raw DICOM pixels are 12–16-bit and unviewable as-is, so we apply the VOI/windowing
    LUT, invert MONOCHROME1 (so bone reads white), collapse RGB/multi-frame studies, and
    normalize to 8-bit. The vLLM worker is unchanged — it only ever receives a PNG.
    """
    try:
        import numpy as np
        import pydicom
        from PIL import Image
        try:
            from pydicom.pixels import apply_voi_lut          # pydicom >= 3
        except ImportError:                                    # pragma: no cover
            from pydicom.pixel_data_handlers.util import apply_voi_lut
    except ImportError:
        raise HTTPException(
            status_code=422,
            detail={"error": "dicom_unsupported",
                    "message": "DICOM support is not available on this server"},
        )

    try:
        ds = pydicom.dcmread(io.BytesIO(content))
        arr = ds.pixel_array
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_file", "message": "Could not read DICOM pixel data"},
        )

    # Any pixel-shape/codec quirk past this point (multi-frame colour, YBR, odd VRs)
    # must degrade to a clean 422 — never an unhandled 500.
    try:
        # Collapse multi-frame studies to the middle frame first: (F,H,W,C) → (H,W,C)
        # for colour, (F,H,W) → (H,W) for grayscale.
        if arr.ndim == 4:
            arr = arr[arr.shape[0] // 2]
        elif arr.ndim == 3 and arr.shape[-1] not in (3, 4):
            arr = arr[arr.shape[0] // 2]

        photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
        if arr.ndim == 3 and arr.shape[-1] in (3, 4):        # colour
            if photometric.startswith("YBR"):                # convert YBR → RGB for true colour
                try:
                    from pydicom.pixels import convert_color_space
                    arr = convert_color_space(arr, photometric, "RGB")
                except Exception:
                    pass
            arr, mode = arr[..., :3].astype("float32"), "RGB"
        else:                                                # grayscale
            try:
                arr = apply_voi_lut(arr, ds)                 # windowing to display range
            except Exception:
                pass
            arr = arr.astype("float32")
            if photometric == "MONOCHROME1":
                arr = arr.max() - arr                        # invert inverted-grayscale studies
            mode = "L"

        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) * 255.0 if hi > lo else arr * 0.0
        img = Image.fromarray(arr.astype(np.uint8), mode=mode)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_file", "message": "Could not render DICOM pixel data"},
        )
