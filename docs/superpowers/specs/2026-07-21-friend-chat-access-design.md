# Friend-Facing Chat Access — Design

**Date:** 2026-07-21
**Status:** Proposed (awaiting review)
**Branch target:** `vllm-fp8-inference` (current)

## Context

The troke API is an async job queue: a client submits an image or question, gets a
`job_id`, and polls `GET /v1/jobs/{id}` until the result is ready. It's also split into
five specialist medical domains (`radiology`, `dermatology`, `pathology`,
`ophthalmology`, `dentistry`), each of which is really the *same* MedGemma-4B model
behind a different prompt (`worker/prompts.py`) and parser (`worker/inference.py`).

The goal is to let a non-technical friend abroad use the running instance. He "sees this
like a chatbot" — so three things about the current surface get in his way:

1. **The async job mechanics** (job IDs, polling, statuses) are the wrong mental model
   for someone who just wants to type a message and get an answer.
2. **The five domains** force a choice he isn't equipped to make (is a mole
   "dermatology"? is a tooth X-ray "dentistry" or "radiology"?).
3. **The API key** — pasting a 64-hex-char `X-API-Key` is friction he shouldn't face.

We want a single unified chat experience that hides all three, plus a way to expose the
locally-running server to him over the internet.

### What already exists (and doesn't)

- `frontend/` is a real Next.js 16 app but it is a **marketing site + API-key
  provisioning dashboard** (Supabase auth → mint an `X-API-Key`). It has **no chat UI**
  and never calls `/analyze` or the poll endpoint. Nothing there to reuse for chat.
- `agent-bridge/` is an unrelated LAN agent-coordination toolkit. Out of scope.
- There is **no synchronous "submit and wait" endpoint** — submit-then-poll is the only
  pattern.
- Auth internals are already reusable: `submit_analysis`/`submit_query` take a `key_hash`
  argument directly; `app/auth.py` factors `_enforce_rate` and the pending-quota
  reconcile; `jobs.py`'s read logic just needs extracting into a function.

## Goals

- A single chat page a friend can open in a browser and use with **zero setup** — no job
  IDs, no polling, no domain choice, **no key to paste**.
- Handle **both** text questions and image uploads from the same box.
- Route everything through **one catch-all domain** so no domain picker is needed.
- Keep **all key material server-side** — the friend's browser never sends or stores a key.
- Expose the local server to the internet via **Cloudflare Tunnel**.
- Follow the repo's existing patterns and the CLAUDE.md "After Every Change" rule (tests
  + `docs/api.md` + `README.md` in the same change).

## Non-Goals

- **No multi-turn memory.** Each submission is independent; the model keeps no
  conversation state. The UI shows a running transcript, but turn N cannot reference
  turn N-1. This is a property of the API, not something we change here.
