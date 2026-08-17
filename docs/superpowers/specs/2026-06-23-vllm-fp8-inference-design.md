# vLLM FP8 Inference — Design Spec

**Date:** 2026-06-23
**Status:** Approved (pending written review)
**Branch:** `vllm-fp8-inference`

## Goal

Make MedGemma inference fast on both axes — **low per-request latency** and **high concurrent throughput** — without losing accuracy in the cloud. Replace the worker's in-process `transformers.generate()` path with a dedicated **vLLM** serving engine.

## Constraints & decisions

- **No accuracy loss in the cloud.** Cloud serving stays `bfloat16`. Local development on an 8 GB RTX 4060 uses FP8 (user-accepted), because bf16 MedGemma-4B (~8.6 GB of weights) does not fit in 8 GB.
- **Single GPU.** No multi-node / network model-sharding. (Tensor/pipeline parallelism over a LAN would be far slower than a single quantized GPU — interconnect bandwidth is 100–1000× too low for per-layer all-reduce.)
- **One precision-configurable vLLM service**, env-switched: `fp8` locally, `bf16` in the cloud.
- **The async job contract is frozen.** `POST → job_id`, poll `GET /v1/jobs/{id}`, rate limits, pending-job tracking, and temp-file lifecycle are unchanged. Only the *inside* of the worker changes.

## Non-goals (deferred — YAGNI)

- vLLM **guided decoding** (JSON/regex-constrained output). The current parse-or-null contract is sufficient; revisit if parse-failure rate is a problem.
- A **mandatory FP8 accuracy gate**. `finetune/evaluate.py` can be pointed at the vLLM endpoint later to measure F1 drift, but no gate is built now.
- **Second-machine / multi-node replicas.** Horizontal scale-out is a cloud concern, handled later by running independent vLLM replicas behind the workers (data parallelism, never model sharding).
- **Pre-quantized (calibrated) FP8 checkpoints.** On-the-fly `--quantization fp8` is sufficient.

## Target architecture

```
Client → FastAPI (app/) → Redis (RQ queue) → Worker replicas ×N (CPU, HTTP client) → vLLM server (GPU, FP8/bf16)
                       ↑ poll /v1/jobs/{id} ↑
```

GPU ownership moves from the worker to a new `vllm` process. The worker becomes a stateless HTTP client and scales horizontally; vLLM does **continuous batching** across all in-flight worker requests, which is the source of the throughput gain.

| Process | Status | Owns GPU? |
|---|---|---|
| redis | unchanged | no |
| api | unchanged | no |
| **vllm** | **new** — `vllm/vllm-openai`, OpenAI-compatible API on `:8001` | **yes** |
| worker | **changed** — GPU-free HTTP client, run ×N replicas | no |

### Why this shape

troke already separates an HTTP layer that owns no model (`app/`) from a GPU layer (`worker/`). This design moves GPU ownership one hop further — to vLLM — and demotes the worker to a client. Continuous batching requires multiple requests in flight simultaneously; the serial `SimpleWorker` provides that by running N replicas, each pulling jobs independently and POSTing concurrently to vLLM.

## Component changes

