"""Key-less chat surface.

Serves a static chat page at ``/chat`` and proxies its requests through
``/chat/api/*`` so the browser never handles an API key. The server attaches a
shared identity (``settings.chat_api_key``) and reuses the same submit/poll
internals as the authed ``/v1`` routes. The department is picked per message via
``/chat/api/domains`` (defaulting to the ``general`` catch-all).
Disabled (503) unless ``CHAT_API_KEY`` is set.
"""
import json
import time
import uuid
from pathlib import Path
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from app.auth import hash_key, enforce_submit_limits, enforce_read_limit
from app.deps import get_redis
from app.domains import DOMAINS
from app.routes._analyze import submit_analysis
from app.routes._query import submit_query
from app.routes.jobs import fetch_job_status
from app.schemas import JobResponse, JobSubmitted, TextQueryRequest
from config import settings

router = APIRouter()

_CHAT_HTML = (Path(__file__).resolve().parent.parent / "static" / "chat.html").read_text()
_CHAT_DOMAIN = "general"


def _valid_domain(value: Optional[str]) -> str:
    # Unknown/missing department → general (the catch-all), never an error.
    return value if value in DOMAINS else _CHAT_DOMAIN


def _chat_key_hash() -> str:
    if not settings.chat_api_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "chat_disabled", "message": "Chat is not enabled on this server"},
        )
    return hash_key(settings.chat_api_key)


def _valid_conversation_id(value: Optional[str]) -> Optional[str]:
    # A malformed/absent id degrades to stateless (None) rather than erroring —
    # mirrors the "never fail the job for a parse error" convention.
    if not value:
        return None
    try:
        uuid.UUID(value)
    except ValueError:
        return None
    return value


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_page() -> HTMLResponse:
    return HTMLResponse(_CHAT_HTML)


@router.get("/chat/api/domains", include_in_schema=False)
async def chat_domains() -> dict:
    # Public metadata (no key gate): the dropdown populates from the live domain list.
    return {"domains": DOMAINS}


@router.get("/chat/api/status", include_in_schema=False)
async def chat_status() -> dict:
    """Report whether the model backend is ready, so the page can show a warmup
    bar and gate the composer until MedGemma can actually answer."""
    health_url = settings.vllm_url.rsplit("/v1", 1)[0] + "/health"
    ready, detail = False, "unreachable"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(health_url)
        ready = resp.status_code == 200
        detail = "ready" if ready else f"http_{resp.status_code}"
    except Exception:
        detail = "starting"
    return {"model_ready": ready, "detail": detail}


@router.get("/chat/api/stream/{job_id}", include_in_schema=False)
async def chat_stream(job_id: str, r=Depends(get_redis)) -> StreamingResponse:
    """Server-Sent-Events relay of a job's live token stream. The worker RPUSHes
    token deltas into ``chat:stream:{job_id}``; here we drain that list and forward
    each as an SSE ``data:`` frame until a ``done``/``error`` marker or timeout."""
    _chat_key_hash()  # 503 if chat is disabled, matching the other proxy routes
    key = f"chat:stream:{job_id}"

    def event_source():
        # Sync generator → FastAPI runs it in a threadpool, so the blocking BLPOP
        # never stalls the event loop. Deadline mirrors the worker's inference cap.
        # Preamble: a large SSE comment (ignored by EventSource) that pushes past a
        # proxy's threshold buffer up front so token frames start flushing. This works
        # for threshold-buffering proxies (nginx et al). NOTE: Cloudflare *quick* tunnels
        # (trycloudflare) fully buffer the whole response regardless, so streaming only
        # appears live on a direct/non-buffering path — over such a tunnel the browser
        # gets the answer at the end and shows a live elapsed-time counter meanwhile.
        yield ": " + ("padding " * 2048) + "\n\n"
        deadline = time.monotonic() + settings.request_timeout_s + 30
        while time.monotonic() < deadline:
            item = r.blpop(key, timeout=2)
            if item is None:
                yield ": keep-alive\n\n"   # comment frame prevents proxy idle-timeout
                continue
            payload = item[1]
            yield f"data: {payload}\n\n"
            try:
                if json.loads(payload).get("t") in ("done", "error"):
                    return
            except (ValueError, TypeError):
                continue

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/api/analyze", response_model=JobSubmitted, status_code=202, include_in_schema=False)
async def chat_analyze(
    image: UploadFile = File(...),
    question: str = Form(default="", max_length=500),
    conversation_id: Optional[str] = Form(default=None),
    domain: Optional[str] = Form(default=None),
    r=Depends(get_redis),
) -> JobSubmitted:
    key_hash = _chat_key_hash()
    await enforce_submit_limits(r, key_hash)
    return await submit_analysis(
        _valid_domain(domain), image, question, key_hash, r,
        conversation_id=_valid_conversation_id(conversation_id),
    )


@router.post("/chat/api/query", response_model=JobSubmitted, status_code=202, include_in_schema=False)
async def chat_query(body: TextQueryRequest, r=Depends(get_redis)) -> JobSubmitted:
    key_hash = _chat_key_hash()
    await enforce_submit_limits(r, key_hash)
    return await submit_query(
        _valid_domain(body.domain), body.question, key_hash, r,
        conversation_id=_valid_conversation_id(body.conversation_id),
    )


@router.get("/chat/api/jobs/{job_id}", response_model=JobResponse, include_in_schema=False)
async def chat_job(job_id: str, r=Depends(get_redis)) -> JobResponse:
    key_hash = _chat_key_hash()
    await enforce_read_limit(r, key_hash)
    return fetch_job_status(job_id, key_hash, r)
