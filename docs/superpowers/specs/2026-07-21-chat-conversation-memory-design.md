# Chat conversation memory — design

Date: 2026-07-21
Branch: `vllm-fp8-inference`
Status: approved design, pre-implementation

## Problem

The keyless `/chat` medical assistant is stateless. Every message mints a fresh
`job_id` and calls the model with a single `user` message (system prompt + the
current question). There is no conversation history, so follow-ups like
"is that serious?" reach the model with no idea what "that" refers to.

Goal: give the `/chat` surface **conversation memory** — the assistant remembers
earlier turns in the same conversation so follow-ups have context.

## Scope

- **In scope:** the keyless `/chat` proxy surface only.
- **Out of scope:** the authed `/v1/<domain>/analyze` + `/query` API stays
  stateless single-shot (its B2B callers manage their own context). No change to
  its observable behavior.
- **Out of scope:** long-term / cross-session user memory, `agent-bridge/`.

## Approach

Server-side history in Redis, keyed by a client-held `conversation_id`.

Rejected alternative: client resends the transcript on each request. Rejected
because it loses history on reload and makes the model's context client-trusted.

Memory read/write lives in the **worker**, the one place that sees both the
incoming question and the produced answer in a single call.

## The load-bearing constraint: token budget

vLLM runs `--max-model-len 2048` and `max_output_tokens = 512`, leaving ~1536
input tokens. Worst case with an image (~256 tok) + system prompt (~120 tok) +
the current question leaves comfortable room for a **~700-token (~2800-char)
history budget**. History is walked newest-first and truncated at this budget, so
memory can never push a request past the context window. Stored turns are trimmed
at write time so Redis cannot grow unbounded.

## Components

### `worker/memory.py` (new — isolated Redis-memory module)

The only code that knows the memory layout. Redis key: `chat:conv:<conversation_id>`,
a LIST of JSON-encoded entries `{"role": "user"|"assistant", "text": "..."}`.

- `load_history(r, conversation_id, char_budget) -> list[dict]`
  - `LRANGE` the list, walk newest-first accumulating until adding the next entry
    would exceed `char_budget`, return the kept slice in chronological order.
  - Returns `[]` for an unknown/empty conversation.
- `append_turn(r, conversation_id, user_text, assistant_text)`
  - Renders the user turn (see image handling), trims user text to
    `<= 400` chars and assistant text to `<= 700` chars.
  - `RPUSH` the two entries, `LTRIM` to the last `chat_memory_max_turns`
    entries, `EXPIRE` to `chat_memory_ttl_seconds` (refresh on every turn).
    Done in a single pipeline.
- image handling: a helper renders an image turn's user text as
  `"[shared a medical image] <question>"`. **Image bytes are never stored or
  re-sent** — only this text placeholder enters memory. This keeps follow-up
  text turns contextual without paying image tokens again.

### `worker/prompts.py`

`build_messages(domain, image_url, question, history=None)`:
- When `history` is falsy → unchanged single-turn behavior (system + question).
- When `history` is present → emit each prior entry as a plain text message
  (`{"role": entry["role"], "content": [{"type": "text", "text": entry["text"]}]}`)
  **before** the current turn. The current turn keeps its exact
  `{system}\n\n{question}` shape, so the structured parsers are untouched.

### `worker/inference.py`

`run_inference(domain, image_bytes, question, history=None)` threads `history`
into `build_messages`. Stays pure — no Redis access here.

### `worker/worker.py`

`process_job(job_id, domain, temp_path, question, key_hash, conversation_id=None)`:
- `conversation_id is None` → today's behavior exactly (no memory).
- Set → `history = load_history(...)` before inference; on **success only**,
  `append_turn(...)`. A failed job remembers nothing.
- Uses the worker's existing Redis connection (`_get_redis()`).
- Logging: add `conversation_id` and `history_turns` to the existing allowlisted
  events. **Never** log turn text (may be PHI).

### `app/routes/_query.py` and `app/routes/_analyze.py`

`submit_query(..., conversation_id=None)` / `submit_analysis(..., conversation_id=None)`,
enqueued as a trailing arg to `process_job`. `/v1` callers pass nothing → `None`
→ identical behavior to today.

### `app/routes/chat.py`

- `chat_query`: read `conversation_id` from the JSON body.
- `chat_analyze`: read `conversation_id` from a form field.
- Validate it is a UUID; invalid or absent → treat as stateless (pass `None`),
  never error. Pass the validated id through to `submit_*`.

### `app/static/chat.html`

- On load, read `conversation_id` from `sessionStorage`; if absent, generate a
  UUID (`crypto.randomUUID()`) and persist it.
- Send `conversation_id` on every request (JSON field for query, `FormData`
  field for analyze).
- Add a **"New chat"** control that rotates the id (new UUID → `sessionStorage`)
  and clears the log back to the empty state.

### `config.py`

New settings:
- `chat_memory_char_budget: int = 2800`
- `chat_memory_max_turns: int = 12`
- `chat_memory_ttl_seconds: int = 1800`

## Data flow

```
browser (conversation_id in sessionStorage)
  -> POST /chat/api/query {question, conversation_id}
  -> chat_query validates id -> submit_query(..., conversation_id)
  -> enqueue process_job(..., conversation_id)
  -> worker: history = load_history(redis, id)            # bounded to char budget
            result = run_inference(domain, img, q, history)
            if ok: append_turn(redis, id, q, result.raw)  # trimmed, TTL refreshed
  -> result {raw, structured} stored in RQ job result (unchanged)
  -> browser polls GET /chat/api/jobs/{id}, renders raw (unchanged)
```

Turns are strictly serialized per browser: the UI disables **Send** until the
answer returns, and the worker writes history *before* the result becomes
pollable. So the next turn always reads a consistent, up-to-date history — no
locking required.

## Error handling / safety

- Malformed/missing `conversation_id` → stateless fallback (consistent with the
  "never fail the job for a parse error" convention).
- Logging stays allowlisted: `conversation_id` + `history_turns` count only,
  never turn text.
- Memory sits in Redis exactly like job results already do, under a 30-min TTL
  that refreshes on each turn.

## Testing (per CLAUDE.md — same-commit)

- `tests/test_memory.py` (new) — `worker/memory.py` with `fakeredis`:
  load/trim/char-budget/TTL, `LTRIM` cap, image-turn text rendering.
- `tests/test_prompts.py` — `build_messages` history injection: prior turns
  precede the current turn; `history=None` is byte-identical to today.
- `tests/test_inference.py` / worker path — `process_job` with fakeredis +
  mocked `worker.inference._client.post`: turn 2's payload contains turn 1's
  context; a failed job writes no history; `conversation_id=None` writes nothing.
- `tests/test_routes_chat.py` — `conversation_id` passthrough for query + analyze,
  UUID validation (bad id → stateless, no error), `/v1` routes unaffected.
- Docs updated same commit: `docs/api.md` (chat proxy request fields),
  `README.md` (chat section), `CLAUDE.md` (chat surface section).

## Known limitations (accepted for this demo)

- A page reload keeps server-side memory but shows a blank transcript; "New chat"
  is the clean reset. No history-replay endpoint (YAGNI).
- Guessing another user's random UUID would leak that thread's context —
  acceptable for a capability-URL research demo, same trust model as the tunnel.
```
