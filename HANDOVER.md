# Handover Notes

Full context for the next Claude session. Read this, then `CLAUDE.md`, before doing anything.

Last updated: 2026-07-22 (overnight session: +8 departments, streaming, DICOM, status bar, stats).

---

## TL;DR — where things stand

- **Shipped & live (all uncommitted, branch `vllm-fp8-inference`):**
  1. a friend-facing **chat feature** — key-less `/chat` page backed by a server-side proxy,
     a `general` catch-all domain, and a Cloudflare Tunnel script;
  2. **21 departments total** — the original 13 plus 8 added 2026-07-22 (`oncology`,
     `endocrinology`, `nephrology`, `urology`, `gynecology`, `pediatrics`, `otolaryngology`,
     `emergency`), all via TDD; existing prompts polished to board-certified specialist voices.
  3. **Live token streaming** — vLLM `stream=True` → worker RPUSHes deltas to a Redis LIST
     `chat:stream:{job_id}` → SSE `GET /chat/api/stream/{id}` → browser `EventSource` renders
     live (first token < 1 s). Poll fallback if the stream drops.
  4. **DICOM upload** — `app/files.py` (`is_dicom` + `dicom_to_png`) transcodes `.dcm` → PNG
     API-side (VOI LUT, MONOCHROME1 invert, multi-frame/colour collapse); non-image DICOMs →
     clean 422. Needs `pydicom`/`numpy`/`pylibjpeg*` (now in `requirements-api.txt`).
  5. **Model status bar + warmup progress** (`GET /chat/api/status`) and a **⚡ Stats panel**
     (`InferenceResult.stats`: tokens/sec, latency, token count).
  - Also: vLLM client `request_timeout_s` 120→**240** (long streamed answers no longer
    ReadTimeout). All **267 tests pass** (was 213).
