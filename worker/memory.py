"""Bounded per-conversation chat memory, stored in Redis.

The ONLY code that knows the memory layout. History for a conversation lives in a
Redis LIST at ``chat:conv:<conversation_id>`` — each element is a JSON object
``{"role": "user"|"assistant", "text": "..."}``. Turns are trimmed on write (so
Redis cannot grow unbounded) and again on read against a character budget (so a
long conversation can never push a request past vLLM's context window).

Nothing here is safe to log — turn text may be PHI — so this module never logs.
"""
import json
from typing import Optional

from config import settings

# Per-entry write caps. Module constants (not settings): the spec exposes only the
# three ``chat_memory_*`` knobs, and these bound Redis growth, not model context.
_USER_TRIM = 400
_ASSISTANT_TRIM = 700


def _key(conversation_id: str) -> str:
    return f"chat:conv:{conversation_id}"


def render_user_turn(question: str, had_image: bool) -> str:
    """Text stored for a user turn. Image turns store only a placeholder — the
    image bytes are never persisted or re-sent."""
    if had_image:
        return f"[shared a medical image] {question}"
    return question


def load_history(r, conversation_id: str, char_budget: int) -> list[dict]:
    """Return prior turns oldest→newest, trimmed to ``char_budget`` total chars by
    dropping the oldest entries first. ``[]`` for an unknown/empty conversation."""
    raw = r.lrange(_key(conversation_id), 0, -1)
    if not raw:
        return []
    entries = [json.loads(item) for item in raw]
    kept: list[dict] = []
    used = 0
    for entry in reversed(entries):  # newest first
        cost = len(entry["text"])
        if used + cost > char_budget:
            break
        kept.append(entry)
        used += cost
    kept.reverse()  # back to chronological order
    return kept


def append_turn(r, conversation_id: str, user_text: str, assistant_text: str) -> None:
    """Append a completed exchange, trimming each side and capping/refreshing the
    list in a single pipeline."""
    key = _key(conversation_id)
    user_entry = json.dumps({"role": "user", "text": user_text[:_USER_TRIM]})
    assistant_entry = json.dumps({"role": "assistant", "text": assistant_text[:_ASSISTANT_TRIM]})
    pipe = r.pipeline()
    pipe.rpush(key, user_entry, assistant_entry)
    pipe.ltrim(key, -settings.chat_memory_max_turns, -1)
    pipe.expire(key, settings.chat_memory_ttl_seconds)
    pipe.execute()
