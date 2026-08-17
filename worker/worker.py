import json
import time
import structlog
from pathlib import Path
from config import make_redis, settings
from worker.inference import run_inference
from worker.memory import load_history, append_turn, render_user_turn

log = structlog.get_logger()

# Live token stream: the worker RPUSHes deltas here and the /chat SSE endpoint drains
# them. A LIST (not pub/sub) so a browser that connects slightly late still gets every
# token. Short TTL — it's a transient relay; the durable answer lives in the RQ result.
_STREAM_KEY = "chat:stream:{job_id}"
_STREAM_TTL = 300


def _stream_channel(job_id: str):
    """Return (publish_delta, finish) callbacks that relay tokens for `job_id`."""
    r = _get_redis()
    key = _STREAM_KEY.format(job_id=job_id)

    def publish(delta: str) -> None:
        r.rpush(key, json.dumps({"t": "delta", "text": delta}))
        r.expire(key, _STREAM_TTL)

    def finish(kind: str, stats=None) -> None:
        r.rpush(key, json.dumps({"t": kind, "stats": stats}))
        r.expire(key, _STREAM_TTL)

    return publish, finish


_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        _redis = make_redis()
    return _redis


def process_job(
    job_id: str,
    domain: str,
    temp_path: str,
    question: str,
    key_hash: str,
    conversation_id: str | None = None,
) -> dict:
    start = time.monotonic()
    log.info("job_started", job_id=job_id, domain=domain, conversation_id=conversation_id)
    path = Path(temp_path) if temp_path else None
    publish, finish = _stream_channel(job_id)
    try:
        image_bytes = path.read_bytes() if path else None
        history = (
            load_history(_get_redis(), conversation_id, settings.chat_memory_char_budget)
            if conversation_id
            else None
        )
        result = run_inference(domain, image_bytes, question, history=history, publish=publish)
        # Remember this turn only on success — a failed turn pollutes nothing. The
        # write happens before we return, so the next turn (enqueued only after the
        # client sees this result) always reads an up-to-date, consistent history.
        if conversation_id:
            append_turn(
                _get_redis(),
                conversation_id,
                render_user_turn(question, had_image=image_bytes is not None),
                result["raw"],
            )
        finish("done", stats=result.get("stats"))
        log.info(
            "job_completed",
            job_id=job_id,
            duration_ms=int((time.monotonic() - start) * 1000),
            conversation_id=conversation_id,
            history_turns=len(history) if history else 0,
        )
        return result
    except Exception as exc:
        finish("error")
        log.error("job_failed", job_id=job_id, error_type=type(exc).__name__)
        raise
    finally:
        _get_redis().srem(f"pending:{key_hash}", job_id)
        if path is not None and path.exists():
            path.unlink()
