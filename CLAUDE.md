# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A B2B REST API wrapping MedGemma 4B for async medical image analysis. Three components: a FastAPI HTTP server, stateless RQ worker replicas (no GPU), and a dedicated vLLM server that owns the GPU and serves MedGemma.

## Commands

```bash
# Run tests
pytest tests/ -v

# Run single test file
pytest tests/test_auth.py -v

# Start Redis (required before API or worker)
redis-server

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start vLLM server (owns the GPU). Flags fit MedGemma-4B (fp8) on an 8GB GPU.
# On a bare `pip install vllm` (no CUDA toolkit), FlashInfer can't JIT-compile, so
# force the native sampler + FlashAttention.
# HF_HUB_OFFLINE loads purely from the local cache — no HF round-trip, so restarts
# can't 401 on the gated repo (weights are cached; the chat template ships inside
# tokenizer_config.json, and chat_template.json is correctly cached as .no_exist).
# SERIAL SERVICE: --max-num-seqs 1 (paired with WORKER_REPLICAS=1 below) serves one
# request at a time; everyone else waits in the Redis queue. With a single sequence the
# whole KV pool (~9.5k tokens at 0.85) serves it, so --max-model-len 6144 fits with margin.
# The app caps each request server-side to ~3.5k tokens (history ≤8000 chars ≈2000 tok +
# question ≤500 + output ≤1024 + 1 image ≈256), so 6144 leaves room and the KV isn't idle.
# gpu-memory-utilization 0.85 → ~1.0–1.5 GB VRAM free (host-dependent on WSL2, where the
# Windows host can spike GPU memory invisibly). If you hit a dxg make_resident ENOMEM /
# "CUDA error: unknown error" under a host spike, drop to 0.80 (~1.6 GB slack).
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN \
vllm serve google/medgemma-4b-it --quantization fp8 \
  --max-model-len 6144 --gpu-memory-utilization 0.85 --max-num-seqs 1 \
  --no-enable-prefix-caching --limit-mm-per-prompt '{"image": 1}' \
  --enforce-eager --port 8001

# Start workers (HTTP clients; no GPU). SERIAL: WORKER_REPLICAS=1 → a single worker
# pulls one job, runs it to completion, then pulls the next — the Redis queue is the
# waiting line. Raise it only if you also raise vLLM --max-num-seqs for concurrency.
WORKER_REPLICAS=1 python -m worker.start

# Create first API key (requires ADMIN_KEY in env)
curl -X POST http://localhost:8000/v1/admin/keys -H "X-API-Key: $ADMIN_KEY"
```

## Environment

Uses a conda venv. All required libs are pre-installed. Copy `.env.example` to `.env` and set `ADMIN_KEY` before running.

## Architecture

```
Client → FastAPI (app/) → Redis queue → Worker replicas (HTTP client) → vLLM server (GPU) → MedGemma
                       ↑ poll status ↑
```

- **`app/`** — HTTP layer only. No model loaded here. Validates requests, enqueues jobs, returns job IDs.
- **`worker/`** — Stateless HTTP client of vLLM. No GPU, no model. Pulls jobs, builds the
  OpenAI chat payload (`prompts.py`), calls vLLM (`inference.py`), parses the structured text.
  Run several replicas to feed vLLM's continuous batcher.
- **`vllm`** — Owns the GPU. `vllm/vllm-openai` serving MedGemma; FP8 locally, bf16 in cloud.
- **`config.py`** — All settings via env vars using pydantic-settings.
- **`app/deps.py`** — Redis singleton. Override with `app.dependency_overrides[get_redis]` in tests.

## Key Conventions

**Auth flow:** `X-API-Key` header → `sha256(key)` compared against Redis set `api_keys`. Raw keys never stored. Rate limit tracked in `rate:{key_hash}` with 60s TTL. Pending job count tracked in `pending:{key_hash}` set.

**Job lifecycle:** Submit → temp file written to `settings.temp_dir/{job_id}.img` → enqueued to RQ queue `troke-jobs` → worker processes → result stored in RQ job result (Redis, 1h TTL) → temp file deleted in `finally`.

**Response format:** Both image analysis and text Q&A are prompted for rich, sectioned **Markdown** (rendered in the chat like ChatGPT), built from shared templates in `worker/prompts.py` (`_ANALYZE_TEMPLATE` / `_QUERY_TEMPLATE`, parameterized per domain via the `_SPECIALIST` map). The legacy regex parsers in `worker/inference.py` still run, but Markdown won't match them, so `structured` is now typically `null` and `raw` (the Markdown) is the answer — never fail the job for a parse miss.

**Error responses:** Always `{"error": "short_code", "message": "..."}`. Never expose stack traces. See `app/routes/jobs.py` `_STATUS` map for RQ → API status mapping.

**Logging:** structlog JSON, one line per event. Allowlisted fields only — never log model output, image bytes, raw keys, or anything that could be PHI. Always include `key_hash` (not raw key) for traceability.

## Testing

- Use `fakeredis.FakeRedis(decode_responses=True)` for all Redis in tests
- Override Redis via `app.dependency_overrides[get_redis] = lambda: fake_redis`
- Mock `Queue` at `app.routes.<domain>.Queue` to avoid real RQ calls
- Mock `Job.fetch` at `app.routes.jobs.Job.fetch` for job status tests
- Mock the vLLM HTTP call at `worker.inference._client.post` — never hit a real server in tests