### `worker/inference.py` (rewrite `run_inference`)
- Remove `get_model()` / `model.generate` usage and the `torch` import.
- Base64-encode the image (when present) into a `data:` URL.
- Build the OpenAI chat payload (see prompt parity below) and `POST {VLLM_URL}/chat/completions` with:
  - `model`: `settings.vllm_model` (defaults to `settings.model_id`; the LoRA name when an adapter is loaded)
  - `temperature: 0` (equivalent to today's greedy `do_sample=False`)
  - `max_tokens: settings.max_output_tokens` (default 512)
- `raw = response["choices"][0]["message"]["content"]`.
- **Regex parsers are unchanged** (`parse_radiology`, `parse_dermatology`, `parse_pathology`, `parse_ophthalmology`, `parse_dentistry`, `parse_query`, and `_ANALYZE_PARSERS`). Return shape stays `{"raw": ..., "structured": ...}`.
- Use a module-level `httpx.Client` with `timeout=settings.request_timeout_s`.

### `worker/prompts.py` (`build_messages`)
- Emit `{"type": "image_url", "image_url": {"url": data_url}}` instead of a PIL `{"type": "image", "image": ...}`.
- **Prompt parity:** keep the existing structure exactly — a single `user` message whose text is `f"{system}\n\n{question}"` (system prompt folded into the user turn, not a separate `system` role). This avoids perturbing the model's output format, which the parsers depend on.

### `worker/model.py`
- **Deleted.** No in-process model in the worker. The `transformers` loader is only needed by `finetune/`, which loads independently and does not import this module.

### `worker/start.py`
- Remove the `get_model()` preload and the stale "CUDA initialized once" comment.
- Add a startup readiness wait: poll vLLM `GET /health` until ready (bounded retries) before `SimpleWorker(...).work()`, so a replica never accepts a job before the engine is up.
- Keep `SimpleWorker` (no fork needed; cheap CPU process).

### `requirements-worker.txt`
- Remove `transformers`, `accelerate`, `peft`.
- Add `httpx`.

### `Dockerfile.worker`
- Base image `pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime` → `python:3.11-slim`. No CUDA/torch in the worker image.

### `docker-compose.yml`
- **New `vllm` service:**
  - `image: vllm/vllm-openai:<pinned>` (a version with Gemma-3 multimodal support).
  - command/args: `--model ${MODEL_ID} --served-model-name ${MODEL_ID} --port 8001 --gpu-memory-utilization 0.9 --max-model-len ${MAX_MODEL_LEN} [--quantization ${QUANTIZATION}] [--enable-lora --lora-modules ...]`.
  - `--quantization fp8` and LoRA flags are conditional on env being set.
  - GPU reservation moves here (from `worker`).
  - `healthcheck`: HTTP `GET /health`.
  - volume: `hf_cache`; env: `HUGGING_FACE_HUB_TOKEN` from `.env`.
- **`worker` service:** remove GPU reservation; base on slim image; add `VLLM_URL`; `depends_on: vllm` with `condition: service_healthy`. Scale via `docker compose up --scale worker=N` (default N=4 documented).

### `config.py` (add settings)
- `vllm_url: str = "http://vllm:8001/v1"`
- `vllm_model: str = ""` → resolved to `model_id` when empty
- `max_output_tokens: int = 512`
- `request_timeout_s: int = 120`
- vLLM launch flags (`QUANTIZATION`, `MAX_MODEL_LEN`, `gpu-memory-utilization`) live in compose/env — the client does not need them.

### `.env.example`
- Add `QUANTIZATION=fp8`, `MAX_MODEL_LEN=4096`, `VLLM_URL=http://vllm:8001/v1`, `HF_TOKEN=`, and a comment documenting `--scale worker=N`.

## Data flow (one request)

1. api validates → writes temp file → enqueues RQ job. *(unchanged)*
2. A worker replica picks up the job → opens the temp image → base64-encodes it → builds the domain chat payload.
3. Worker POSTs to vLLM `/v1/chat/completions` (`temperature=0`, `max_tokens=512`).
4. vLLM continuously batches this with other in-flight requests, runs FP8 (or bf16) inference, returns completion text.
5. Worker regex-parses → `{raw, structured}` → stored as the RQ job result (Redis, 1h TTL); temp file deleted in `finally`. *(unchanged)*
6. Client polls `/v1/jobs/{id}` and receives the result. *(unchanged)*

## FP8 / precision strategy

- vLLM `--quantization fp8` performs **on-the-fly** FP8 quantization of the bf16 checkpoint at load (no pre-quantized files), using the 4060's native Ada FP8 path. Weights ≈ 4.3 GB, fits 8 GB with room for the KV cache and vision activations.
- **8 GB tuning knobs:** `--max-model-len 4096`, `--gpu-memory-utilization 0.9`, `--max-num-seqs` (tune down if OOM), `--enforce-eager` as a fallback if CUDA-graph capture memory is too tight (costs some speed).
- **Cloud:** same service, `QUANTIZATION=""` (bf16) and a larger `MAX_MODEL_LEN`.
- **LoRA preserved:** when `ADAPTER_PATH` is set, launch vLLM with `--enable-lora --lora-modules <name>=<path>` and set `vllm_model` to `<name>`.

## Error handling

- vLLM unreachable / timeout / non-200 → worker raises → existing `process_job` try/finally logs `job_failed`, clears the `pending:{key_hash}` set, and deletes the temp file. The job surfaces as the existing `inference_failed` code; a distinct `inference_unavailable` code was considered but **deferred** (see the plan), so no new error code is introduced. No stack traces leak (existing convention).
- Parse failure → **unchanged**: `structured=null`, `raw` still returned, job never fails.
- Determinism preserved via `temperature=0`.
- vLLM OOM at startup → server fails health check → workers wait (they never accept jobs). Tuning knobs above are the remedy; documented in CLAUDE.md.

## Testing

- `tests/test_inference.py`: replace the `get_model` mock with a mocked `httpx` call. Assert payload shape (`model`, `temperature=0`, `max_tokens`, image data-URL present for `/analyze` and absent for `/query`) and that a canned vLLM response parses into the correct `structured` dict. Parser unit tests stay as-is.
- Remove the obsolete `worker.model` import path from tests.
- `app/` route tests unchanged (they mock `Queue`; the contract is intact).
- Update `CLAUDE.md` testing notes: "mock the vLLM HTTP client in `worker.inference`" replaces "mock `get_model`".

## Docs to update (repo's "After Every Change" rule)

- `README.md` — architecture diagram + how-it-works (worker is now a client; vLLM owns the GPU).
- `docs/api.md` — no endpoint surface change expected; note the new internal serving path if referenced.
- `docs/quickstart.md` — new run instructions (start vLLM, scale workers).
- `CLAUDE.md` — architecture, commands (local: `vllm serve ...` + N workers), env vars, testing notes.

## Run instructions (to document)

**Docker (local, 8 GB 4060):**
```bash
cp .env.example .env   # set ADMIN_KEY, HF_TOKEN; QUANTIZATION=fp8
docker compose up --build --scale worker=4
```

**Local (no Docker):**
```bash
redis-server
vllm serve google/medgemma-4b-it --quantization fp8 --max-model-len 4096 \
  --gpu-memory-utilization 0.9 --port 8001
uvicorn app.main:app --host 0.0.0.0 --port 8000   # API
python -m worker.start                            # run several of these
```

## Risks / open items

- **vLLM image/version pin** must include Gemma-3 multimodal support; verify the chosen tag serves MedGemma-4B with `image_url` inputs before finalizing.
- **8 GB headroom** is tight with vision prefill; `--max-num-seqs` / `--enforce-eager` may need tuning empirically on the actual card.
- **FP8 + LoRA** interaction in vLLM should be verified if an adapter is used locally (cloud bf16 + LoRA is the safe combination).