- **No new synchronous backend endpoint.** A blocking "submit and wait" route would hold
  an HTTP connection open through the tunnel for the whole GPU inference — exactly what
  the async queue exists to avoid. The poll loop lives in browser JS instead. (The
  `job_id` is still returned to the browser by the proxy, but the UI never shows it — it
  isn't a credential, just a per-request handle scoped to the shared identity.)
- **No changes to the existing five domains** or their prompts/parsers.
- **No per-person authentication of the chat.** Once the key step is removed, the tunnel
  URL is the capability — see Security.

## Architecture

Three independent pieces, backend → browser. The browser talks only to **key-less
`/chat/api/*` proxy routes**; the server attaches the shared identity and reuses the
existing `/v1` internals.

```
Friend's browser ──HTTPS──> Cloudflare Tunnel ──> localhost:8000 (FastAPI)
   chat.html (JS)                                   ├─ GET  /chat                 (serves the page)
   - NO key                                         ├─ POST /chat/api/analyze|query  (proxy, no key)
   - submit + poll loop                             ├─ GET  /chat/api/jobs/{id}      (proxy, no key)
   - hides job_id                                   │     └─ attach shared key_hash, reuse:
                                                     │        submit_analysis / submit_query
                                                     │        fetch_job_status
                                                     └─ /v1/* (unchanged, header-authed)
                                                          │
                                            Redis queue → worker → vLLM (GPU) → MedGemma
```

Same origin for page + proxy (both on `:8000`, both behind the one tunnel URL) → **no
CORS middleware needed**.

### Part A — `general` catch-all domain (backend)

The domain factory (`app/routes/_domain.py`) already generates the identical
`analyze`+`query` routes for any domain string, so adding a domain is a three-touch
change (per the note at `app/main.py:47-49`):

1. **`app/main.py:50`** — append `"general"` to `DOMAINS`. This auto-registers
   `POST /v1/general/analyze` and `POST /v1/general/query` (the proxy targets the
   `general` domain internally; these public routes come along for free and are harmless).
2. **`worker/prompts.py`** — add a `general` entry to **both** `_ANALYZE` and `_QUERY`.
   Required, not optional: `build_messages` does a hard `_ANALYZE[domain]` /
   `_QUERY[domain]` lookup (`worker/prompts.py:86`) that would `KeyError` otherwise.
   - `_ANALYZE["general"]`: a domain-agnostic image prompt asking for
     `FINDINGS / IMPRESSION / CONFIDENCE` (no `SEVERITY` — the catch-all stays loose),
     explicitly noting the image may be any modality (radiograph, skin photo, histology,
     fundus, dental, etc.).
   - `_QUERY["general"]`: the standard `ANSWER / CONFIDENCE` format, so the existing
     `parse_query` handles it with no change.
3. **`worker/inference.py`** — add `parse_general(raw)` (regex for
   `FINDINGS / IMPRESSION / CONFIDENCE`) and register it in `_ANALYZE_PARSERS`. If it ever
   fails to match, `_ANALYZE_PARSERS.get("general")` still degrades gracefully:
   `structured` is `null` and `raw` flows through unchanged (`worker/inference.py:166`).

**Result shape for `general`** (`/analyze`): `{findings, impression, confidence}`.
`/query` reuses the shared `{answer, confidence}`.

### Part B — key-less chat, served + proxied by FastAPI

The friend's browser never handles a key. It loads a static page and calls three
unauthenticated, same-origin proxy routes; the server supplies the shared identity.

**Config (`config.py`, `.env.example`):**
- Add `chat_api_key: str = ""` to `Settings`. When empty, the chat proxy is **disabled**
  (returns `503 chat_disabled`) — chat is strictly opt-in. When set, the server uses
  `hash_key(chat_api_key)` as the shared identity for all proxied jobs.
- `.env.example` gains `CHAT_API_KEY=` with a comment. To rotate/disable, change it and
  restart. (Not required to be a member of the Redis `api_keys` set — the proxy bypasses
  header auth and uses the hash purely as the quota/ownership identity.)

**Reusable refactors (no behavior change to existing routes):**
- `app/auth.py` — factor the pending reconcile+check out of `check_job_quota` into
  `_check_pending_quota(r, key_hash)`; `check_job_quota` calls it (unchanged behavior).
  Add two header-free helpers the proxy uses:
  `enforce_submit_limits(r, key_hash)` (= `_enforce_rate(... "rate" ...)` +
  `_check_pending_quota`) and `enforce_read_limit(r, key_hash)`
  (= `_enforce_rate(... "read_rate" ...)`).
- `app/routes/jobs.py` — extract the body of `get_job` into
  `fetch_job_status(job_id, key_hash, r) -> JobResponse`; the existing `/v1/jobs/{id}`
  route becomes a thin wrapper calling it. The proxy calls the same function.

**New `app/routes/chat.py`:**
- `_CHAT_HTML = (… / "static" / "chat.html").read_text()` at import.
- `_chat_key_hash()` → `hash_key(settings.chat_api_key)`; raises
  `503 {"error": "chat_disabled", ...}` if `chat_api_key` is unset.
- `GET /chat` → `HTMLResponse(_CHAT_HTML)` (`include_in_schema=False`).
- `POST /chat/api/analyze` (`image: UploadFile`, `question: str = Form("")`,
  `r=Depends(get_redis)`):
  `kh = _chat_key_hash(); await enforce_submit_limits(r, kh);
  return await submit_analysis("general", image, question, kh, r)`.
- `POST /chat/api/query` (`body: TextQueryRequest`, `r=Depends(get_redis)`):
  `kh = _chat_key_hash(); await enforce_submit_limits(r, kh);
  return await submit_query("general", body.question, kh, r)`.
- `GET /chat/api/jobs/{job_id}` (`r=Depends(get_redis)`):
  `kh = _chat_key_hash(); await enforce_read_limit(r, kh);
  return fetch_job_status(job_id, kh, r)`.
- Mounted in `app/main.py` **without** the `/v1` prefix: `app.include_router(chat.router)`.

Because submit and poll use the *same* `kh`, `fetch_job_status`'s ownership check passes.
Server-side image validation (10MB + JPEG/PNG) is inherited from `submit_analysis`.

**`app/static/chat.html`** — one self-contained vanilla-JS file (no build, no framework,
no external CDN):
- **No key anywhere.** API base is `window.location.origin`, so it works identically on
  localhost and through the tunnel.
- **Send:** one text box + image attach + send.
  - Image attached → `POST {origin}/chat/api/analyze` (`multipart`: `image` + optional
    `question` = typed text).
  - Text only → `POST {origin}/chat/api/query` (`{"question": ...}`).
- **Under the hood:** read `job_id` from the `202`, show a "thinking…" assistant bubble,
  **poll `GET {origin}/chat/api/jobs/{job_id}` every 2s** (well under the 600/min read
  budget) up to a ~120s timeout. On `completed`, render `result.raw`
  (`white-space: pre-wrap`); on `failed`/timeout, a friendly error bubble. **The `job_id`
  is never shown.**
- **Transcript:** user + assistant bubbles accumulate (visual history only — see
  Non-Goals re: no server memory).
- **Disclaimer:** persistent "research demo — not for clinical use" banner, matching the
  tone of `docs/api.md:17`.
- **Client-side guardrails:** reject non-JPEG/PNG and >10MB before upload with a friendly
  message (mirrors `app/files.py`), so the friend sees a clear message instead of a raw
  422. Images are **not** silently downscaled (would degrade diagnostic detail).

### Part C — Cloudflare Tunnel

- **Install** the single static binary (no system package, no sudo required as root):
  ```
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
  ```
- **`scripts/expose.sh`** — a small helper:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  # Exposes the local troke API (and the /chat page) over a temporary public URL.
  # Requires the full stack (Redis + vLLM + workers + API on :8000) running,
  # and CHAT_API_KEY set in .env so the /chat proxy is enabled.
  exec cloudflared tunnel --url http://localhost:8000
  ```
  It prints a `https://<random>.trycloudflare.com` URL. The friend opens
  `https://<random>.trycloudflare.com/chat` and just starts typing.
- The URL is **ephemeral** (changes each run). A stable custom-domain named tunnel is a
  documented follow-up, not part of this change.

## Data Flow (one image turn)

1. Friend types "what's wrong with this?" + attaches `xray.jpg`, hits send. (No key.)
2. JS `POST {origin}/chat/api/analyze` (multipart) → server: `enforce_submit_limits` on
   the shared `kh` → `submit_analysis("general", …, kh, r)` → `202 {job_id}`.
3. JS shows "thinking…" and polls `GET {origin}/chat/api/jobs/{job_id}` every 2s →
   `enforce_read_limit` → `fetch_job_status(job_id, kh, r)`.
4. Server: temp file → RQ `troke-jobs` → worker builds the `general` analyze prompt →
   vLLM → MedGemma → parsed → result stored in RQ (1h TTL).
5. Poll returns `{status: "completed", result: {raw, structured}}`; JS renders `raw`.

## Error Handling

- **Chat disabled** (`CHAT_API_KEY` unset) → proxy returns `503 chat_disabled`; the page
  shows "chat isn't enabled on this server."
- **Rate/queue limits** (`429 rate_limited` / `queue_full`, on the shared key) → JS shows
  "server busy, try again in a moment" (rare for one friend).
- **Parse failure** → `structured: null`, `raw` still shown. No special handling.
- **Job failed / poll timeout** → friendly error bubble; transcript preserved for retry.
- **Oversized / wrong-type image** → caught client-side before upload; server also
  rejects with `422 invalid_file` as a backstop.

## Testing (`pytest tests/ -v`)

Mirror the existing per-domain and jobs patterns:

- **`tests/test_routes_general.py`** (new) — clone `tests/test_routes_radiology.py` for the
  public `/v1/general/*` routes: analyze/query return a `job_id` (patching
  `app.routes._analyze.Queue` / `app.routes._query.Queue`), auth required, invalid-mime,
  oversized, empty-question.
- **`tests/test_routes_chat.py`** (new):
  - `GET /chat` → `200`, `text/html`, body contains a known marker (confirms the static
    file loads at import).
  - With `settings.chat_api_key` monkeypatched to a value: `POST /chat/api/query` and
    `/chat/api/analyze` return a `job_id` (patch `app.routes._query.Queue` /
    `app.routes._analyze.Queue`); **no `X-API-Key` header sent**.
  - `GET /chat/api/jobs/{id}` returns mapped status (patch `app.routes.jobs.Job.fetch`).
  - With `chat_api_key` empty → the three proxy routes return `503 chat_disabled`.
- **`tests/test_prompts.py`** (extend) — `build_messages("general", _IMG, "")` contains
  `FINDINGS/IMPRESSION/CONFIDENCE`; `build_messages("general", None, "")` contains
  `ANSWER/CONFIDENCE`; no `KeyError`.
- **`tests/test_inference.py`** (extend) — `parse_general` parses good output, returns
  `None` on garbage; `run_inference("general", img, "")` returns `raw` + `structured`.
- **`tests/test_auth.py`** / **`tests/test_routes_jobs.py`** (extend if needed) — confirm
  the refactored `check_job_quota` and `fetch_job_status` keep existing behavior (the
  existing tests should already cover this; add a direct test for the extracted helpers).

No change to `eval/` — the accuracy gate only iterates domains present in
`eval/cases/queries.json`, so `general` is inert there unless cases are added later.

## Documentation (same change, per CLAUDE.md)

- **`docs/api.md`** — add a `general` domain section (analyze + query) and its result
  shape; add a short "Chat UI" note describing `GET /chat` and that it's backed by
  server-side `/chat/api/*` proxy routes using a shared `CHAT_API_KEY` (not part of the
  public per-key API).
- **`README.md`** — add `general` to the domains table; add a "Share with a friend"
  section: set `CHAT_API_KEY`, run `scripts/expose.sh`, hand over the `…/chat` URL.
- **`CLAUDE.md`** — add `general` to the supported-domains list; note the `/chat` page +
  proxy + `CHAT_API_KEY` + tunnel.
- **`.env.example`** — add `CHAT_API_KEY=`.

## Security Considerations

- **The tunnel URL is the capability.** With no per-person key, anyone with the link can
  use the chat. That's the intended model for a private link handed to one friend, but it
  is the real security boundary — name it when sharing.
- **No key in the browser.** The proxy keeps `CHAT_API_KEY` server-side; it never reaches
  the page, `localStorage`, or view-source. This is the whole point of the proxy over
  baking a key into the HTML.
- **Chat is opt-in.** With `CHAT_API_KEY` unset (the default), `/chat/api/*` returns
  `503`, so merely deploying this doesn't expose an open endpoint. Rotate/disable by
  editing `CHAT_API_KEY` and restarting.
- **Rate + quota still apply** to the shared identity (60 submit/min, 600 poll/min, 10
  pending) — a runaway client self-throttles.
- **Admin endpoint is exposed by the tunnel.** `POST /v1/admin/keys` becomes reachable at
  the public URL, gated by `ADMIN_KEY`. **Preflight: confirm `ADMIN_KEY` in `.env` is long
  and random** before opening the tunnel.
- **PHI:** the in-UI disclaimer states research-only; real patient data should not be sent
  over an ephemeral tunnel. Consistent with the repo's logging rules that treat image
  bytes as PHI.

## Files

**New:** `app/routes/chat.py`, `app/static/chat.html`, `scripts/expose.sh`,
`tests/test_routes_general.py`, `tests/test_routes_chat.py`

**Modified:** `app/main.py` (add `general`; mount chat router), `config.py` (+`chat_api_key`),
`.env.example` (+`CHAT_API_KEY`), `app/auth.py` (factor helpers), `app/routes/jobs.py`
(extract `fetch_job_status`), `worker/prompts.py`, `worker/inference.py`,
`tests/test_prompts.py`, `tests/test_inference.py`, `docs/api.md`, `README.md`, `CLAUDE.md`

## Verification (end to end)

1. `pytest tests/ -v` — all green (existing 104 + new cases).
2. Set `CHAT_API_KEY` in `.env`. Start the stack (Redis, vLLM, workers, API).
   `curl -s localhost:8000/chat` returns the HTML page; `curl -s
   localhost:8000/chat/api/query -d '{"question":"hi"}' -H 'Content-Type: application/json'`
   returns a `job_id` (no key header).
3. Open `http://localhost:8000/chat`, send a text question and an image — confirm an
   answer renders, nothing asks for a key, and no job ID is visible.
4. `bash scripts/expose.sh`; open the printed `…/chat` URL on another device and repeat
   step 3 through the tunnel.

## Open Questions / Follow-ups (not in scope)

- Stable custom-domain named tunnel instead of the ephemeral `trycloudflare.com` URL.
- Optional per-person keys / an "advanced" domain override for power users.
- Whether to add `general` cases to the eval baseline.
