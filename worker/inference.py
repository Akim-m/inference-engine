import base64
import json
import re
import time
import httpx
import structlog
from typing import Callable, Optional
from config import settings
from worker.prompts import build_messages

log = structlog.get_logger()

_client = httpx.Client(timeout=settings.request_timeout_s)

_RADIOLOGY_RE = re.compile(
    r"FINDINGS:\s*(.+?)\s*\n"
    r"IMPRESSION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_DERMATOLOGY_RE = re.compile(
    r"CONDITION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"RECOMMENDATION:\s*(.+?)\s*\n"
    r"CONFIDENCE:\s*(\d+\.\d+)",
    re.IGNORECASE,
)


def parse_radiology(raw: str) -> Optional[dict]:
    m = _RADIOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "findings": m.group(1).strip(),
        "impression": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_dermatology(raw: str) -> Optional[dict]:
    m = _DERMATOLOGY_RE.search(raw)
    if not m:
        return None
    try:
        confidence = float(m.group(4))
        confidence = max(0.0, min(1.0, confidence))
    except ValueError:
        confidence = None
    return {
        "condition": m.group(1).strip(),
        "severity": m.group(2).lower(),
        "recommendation": m.group(3).strip(),
        "confidence": confidence,
    }


_PATHOLOGY_RE = re.compile(
    r"DIAGNOSIS:\s*(.+?)\s*\n"
    r"TISSUE_TYPE:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_OPHTHALMOLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_STRUCTURE:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_DENTISTRY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_AREA:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_GENERAL_RE = re.compile(
    r"FINDINGS:\s*(.+?)\s*\n"
    r"IMPRESSION:\s*(.+?)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_ORTHOPEDICS_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_BONE:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_PULMONOLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_REGION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_NEUROLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_REGION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_GASTROENTEROLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"LOCATION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_CARDIOLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_STRUCTURE:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_HEMATOLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"CELL_LINE:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_RHEUMATOLOGY_RE = re.compile(
    r"FINDING:\s*(.+?)\s*\n"
    r"AFFECTED_JOINT:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(\S+)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)

_QUERY_RE = re.compile(
    r"ANSWER:\s*(.+?)\s*\n"
    r"CONFIDENCE:\s*(\S+)",
    re.IGNORECASE,
)


def parse_pathology(raw: str) -> Optional[dict]:
    m = _PATHOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "diagnosis": m.group(1).strip(),
        "tissue_type": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_ophthalmology(raw: str) -> Optional[dict]:
    m = _OPHTHALMOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_structure": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_dentistry(raw: str) -> Optional[dict]:
    m = _DENTISTRY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_area": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_general(raw: str) -> Optional[dict]:
    m = _GENERAL_RE.search(raw)
    if not m:
        return None
    return {
        "findings": m.group(1).strip(),
        "impression": m.group(2).strip(),
        "confidence": m.group(3).lower(),
    }


def parse_orthopedics(raw: str) -> Optional[dict]:
    m = _ORTHOPEDICS_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_bone": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_pulmonology(raw: str) -> Optional[dict]:
    m = _PULMONOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_region": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_neurology(raw: str) -> Optional[dict]:
    m = _NEUROLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_region": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_gastroenterology(raw: str) -> Optional[dict]:
    m = _GASTROENTEROLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "location": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_cardiology(raw: str) -> Optional[dict]:
    m = _CARDIOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_structure": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_hematology(raw: str) -> Optional[dict]:
    m = _HEMATOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "cell_line": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_rheumatology(raw: str) -> Optional[dict]:
    m = _RHEUMATOLOGY_RE.search(raw)
    if not m:
        return None
    return {
        "finding": m.group(1).strip(),
        "affected_joint": m.group(2).strip(),
        "severity": m.group(3).lower(),
        "confidence": m.group(4).lower(),
    }


def parse_query(raw: str) -> Optional[dict]:
    m = _QUERY_RE.search(raw)
    if not m:
        return None
    return {
        "answer": m.group(1).strip(),
        "confidence": m.group(2).lower(),
    }


_ANALYZE_PARSERS = {
    "radiology": parse_radiology,
    "dermatology": parse_dermatology,
    "pathology": parse_pathology,
    "ophthalmology": parse_ophthalmology,
    "dentistry": parse_dentistry,
    "general": parse_general,
    "orthopedics": parse_orthopedics,
    "pulmonology": parse_pulmonology,
    "neurology": parse_neurology,
    "gastroenterology": parse_gastroenterology,
    "cardiology": parse_cardiology,
    "hematology": parse_hematology,
    "rheumatology": parse_rheumatology,
}


def _bytes_to_data_url(image_bytes: bytes) -> str:
    # Forward the original encoded image — no decode/re-encode. validate_image()
    # already restricted uploads to JPEG/PNG, and vLLM's image processor handles the
    # colour-space conversion, so we only sniff the magic bytes for the MIME type.
    mime = "image/jpeg" if image_bytes[:3] == b"\xff\xd8\xff" else "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _post_streaming(payload: dict, publish: Callable[[str], None]) -> tuple[str, Optional[int]]:
    """Stream a chat completion from vLLM, forwarding each token delta through
    `publish`. Returns the full text and the completion-token count (from the
    trailing usage chunk emitted by `stream_options.include_usage`)."""
    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    parts: list[str] = []
    completion_tokens: Optional[int] = None
    with _client.stream("POST", f"{settings.vllm_url}/chat/completions", json=payload) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            obj = json.loads(data)
            for choice in obj.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content")
                if delta:
                    parts.append(delta)
                    publish(delta)
            usage = obj.get("usage")
            if usage and usage.get("completion_tokens") is not None:
                completion_tokens = usage["completion_tokens"]
    return "".join(parts), completion_tokens


def run_inference(
    domain: str,
    image_bytes: Optional[bytes],
    question: str,
    history: Optional[list[dict]] = None,
    publish: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run one inference. When `publish` is given, stream from vLLM and forward each
    token delta through it (the worker relays these to the browser via Redis); the
    non-streaming path is kept for callers that only want the final result."""
    image_url = _bytes_to_data_url(image_bytes) if image_bytes is not None else None
    messages = build_messages(domain, image_url, question, history=history)
    payload = {
        "model": settings.vllm_model or settings.model_id,
        "messages": messages,
        "temperature": 0,
        "max_tokens": settings.max_output_tokens,
    }
    t0 = time.monotonic()
    if publish is not None:
        raw, completion_tokens = _post_streaming(payload, publish)
    else:
        resp = _client.post(f"{settings.vllm_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        completion_tokens = (data.get("usage") or {}).get("completion_tokens")
    inference_ms = int((time.monotonic() - t0) * 1000)
    tps = (
        round(completion_tokens / (inference_ms / 1000), 1)
        if completion_tokens and inference_ms
        else None
    )
    parser = parse_query if image_bytes is None else _ANALYZE_PARSERS.get(domain)
    return {
        "raw": raw,
        "structured": parser(raw) if parser else None,
        "stats": {
            "completion_tokens": completion_tokens,
            "inference_ms": inference_ms,
            "tokens_per_second": tps,
        },
    }
