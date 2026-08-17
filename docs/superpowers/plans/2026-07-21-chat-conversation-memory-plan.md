# Chat conversation memory — implementation plan

Date: 2026-07-21
Branch: `vllm-fp8-inference`
Spec: `docs/superpowers/specs/2026-07-21-chat-conversation-memory-design.md` (approved — the source of truth for every decision below)

## Overview

Add server-side conversation memory to the keyless `/chat` surface. The browser holds a
`conversation_id` (UUID in `sessionStorage`); the worker stores/loads a bounded
per-conversation history in Redis (`chat:conv:<id>`, LIST of `{"role","text"}` JSON
entries) and threads it into the vLLM call as prior chat messages. The authed `/v1`
API stays observably stateless: `conversation_id` defaults to `None` at every layer and
only the `/chat` proxy ever passes it.

**Method: strict TDD.** For every task: write the failing test → run it and watch it
fail (for the right reason) → implement the minimal change → run it green → run the
touched test files → commit. Never write implementation before the failing test exists.

**Environment:** activate the venv (`.venv`), run tests with `pytest tests/ -v`
(single file: `pytest tests/test_memory.py -v`). Commit per task on the current branch.

## Order of work

1. Config knobs (`chat_memory_*` settings)
2. `worker/memory.py` — the isolated Redis-memory module (new)
3. `worker/prompts.py` — `build_messages(..., history=None)`
4. `worker/inference.py` — `run_inference(..., history=None)`
5. `worker/worker.py` — `process_job(..., conversation_id=None)` load/append + logging
6. Submit helpers + schema — `submit_query` / `submit_analysis` / `TextQueryRequest` carry `conversation_id`
7. `/chat` proxy — read + UUID-validate `conversation_id`, pass through
8. `app/static/chat.html` — sessionStorage id + "New chat" button
9. Docs — `docs/api.md`, `README.md`, `CLAUDE.md`, `.env.example`
10. Full-suite verification + manual smoke test

## Interfaces locked by the spec (do not re-litigate)

- Redis key: `chat:conv:<conversation_id>` — LIST of JSON entries `{"role": "user"|"assistant", "text": "..."}`.
- `worker/memory.py`:
  - `load_history(r, conversation_id: str, char_budget: int) -> list[dict]` — LRANGE all, walk newest-first accumulating `len(entry["text"])`, stop before exceeding `char_budget`, return kept slice in chronological order. `[]` for unknown/empty conversation.
  - `append_turn(r, conversation_id: str, user_text: str, assistant_text: str) -> None` — trim user to ≤400 chars / assistant to ≤700 chars (module constants, not config), then in ONE pipeline: `RPUSH` two entries, `LTRIM` to last `settings.chat_memory_max_turns` **entries**, `EXPIRE settings.chat_memory_ttl_seconds` (refreshes every turn).
  - `render_user_turn(question: str, had_image: bool) -> str` — returns `f"[shared a medical image] {question}"` when `had_image`, else `question`. Image bytes are NEVER stored.