- **Running now:** full native stack (Redis + vLLM + worker + API) **+ live Cloudflare Tunnel**.
  vLLM at `--gpu-memory-utilization 0.85`, `--max-model-len 6144`, `--max-num-seqs 1`,
  `HF_HUB_OFFLINE=1` (see [Incident 2026-07-21](#incident-2026-07-21--vllm-crash--hardened-restart)).
  **Restart discipline:** the tunnel + vLLM stay up across code changes — restart only worker+API
  (or API-only for `app/`-side changes like `files.py`) so the tunnel URL never changes.
  Throughput ~10–11 tok/s serial; a long rich answer ≈ 80 s total but streams from ~0.6 s.
- **No open task** at session end beyond letting the live test harness finish. **Ask before
  committing** — nothing is committed yet.
- **Design spec** for the chat work: `docs/superpowers/specs/2026-07-21-friend-chat-access-design.md`.

---

## Architecture (CURRENT — the old notes below the fold were wrong)

This branch runs **vLLM as a separate server that owns the GPU**. The worker is now a
**stateless HTTP client** of vLLM — it does NOT load a model. (An earlier version loaded
MedGemma inside the worker via `worker/model.py`; that's gone. Ignore any mention of
`worker/model.py`, `SimpleWorker`-owns-the-GPU, or `device_map="auto"`.)

```
Client → FastAPI (app/, :8000) → Redis queue → Worker replicas (HTTP client) → vLLM (:8001, GPU) → MedGemma
                              ↑ poll status ↑
```

- **`app/`** — HTTP only. Validates, enqueues, returns job IDs. No model.
- **`worker/`** — pulls RQ jobs, builds the OpenAI chat payload (`prompts.py`), calls vLLM
  over HTTP (`inference.py`), parses structured text. `WORKER_REPLICAS=N` runs N of them.
- **vLLM** — `/root/vllm-venv/bin/vllm serve …` on :8001. Owns the GPU (RTX 4060, 8 GB).
- **Redis** — runs natively on the host (`redis-cli ping` → PONG). **Docker is NOT usable
  here** (Docker Desktop isn't running in WSL), so `docker compose up` does not work —
  everything is started natively.

Two venvs: the app/worker venv is `.venv` (has `uvicorn`, `rq`, not `vllm`); vLLM has its
own `/root/vllm-venv` (has `vllm`). The MedGemma weights are cached at
`~/.cache/huggingface/hub/models--google--medgemma-4b-it` (8.1 GB) — vLLM loads from disk
(~2–3 min), no re-download.

---

## What the chat feature is (just built)

Goal: let a non-technical friend abroad use the service like a chatbot — **no job IDs, no
domain picker, no API key to paste.**

- **`general` domain** — a domain-agnostic catch-all (generalist prompt + a
  `FINDINGS/IMPRESSION/CONFIDENCE` parser). Added via the existing domain factory. Files:
  `app/main.py` (`DOMAINS`), `worker/prompts.py` (`_ANALYZE`/`_QUERY`),
  `worker/inference.py` (`parse_general` + `_ANALYZE_PARSERS`).
- **Key-less chat** — `app/routes/chat.py` serves `app/static/chat.html` at `GET /chat`,
  plus proxy routes `POST /chat/api/analyze`, `POST /chat/api/query`,
  `GET /chat/api/jobs/{id}`. The browser sends **no key**; the server attaches
  `settings.chat_api_key` and reuses `submit_analysis` / `submit_query` /
  `fetch_job_status`. Header-free limit helpers `enforce_submit_limits` /
  `enforce_read_limit` live in `app/auth.py`. All chat jobs use the `general` domain.
- **Opt-in** — with `CHAT_API_KEY` unset, the proxy returns `503 chat_disabled`. It is
  currently **set** in `.env` (see below), so chat is live.
- **Tunnel** — `scripts/expose.sh` runs `cloudflared tunnel --url http://localhost:8000`.
  `cloudflared` is installed at `/usr/local/bin/cloudflared` (v2026.7.2). Share the printed
  `https://<random>.trycloudflare.com/chat`.

### The minted token
`.env` now has **`CHAT_API_KEY`** set to a freshly minted key (also registered in Redis
`api_keys`, so it doubles as a normal `/v1` key). The raw value lives only in `.env`
(gitignored) — it is intentionally NOT written here. Rotate by editing `CHAT_API_KEY` and
restarting the API.

> Security: the tunnel URL is the only thing gating chat access (capability URL). It also
> exposes `/v1/admin/keys`, gated by `ADMIN_KEY` — which is already a strong value in
> `.env`. Research demo only; no real patient data over the tunnel.

---

## Operating the running stack

Started natively as background processes; PIDs in `logs/pids.txt`, logs in `logs/`
(gitignored).

**Health checks**
```bash
redis-cli ping                                   # PONG
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/chat      # 200
curl -s localhost:8001/v1/models -o /dev/null -w '%{http_code}\n' # 200 once vLLM finished loading
tail -f logs/vllm.log logs/worker.log logs/api.log
```

**Restart a piece** (kill via `logs/pids.txt`, then re-run):
```bash
# vLLM (separate venv, owns GPU). HF_HUB_OFFLINE loads from the local cache — no HF
# round-trip, so no gated-repo 401 on restart. SERIAL config: --max-num-seqs 1 (one
# request at a time), --max-model-len 6144 (covers the app's ~3.5k-token cap), util 0.85
# (~1.0-1.5GB VRAM free, host-dependent). Drop to 0.80 if you ENOMEM. See "Tuning 2026-07-21".
nohup env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN \
  /root/vllm-venv/bin/vllm serve google/medgemma-4b-it --quantization fp8 \
  --max-model-len 6144 --gpu-memory-utilization 0.85 --max-num-seqs 1 \
  --no-enable-prefix-caching --limit-mm-per-prompt '{"image": 1}' \
  --enforce-eager --port 8001 > logs/vllm.log 2>&1 &

# worker (1 replica — serial, one request at a time; the Redis queue is the waiting line)
nohup env WORKER_REPLICAS=1 .venv/bin/python -m worker.start > logs/worker.log 2>&1 &

# API
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
```
The worker health-checks vLLM (`vllm_waiting` in `logs/worker.log`) and starts processing
once `:8001` is up, so worker/API can start before vLLM finishes loading.

**Expose to the friend:** `bash scripts/expose.sh` → share `<printed-url>/chat`.

### Incident 2026-07-21 — vLLM crash + hardened restart
- **Symptom:** chat showed "analysis failed"; vLLM had died with `torch.AcceleratorError:
  CUDA error: unknown error`, freeing the GPU. Root cause (via dmesg
  `dxgkio_make_resident: -12` ENOMEM during load): at `--gpu-memory-utilization 0.85`
  only ~800 MiB VRAM slack, and on WSL2 the Windows host can spike GPU memory invisibly
  to WSL → over physical VRAM → hard fault.
- **Fix applied (config now live):** relaunched with `--gpu-memory-utilization 0.80`
  (~1.2 GiB slack) and `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` (a naive
  `HF_TOKEN`-from-.env restart 401'd on the gated repo; offline avoids HF entirely since
  weights + tokenizer chat template are cached). Restart command updated above + in CLAUDE.md.
- **Tradeoff:** at 0.80, KV cache = 0.37 GiB / 2,747 tokens → max concurrency ~1.34x for
  full 2048-token requests. Fine for this demo (2 worker replicas; typical requests are
  far shorter). If you see queuing under load, nudge util up (e.g. 0.82) OR try
  `--kv-cache-dtype fp8_e4m3` (test with the accuracy harness first). Keep WORKER_REPLICAS
  aligned with KV size — do NOT raise above what vLLM can hold concurrently.

### Tuning 2026-07-21 — serial single-user config (current live)
- **Config now:** `--gpu-memory-utilization 0.85 --max-model-len 6144 --max-num-seqs 1`
  + `WORKER_REPLICAS=1`. Strictly one request at a time; everyone else waits in the
  Redis `troke-jobs` queue. At the earlier 4096 window: ~6.4 GB VRAM used / ~1.0–1.5 GB
  free (host-dependent), KV pool 9,472 tokens; 6144 still fits that pool (1.54x margin).
- **Context sizing:** `max-model-len 6144` covers the app's ~3.5k-token request cap
  (chat history ≤8000 chars ≈2000 tok via `chat_memory_char_budget`, question ≤500,
  output ≤1024 via `max_output_tokens`, 1 image ≈256). `--max-num-seqs 1` frees the
  activation memory `seqs 4` reserved, ~doubling the KV pool at the same util.
- **Also added 2026-07-21:** 3 departments (cardiology, hematology, rheumatology →
  **13 total**), a per-message chat department selector (`GET /chat/api/domains` +
  `domain` field; `DOMAINS` extracted to `app/domains.py`), and the context bump above.
  228 tests pass. Needs a restart of API+workers (new code/config) and vLLM (6144).
- **RAM note (asked & investigated):** vLLM's ~4 GB system RAM is irreducible CUDA +
  PyTorch runtime (per process: API frontend + EngineCore); the model weights are 100%
  in VRAM. There is NO RAM→VRAM offload (only the reverse, `--cpu-offload-gb`, which we
  keep at 0). `VLLM_ENABLE_V1_MULTIPROCESSING=0` had no effect; `--swap-space` doesn't
  exist in vLLM V1 (v0.23.0). The low `free` column is reclaimable model-file page cache;
  `available` (~5.8 GB) is the real headroom. More RAM ⇒ raise WSL's cap in `.wslconfig`.
- **Spike caveat still applies:** 0.85 leaves less slack than 0.80. Under a documented
  ~800 MB Windows-host VRAM spike, 0.85's ~1.0 GB-floor readings can dip toward 600 MB;
  if you see ENOMEM / "CUDA error: unknown error", fall back to 0.80.

---

## Departments (10 total — 4 added 2026-07-21)

Full list: `radiology`, `dermatology`, `pathology`, `ophthalmology`, `dentistry`, `general`,
and — added 2026-07-21 via TDD — `orthopedics`, `pulmonology`, `neurology`,
`gastroenterology`. All wired end-to-end (routes + analyze/query prompts + parsers) and
**live** (the running API/workers were restarted to pick them up). Live-verified with a real
`/v1/orthopedics/query` inference; `169 tests pass`.

Analyze schemas for the four new ones (they mirror the existing `FINDING`/`AFFECTED_*` enum
style, `SEVERITY: normal|mild|moderate|severe`, `CONFIDENCE: low|medium|high`):

| Domain | Analyze fields |
|---|---|
| orthopedics | `FINDING`, `AFFECTED_BONE`, `SEVERITY`, `CONFIDENCE` → finding, affected_bone, severity, confidence |
| pulmonology | `FINDING`, `AFFECTED_REGION`, `SEVERITY`, `CONFIDENCE` → finding, affected_region, severity, confidence |
| neurology | `FINDING`, `AFFECTED_REGION`, `SEVERITY`, `CONFIDENCE` → finding, affected_region, severity, confidence |
| gastroenterology | `FINDING`, `LOCATION`, `SEVERITY`, `CONFIDENCE` → finding, location, severity, confidence |

**MedGemma-fit caveat (still true):** orthopedics/pulmonology are good (X-ray/chest adjacent),
neurology moderate, gastroenterology weaker (more bluffing on endoscopy). The user chose all
four knowingly.

**Known-benign quirk:** query answers share `parse_query`, which returns `structured=null`
when the model omits the `CONFIDENCE:` line (e.g. list-style answers — seen live on the
orthopedics query). That's the intended graceful path — `raw` text is always returned and the
job never fails on a parse miss. It affects all 10 domains identically; not a departments bug.

The chat page uses only `general`, so the new departments are reachable via `/v1/<domain>/…`
with an API key (they'd only appear in `/chat` if you add a picker — intentionally omitted).

Note: adding domains is inert for `eval/` unless you add cases to `eval/cases/queries.json`.

### How to add ANOTHER domain (generic recipe)
Copy any existing domain (`general` is the simplest template). **Use TDD** (test-driven-development
skill) — write the failing test, watch it fail, then implement. Per touch point:

1. **`worker/prompts.py`** — add the domain to **both** `_ANALYZE` and `_QUERY`
   (a `KeyError` at `build_messages` if you forget either). Query prompts must keep the
   `ANSWER:/CONFIDENCE:` format so the shared `parse_query` works.
2. **`worker/inference.py`** — add a `parse_<domain>` + regex and register it in
   `_ANALYZE_PARSERS`. (`.get(domain)` degrades to `structured=null` if it's missing, but
   add it for real.)
3. **`app/main.py`** — append the domain to `DOMAINS` (auto-registers `/v1/<domain>/…`).
4. **Tests** — new `tests/test_routes_<domain>.py` (clone an existing one);
   extend `tests/test_prompts.py` and `tests/test_inference.py`.
5. **Docs** (same change, per CLAUDE.md) — `docs/api.md` (endpoint + result table),
   `README.md` (domains table), `CLAUDE.md` (`## Domains` list).
6. **Deploy** — the running API/workers don't hot-reload; restart them (NOT vLLM) so new
   routes register and workers have the new prompt/parser. See
   [Operating the running stack](#operating-the-running-stack).

---

## What's next

Nothing is required — the requested work is done. Options, if the developer wants more:

1. **Commit the work.** Everything is uncommitted on `vllm-fp8-inference` (chat feature +
   4 departments + memory hardening + this handover). The developer prefers to commit
   themselves — **ask first.**
2. **Chat domain picker.** `/chat` is hard-wired to `general`. A small dropdown could let the
   friend target a specific department (requires a picker in `chat.html` + threading the
   domain through the `/chat/api/*` proxy, which currently forces `general`).
3. **Eval coverage** for the new domains — add cases to `eval/cases/queries.json`.
4. **Concurrency tuning** — if the demo sees queuing, nudge vLLM util 0.80 → 0.82 or try
   `--kv-cache-dtype fp8_e4m3` (test with the accuracy harness). See the incident note.

---

## Verify before claiming done
- `pytest tests/ -v` → all pass (169 as of 2026-07-21; more if you add domains).
- Real inference smoke: once vLLM is up, submit through `/chat` (keyless) or
  `curl -X POST localhost:8000/v1/<domain>/analyze -H "X-API-Key: <CHAT_API_KEY>" -F image=@some.jpg -F question=...`
  then poll `GET /v1/jobs/{id}`. (For a text-only smoke use `/v1/<domain>/query`.)

## Uncommitted work / git
Branch `vllm-fp8-inference`. Everything below is uncommitted (the developer commits
themselves — **ask before committing**):
- **Chat feature:** `app/routes/chat.py`, `app/static/chat.html`, `scripts/expose.sh`,
  `tests/test_routes_chat.py`, the design spec, `app/auth.py` helpers.
- **4 departments:** `worker/prompts.py`, `worker/inference.py`, `app/main.py`,
  `tests/test_routes_{general,orthopedics,pulmonology,neurology,gastroenterology}.py`,
  `tests/test_prompts.py`, `tests/test_inference.py`, and docs
  (`docs/api.md`, `README.md`, `CLAUDE.md`).
- **Memory hardening:** the vLLM restart command (0.80 + offline) in `CLAUDE.md` +
  this file, and the incident note.
- `logs/` is gitignored.