## After Every Change

Always update in the same commit:
- **Tests** — add or update tests covering the changed behavior
- **`docs/api.md`** — reflect any new or modified endpoints, fields, or request/response shapes
- **`README.md`** — update the domains table or how-it-works section if the surface area changed

## Domains

Currently supported: `radiology`, `dermatology`, `pathology`, `ophthalmology`, `dentistry`, `general`, `orthopedics`, `pulmonology`, `neurology`, `gastroenterology`, `cardiology`, `hematology`, `rheumatology`, `oncology`, `endocrinology`, `nephrology`, `urology`, `gynecology`, `pediatrics`, `otolaryngology`, `emergency`. Adding a new domain requires:
1. Add the domain to the `DOMAINS` list in **`app/domains.py`** (the single source of
   truth; `app/main.py` registers routes from it, `app/routes/chat.py` builds the chat
   dropdown from it — so they can't drift)
2. One line in the `_SPECIALIST` map in `worker/prompts.py` (specialist voice + image
   type) — that builds both the rich analyze and query prompts from the shared templates
3. (Optional) a parser + regex in `worker/inference.py` — only needed if you want
   structured extraction; replies are rich Markdown by default, so `structured` is null

`general` is a domain-agnostic catch-all; it's the chat surface's default department.

## Chat surface

`app/routes/chat.py` serves a static chat page at `GET /chat` (`app/static/chat.html`)
plus **key-less** proxy routes `POST /chat/api/analyze`, `POST /chat/api/query`,
`GET /chat/api/jobs/{id}`, `GET /chat/api/status`, and `GET /chat/api/stream/{id}`. The
browser sends no key; the server attaches `settings.chat_api_key` server-side and reuses
`submit_analysis` / `submit_query` / `fetch_job_status` (extracted from `jobs.py`) via the
header-free `enforce_submit_limits` / `enforce_read_limit` helpers in `app/auth.py`.
Disabled (`503 chat_disabled`) unless `CHAT_API_KEY` is set. `scripts/expose.sh` exposes
`:8000` over a Cloudflare Tunnel so a remote user can reach `/chat`.

**Live token streaming:** vLLM is called with `stream=True` in `run_inference` (when a
`publish` callback is passed). `process_job` passes a publisher that RPUSHes each token
delta into a Redis LIST `chat:stream:{job_id}` (+ a trailing `done`/`error` marker with
stats), TTL ~300s. `GET /chat/api/stream/{job_id}` is an SSE endpoint whose sync generator
`BLPOP`s that list and forwards `data:` frames until the marker — a LIST (not pub/sub) so a
late-connecting browser still gets every token. The page opens an `EventSource`, renders
tokens live, and **falls back to `/chat/api/jobs/{id}` polling** if the stream drops. The
non-streaming path in `run_inference` (no `publish`) is retained for direct callers/tests.

**Model status + stats:** `GET /chat/api/status` proxies vLLM `/health` → `{model_ready,
detail}`; the page polls it to drive the **top status bar** (🟡 warming / 🟢 ready) and a
cold-start progress bar. Each result carries an `InferenceResult.stats`
(`completion_tokens`, `inference_ms`, `tokens_per_second`) captured from vLLM's usage
chunk; the page's **⚡ Stats** panel shows per-response speed and session averages.

**DICOM upload:** `app/files.py::is_dicom` (the `DICM` magic at byte 128) + `dicom_to_png`
transcode uploaded `.dcm` files to PNG **in `submit_analysis` (API-side)** — VOI/windowing
LUT, MONOCHROME1 inversion, multi-frame/colour collapse, 8-bit normalize — so the worker
and vLLM only ever see a standard image. Non-renderable DICOMs (structured reports, RT
plans, waveforms, truncated files) degrade to a clean `422`, never a 500. Requires
`pydicom`/`numpy`/`pylibjpeg*` in the API venv. The chat picker accepts `.dcm` and uploads
it raw (canvas can't downscale DICOM).

**Department selector:** `GET /chat/api/domains` returns `app.domains.DOMAINS`; the page
builds a dropdown from it and sends `domain` per message. `chat.py` validates it via
`_valid_domain` (unknown/absent → `general`, never an error) and passes it to `submit_*`.
Memory is domain-agnostic text, so switching department mid-conversation just changes the
next message's specialty — history carries.

**Conversation memory:** `worker/memory.py` is the only code that knows the memory
layout — a Redis LIST at `chat:conv:<conversation_id>` of `{"role","text"}` JSON entries.
`load_history` reads it newest-first up to `chat_memory_char_budget`; `append_turn`
trims each side, `LTRIM`s to `chat_memory_max_turns` entries, and refreshes
`chat_memory_ttl_seconds` (all in `config.py`). The browser holds a UUID
`conversation_id` in `sessionStorage` (rotated by the "New chat" button); it flows
`chat.py` (UUID-validated, invalid/absent → stateless) → `submit_*` → `process_job`,
defaulting to `None` everywhere so `/v1` stays stateless. `process_job` loads history
before inference and appends the turn on success only; image turns are stored as a
`[shared a medical image] <question>` placeholder — image bytes are never persisted.
Logging stays allowlisted: `conversation_id` + `history_turns` count only, never turn
text (may be PHI).