- `build_messages(domain, image_url, question, history=None)` — history entries emitted as `{"role": entry["role"], "content": [{"type": "text", "text": entry["text"]}]}` BEFORE the current turn; current turn keeps its exact `{system}\n\n{question}` shape (parsers untouched).
- `run_inference(domain, image_bytes, question, history=None)` — pure, no Redis.
- `process_job(job_id, domain, temp_path, question, key_hash, conversation_id=None)` — `None` ⇒ byte-identical to today; set ⇒ load before inference, append on success only. Uses existing `_get_redis()`.
- `submit_query(..., conversation_id=None)` / `submit_analysis(..., conversation_id=None)` — enqueued as trailing positional arg to `process_job` (always passed; `/v1` passes nothing so it's `None`).
- Config: `chat_memory_char_budget: int = 2800`, `chat_memory_max_turns: int = 12`, `chat_memory_ttl_seconds: int = 1800`.
- Proxy validation: `conversation_id` must parse as `uuid.UUID`; invalid/absent → pass `None` (stateless), never an error.
- Logging: add `conversation_id` and `history_turns` (a count) to existing allowlisted events. NEVER log turn text — it may be PHI.

---

## Task 1 — Config: three `chat_memory_*` settings

**Files:** `config.py`, `tests/test_config.py`, `.env.example`

**Failing test first** — append to `tests/test_config.py` (matches the existing
`test_vllm_client_settings_defaults` style, `Settings(_env_file=None)`):

```python
def test_chat_memory_defaults():
    s = Settings(_env_file=None)
    assert s.chat_memory_char_budget == 2800
    assert s.chat_memory_max_turns == 12
    assert s.chat_memory_ttl_seconds == 1800
```

Run `pytest tests/test_config.py -v` → the new test fails with `AttributeError`.

**Implement:** in `config.py`, add the three fields to `Settings` directly below
`read_rate_limit_per_minute: int = 600` (line 24), with a short comment that they bound
the `/chat` conversation memory. Add commented entries to `.env.example`
(`# CHAT_MEMORY_CHAR_BUDGET=2800` etc.) next to `CHAT_API_KEY`.

**Verify:** `pytest tests/test_config.py -v` → all pass. Commit.

---

## Task 2 — `worker/memory.py`: bounded Redis history module (new)

**Files:** `worker/memory.py` (new), `tests/test_memory.py` (new)

**Failing tests first** — create `tests/test_memory.py` using the `fake_redis` fixture
from `tests/conftest.py` (`fakeredis.FakeRedis(decode_responses=True)`), and
`monkeypatch.setattr(settings, ...)` (the pattern `tests/test_routes_chat.py` uses for
`chat_api_key`) when a test needs a small `max_turns`/budget:

```python
from config import settings
from worker.memory import load_history, append_turn, render_user_turn

CID = "11111111-1111-4111-8111-111111111111"
```

- `test_load_history_unknown_conversation_returns_empty` — `load_history(fake_redis, CID, 2800) == []`.
- `test_append_then_load_round_trip` — `append_turn(fake_redis, CID, "q1", "a1")` then
  `load_history(...)` returns exactly
  `[{"role": "user", "text": "q1"}, {"role": "assistant", "text": "a1"}]` (chronological).
- `test_append_trims_user_and_assistant_text` — append `"u" * 401` / `"a" * 800`; loaded
  entries have `len(text) == 400` and `len(text) == 700`.
- `test_char_budget_keeps_newest_first` — append 3 turns whose texts are each 100 chars;
  `load_history(fake_redis, CID, char_budget=250)` returns only the **newest 2 entries**,
  still in chronological order (walk newest-first, stop before exceeding budget).
- `test_ltrim_caps_total_entries` — `monkeypatch.setattr(settings, "chat_memory_max_turns", 4)`;
  append 4 turns (8 entries); `fake_redis.llen(f"chat:conv:{CID}") == 4` and
  `load_history` returns the newest 4 entries.
- `test_ttl_set_and_refreshed_on_append` — after `append_turn`,
  `fake_redis.ttl(f"chat:conv:{CID}") == settings.chat_memory_ttl_seconds`; append again
  and the TTL is back at the full value.
- `test_render_user_turn_with_image` — `render_user_turn("what is this?", had_image=True)
  == "[shared a medical image] what is this?"`.
- `test_render_user_turn_without_image` — returns the question unchanged.

Run `pytest tests/test_memory.py -v` → all fail with `ModuleNotFoundError`.

**Implement:** create `worker/memory.py` — the ONLY code that knows the memory layout:
module constants `_USER_TRIM = 400`, `_ASSISTANT_TRIM = 700`; `_key(conversation_id)`
returning `f"chat:conv:{conversation_id}"`; the three functions per the Interfaces
section. `append_turn` uses `r.pipeline()` for RPUSH×2 + `LTRIM(key,
-settings.chat_memory_max_turns, -1)` + `EXPIRE`. `load_history` does
`LRANGE(key, 0, -1)`, `json.loads` each, walks `reversed(entries)` accumulating
`len(entry["text"])`, then returns the kept tail in original order. No logging in this
module (nothing here is safe to log).

**Verify:** `pytest tests/test_memory.py -v` → all pass. Commit.

---

## Task 3 — `worker/prompts.py`: `build_messages` accepts history

**Files:** `worker/prompts.py`, `tests/test_prompts.py`

**Failing tests first** — append to `tests/test_prompts.py` (reuse its `_text` /
`_image_parts` helpers where possible):

```python
_HISTORY = [
    {"role": "user", "text": "What is this rash?"},
    {"role": "assistant", "text": "It looks like eczema."},
]

def test_history_absent_is_single_message():
    assert len(build_messages("general", None, "q")) == 1
    assert len(build_messages("general", None, "q", history=None)) == 1
    assert len(build_messages("general", None, "q", history=[])) == 1

def test_history_prepended_before_current_turn():
    msgs = build_messages("general", None, "Is it serious?", history=_HISTORY)
    assert len(msgs) == 3
    assert msgs[0] == {"role": "user", "content": [{"type": "text", "text": "What is this rash?"}]}
    assert msgs[1] == {"role": "assistant", "content": [{"type": "text", "text": "It looks like eczema."}]}

def test_current_turn_shape_unchanged_with_history():
    # Final message still carries system prompt + question — parsers depend on this.
    msgs = build_messages("general", None, "Is it serious?", history=_HISTORY)
    final_text = msgs[-1]["content"][-1]["text"]
    assert "ANSWER:" in final_text and "Is it serious?" in final_text
    assert msgs[-1]["role"] == "user"

def test_history_with_image_current_turn():
    # Image only on the current turn; history entries are text-only.
    msgs = build_messages("general", _IMG, "And this one?", history=_HISTORY)
    assert len(msgs) == 3
    assert all(p["type"] == "text" for m in msgs[:-1] for p in m["content"])
    assert any(p["type"] == "image_url" for p in msgs[-1]["content"])
```

Run `pytest tests/test_prompts.py -v` → the four new tests fail with `TypeError`
(unexpected keyword `history`).

**Implement:** change the signature at `worker/prompts.py:164` to
`build_messages(domain: str, image_url: Optional[str], question: str, history: Optional[list[dict]] = None) -> list[dict]`.
Build `messages = []`; when `history` is truthy, append one
`{"role": entry["role"], "content": [{"type": "text", "text": entry["text"]}]}` per
entry; then append the existing current-turn message (unchanged construction) and return.
With no history, the return value is byte-identical to today — all existing
`msgs[0]`-indexing tests must pass untouched.

**Verify:** `pytest tests/test_prompts.py -v` → all pass (old + new). Commit.

---

## Task 4 — `worker/inference.py`: `run_inference` threads history

**Files:** `worker/inference.py`, `tests/test_inference.py`

**Failing tests first** — append to `tests/test_inference.py` (reuse its
`_fake_response` helper and the mandated mock point `worker.inference._client.post`):

```python
def test_run_inference_threads_history_into_payload():
    history = [{"role": "user", "text": "What is a fracture?"},
               {"role": "assistant", "text": "A break in bone."}]
    with patch("worker.inference._client.post",
               return_value=_fake_response("ANSWER: yes\nCONFIDENCE: high\n")) as mock_post:
        run_inference("general", None, "Is it serious?", history=history)
    messages = mock_post.call_args.kwargs["json"]["messages"]
    assert len(messages) == 3
    assert messages[0]["content"][0]["text"] == "What is a fracture?"
    assert messages[1]["role"] == "assistant"

def test_run_inference_history_default_is_single_message():
    with patch("worker.inference._client.post",
               return_value=_fake_response("ANSWER: x\nCONFIDENCE: low\n")) as mock_post:
        run_inference("general", None, "q")
    assert len(mock_post.call_args.kwargs["json"]["messages"]) == 1
```

Run `pytest tests/test_inference.py -v` → first new test fails with `TypeError`.

**Implement:** at `worker/inference.py:257`, change the signature to
`run_inference(domain: str, image_bytes: Optional[bytes], question: str, history: Optional[list[dict]] = None) -> dict`
and pass it through: `messages = build_messages(domain, image_url, question, history=history)`
(line 259). Nothing else changes — this function stays pure (no Redis).

**Verify:** `pytest tests/test_inference.py -v` → all pass. Commit.

---

## Task 5 — `worker/worker.py`: `process_job` loads/appends memory

**Files:** `worker/worker.py`, `tests/test_worker.py` (new)

**Failing tests first** — create `tests/test_worker.py`. `process_job` gets Redis from
the module global via `_get_redis()`, so point the global at fakeredis with
`monkeypatch.setattr("worker.worker._redis", fake_redis)` (monkeypatch restores it; this
also makes the existing `finally`-block `srem` hit fakeredis). Mock vLLM at
`worker.inference._client.post` with the same `_fake_response` shape as
`tests/test_inference.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from worker.worker import process_job

CID = "22222222-2222-4222-8222-222222222222"

def _fake_response(content: str):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp
```

- `test_process_job_without_conversation_id_writes_no_memory` — call
  `process_job("j1", "general", "", "hello", "kh")` (no `conversation_id`); assert
  `fake_redis.keys("chat:conv:*") == []`. **This is the `/v1`-stays-stateless guard.**
- `test_second_turn_payload_contains_first_turn_context` — run two `process_job` calls
  with `conversation_id=CID` ("What is eczema?" then "Is it serious?"); on the second
  call's `mock_post.call_args.kwargs["json"]["messages"]`, flatten all text parts and
  assert `"What is eczema?"` appears and the message count is 3 (2 history + current).
- `test_failed_job_writes_no_history` — `mock_post` raises (`resp.raise_for_status.side_effect = httpx.HTTPStatusError(...)`
  as in `test_run_inference_raises_on_http_error`); `pytest.raises` around
  `process_job(..., conversation_id=CID)`; assert `fake_redis.exists(f"chat:conv:{CID}") == 0`.
- `test_image_turn_stores_placeholder_not_bytes` — write `b"\xff\xd8\xff" + b"x" * 32`
  to `tmp_path / "j.img"`; run `process_job("j4", "general", str(tmp_path / "j.img"), "what is this?", "kh", conversation_id=CID)`
  with an analyze-format fake response; assert the first stored entry's `text` ==
  `"[shared a medical image] what is this?"` and `"base64"` appears nowhere in
  `fake_redis.lrange(f"chat:conv:{CID}", 0, -1)`. (Also confirms the temp file was
  deleted — existing behavior.)
- `test_success_with_conversation_id_appends_trimmed_turn` — single call with `CID`;
  `load_history` returns 2 entries: `role=user` first, `role=assistant` second with the
  fake raw text.

Run `pytest tests/test_worker.py -v` → all fail (`TypeError: unexpected keyword
argument 'conversation_id'` / empty-memory asserts pass trivially only for the first).

**Implement:** in `worker/worker.py`:
- `from config import settings` and `from worker.memory import load_history, append_turn, render_user_turn`.
- Signature: `process_job(job_id: str, domain: str, temp_path: str, question: str, key_hash: str, conversation_id: str | None = None) -> dict`.
- Inside `try`, after `image_bytes`:
  `history = load_history(_get_redis(), conversation_id, settings.chat_memory_char_budget) if conversation_id else None`.
- Call `run_inference(domain, image_bytes, question, history=history)`.
- On success only (right before the `job_completed` log/return):
  `if conversation_id: append_turn(_get_redis(), conversation_id, render_user_turn(question, had_image=image_bytes is not None), result["raw"])`.
  This runs before `return`, so history is written before RQ stores the result —
  preserving the spec's "history is consistent before the result becomes pollable"
  serialization guarantee.
- Logging (allowlisted fields only, never text): add `conversation_id=conversation_id`
  to the existing `job_started` event (line 27); add `conversation_id=conversation_id,
  history_turns=len(history) if history else 0` to `job_completed` (line 32). Leave
  `job_failed` unchanged.

**Verify:** `pytest tests/test_worker.py tests/test_inference.py -v` → all pass. Commit.

---

## Task 6 — Submit helpers + schema carry `conversation_id`

**Files:** `app/routes/_query.py`, `app/routes/_analyze.py`, `app/schemas.py`,
`tests/test_routes_general.py`

**Failing tests first** — append to `tests/test_routes_general.py` (its `client`
fixture + `valid_key` + the mandated mock points `app.routes._query.Queue` /
`app.routes._analyze.Queue`). Enqueue positional args are
`("worker.worker.process_job", job_id, domain, temp_path, question, key_hash, conversation_id)`,
so the trailing conversation slot is `args[6]`:

```python
def test_v1_query_enqueues_stateless(client, valid_key):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        client.post("/v1/general/query", json={"question": "hi"},
                    headers={"X-API-Key": valid_key})
    assert mock_q.return_value.enqueue.call_args.args[6] is None

def test_v1_analyze_enqueues_stateless(client, valid_key, sample_jpeg):
    # same shape with app.routes._analyze.Queue and a files= upload
    ...
    assert mock_q.return_value.enqueue.call_args.args[6] is None
```

Run `pytest tests/test_routes_general.py -v` → both fail with `IndexError` (only 6
positional args today).

**Implement:**
- `app/schemas.py` — add `conversation_id: Optional[str] = None` to `TextQueryRequest`
  (line 42). No length/format constraint here; the proxy validates, `/v1` ignores it.
- `app/routes/_query.py` — `submit_query(domain, question, key_hash, r, conversation_id=None)`;
  enqueue args become `job_id, domain, "", question, key_hash, conversation_id` (line 14).
- `app/routes/_analyze.py` — `submit_analysis(domain, image, question, key_hash, r, conversation_id=None)`;
  enqueue args become `job_id, domain, str(temp_path), question, key_hash, conversation_id` (line 38).
- Do NOT touch `app/routes/_domain.py` — the `/v1` routes keep calling
  `submit_query(domain, body.question, key_hash, r)` / `submit_analysis(domain, image, question, key_hash, r)`
  with no id, so `/v1` always enqueues `None`.

**Verify:** `pytest tests/test_routes_general.py tests/test_routes_chat.py -v` → all
pass (chat tests still pass because the extra `None` arg doesn't affect them). Commit.

---

## Task 7 — `/chat` proxy: read + validate `conversation_id`

**Files:** `app/routes/chat.py`, `tests/test_routes_chat.py`

**Failing tests first** — append to `tests/test_routes_chat.py` (its `client` +
`chat_enabled` fixtures; same `Queue` mock points; `args[6]` as in Task 6):

```python
CID = "33333333-3333-4333-8333-333333333333"

def test_chat_query_passes_conversation_id(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        client.post("/chat/api/query", json={"question": "hi", "conversation_id": CID})
    assert mock_q.return_value.enqueue.call_args.args[6] == CID

def test_chat_analyze_passes_conversation_id(client, chat_enabled, sample_jpeg):
    # multipart: files={"image": ...}, data={"question": "x", "conversation_id": CID}
    ...
    assert mock_q.return_value.enqueue.call_args.args[6] == CID

def test_chat_query_invalid_conversation_id_falls_back_stateless(client, chat_enabled):
    # "not-a-uuid" → 202 (never an error) and args[6] is None
    ...

def test_chat_query_missing_conversation_id_is_stateless(client, chat_enabled):
    # {"question": "hi"} → 202, args[6] is None
    ...
```

Run `pytest tests/test_routes_chat.py -v` → the two passthrough tests fail
(`args[6] is None`, not the CID); the fallback tests pass trivially — keep them as
regression guards.

**Implement:** in `app/routes/chat.py`:
- Add module helper:
  ```python
  def _valid_conversation_id(value: str | None) -> str | None:
      if not value:
          return None
      try:
          uuid.UUID(value)
      except ValueError:
          return None
      return value
  ```
  (import `uuid`; invalid/absent → stateless `None`, never an HTTP error — mirrors the
  "never fail the job for a parse error" convention).
- `chat_query` (line 52): pass
  `conversation_id=_valid_conversation_id(body.conversation_id)` to `submit_query`.
- `chat_analyze` (line 41): add parameter
  `conversation_id: Optional[str] = Form(default=None)` and pass
  `conversation_id=_valid_conversation_id(conversation_id)` to `submit_analysis`.

**Verify:** `pytest tests/test_routes_chat.py -v` → all pass. Commit.

---

## Task 8 — `app/static/chat.html`: sessionStorage id + "New chat"

**Files:** `app/static/chat.html`, `tests/test_routes_chat.py`

**Failing test first** (the page is static — the serving test asserts the new controls
shipped, matching the existing `test_chat_page_served` style):

```python
def test_chat_page_has_conversation_memory_controls(client):
    resp = client.get("/chat")
    assert "crypto.randomUUID" in resp.text
    assert "New chat" in resp.text
    assert "conversation_id" in resp.text
```

Run → fails (none of those strings exist in `chat.html`).

**Implement** in `app/static/chat.html`:
- **Id management** (top of the `<script>`):
  ```js
  const CONV_KEY = "troke_conversation_id";
  function conversationId() {
    let id = sessionStorage.getItem(CONV_KEY);
    if (!id) { id = crypto.randomUUID(); sessionStorage.setItem(CONV_KEY, id); }
    return id;
  }
  ```
- **Send it on every request** in `submitJob` (line 174): the analyze branch adds
  `fd.append("conversation_id", conversationId());`; the query branch body becomes
  `JSON.stringify({ question: text, conversation_id: conversationId() })`.
- **"New chat" button**: add `<button type="button" id="newchat">New chat</button>` to
  the `<header>` (style like the `.attach` chip, pushed right with `margin-left: auto`).
  Handler: `sessionStorage.setItem(CONV_KEY, crypto.randomUUID())`, then reset the log
  to the empty state by restoring the original `#empty` div markup inside `#log`, and
  `q.focus()`.
- **Fix the stale `empty` reference**: `addBubble` currently captures `const empty = ...`
  once (line 109) and calls `empty.remove()` (line 156). After "New chat" re-creates the
  div, that const points at a detached node — change `addBubble` to look it up live:
  `const e = document.getElementById("empty"); if (e) e.remove();` (and drop the
  module-level `empty` const).
- Do NOT change the send-disable-until-answer flow — turn serialization (spec) depends
  on `sendBtn.disabled = true` until `pollResult` resolves.

**Verify:** `pytest tests/test_routes_chat.py -v` → all pass. Commit.

---

## Task 9 — Docs (same-change convention from CLAUDE.md)

**Files:** `docs/api.md`, `README.md`, `CLAUDE.md`

- **`docs/api.md`** — in the chat page/proxy section (~lines 422–439): document the
  optional `conversation_id` field on `POST /chat/api/query` (JSON) and
  `POST /chat/api/analyze` (form field); state that a valid UUID enables bounded
  server-side memory (last turns, ~2800-char budget, 30-min sliding TTL), that an
  invalid/absent id is silently stateless, and that image bytes are never stored (a
  `[shared a medical image]` placeholder enters memory). Add one line to the `/v1`
  section stating `/v1` endpoints remain stateless single-shot.
- **`README.md`** — "Share via chat" section (~line 59): one short paragraph — the chat
  remembers the conversation (server-side, 30-min TTL) and the "New chat" button starts
  fresh; mention the three `CHAT_MEMORY_*` env knobs.
- **`CLAUDE.md`** — "Chat surface" section: append a paragraph covering
  `worker/memory.py` (key layout `chat:conv:<id>`, LIST of `{"role","text"}` JSON,
  char-budget load / trim-on-write / LTRIM / TTL), that `conversation_id` flows
  `chat.py → submit_* → process_job` and defaults to `None` everywhere (`/v1`
  stateless), the three `chat_memory_*` settings in `config.py`, and the logging rule
  (`conversation_id` + `history_turns` only, never turn text).

**Verify:** re-read each diff for accuracy against the implemented behavior. Commit
(docs-only commit closing out the feature).

---

## Task 10 — Full-suite verification + manual smoke

1. `pytest tests/ -v` → **every** test passes (the suite includes the untouched `/v1`
   domain-route files — they are the regression net for "byte-identical `/v1`").
2. `git status` — confirm only the files named in this plan changed.
3. **Manual smoke** (optional but recommended; needs Redis + vLLM + a worker per
   CLAUDE.md commands, `CHAT_API_KEY` set):
   - Open `http://localhost:8000/chat`; ask "what is eczema?" → answer arrives.
   - Ask "is it serious?" → the answer clearly refers to eczema (memory works).
   - `redis-cli LRANGE chat:conv:<id> 0 -1` → JSON `{"role","text"}` entries, no image
     data; `TTL` ≈ 1800.
   - Click "New chat", ask "is it serious?" → the model has no context (fresh thread).
   - `curl` a `/v1/general/query` with a key → response shape unchanged.

---

## Ambiguities for the implementer

1. **`TextQueryRequest` is shared with `/v1`** — adding optional `conversation_id`
   makes the field appear in `/v1`'s OpenAPI schema (responses and behavior stay
   identical; `/v1` never forwards it). The task brief explicitly mandates the field on
   `TextQueryRequest`, so this schema-doc side effect is accepted. If a reviewer
   objects, the fallback is a chat-only subclass — but that is NOT what this plan does.
2. **`chat_memory_max_turns` counts LIST entries, not exchanges** — the spec says
   "LTRIM to the last `chat_memory_max_turns` entries", so 12 = 6 user/assistant
   exchanges. Implement exactly that.
3. **Trim caps (400/700) are module constants** in `worker/memory.py`, not settings —
   the spec names only three config knobs.
4. **`append_turn` takes pre-rendered `user_text`** — the caller (`process_job`)
   composes `render_user_turn(question, had_image=...)` first. The spec's wording was
   ambiguous ("renders the user turn"); this split matches the three-function interface
   the design mandates.
5. **CLAUDE.md says conda venv; the task brief says `.venv`** — use whichever
   interpreter actually resolves `pytest` in this checkout; the commands above assume
   the venv is active.
