# vLLM FP8 Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the worker's in-process `transformers.generate()` path with a dedicated vLLM OpenAI server (continuous batching) fed by GPU-free client workers, for low latency + high throughput.

**Architecture:** A new `vllm` process owns the GPU and serves an OpenAI-compatible API. The RQ worker becomes a stateless HTTP client and runs as N replicas, so multiple requests are in flight at once and vLLM batches them. The async job/poll contract is unchanged — only the worker's internals change.

**Tech Stack:** Python, FastAPI (unchanged), RQ + Redis, `httpx` (new, worker→vLLM), vLLM (`vllm/vllm-openai` image), Docker Compose. MedGemma-4B served FP8 locally (8 GB RTX 4060) / bf16 in cloud.

## Global Constraints

- Cloud serving stays **bfloat16** (no accuracy loss). Local 8 GB 4060 uses **FP8** (`--quantization fp8`).
- **Single GPU.** No multi-node / network model-sharding.
- **One precision-configurable vLLM service**, env-switched: `QUANTIZATION=fp8` local, `QUANTIZATION=` (empty → bf16) cloud.
- **Async job contract is frozen:** `POST → job_id`, poll `GET /v1/jobs/{id}`, rate limits, pending-job tracking, temp-file lifecycle — all unchanged. `app/` is not modified. `worker/worker.py` `process_job` signature is unchanged.
- **Prompt parity:** one `user` message; text is exactly `f"{system}\n\n{question}"`; image goes in the user turn (no separate `system` role).
- **Determinism parity:** request uses `temperature: 0` (equivalent to today's greedy `do_sample=False`).
- **Regex parsers unchanged:** all `parse_*` functions, the `_RE` regexes, and `_ANALYZE_PARSERS` in `worker/inference.py` stay byte-for-byte identical.
- **Deferred (do NOT build):** vLLM guided decoding; a mandatory FP8 accuracy gate; multi-node replicas; pre-quantized FP8 checkpoints. A distinct `inference_unavailable` API code is **deferred** — all inference failures (including vLLM-down) cleanly surface as the existing `inference_failed` (no stack traces), which already satisfies the error contract.

---

### Task 1: Client config settings + env

**Files:**
- Modify: `config.py` (add fields to `Settings`)
- Modify: `.env.example`
- Test: `tests/test_config.py` (create)

**Interfaces:**
- Produces: `settings.vllm_url: str`, `settings.vllm_model: str`, `settings.max_output_tokens: int`, `settings.request_timeout_s: int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from config import Settings


def test_vllm_client_settings_defaults():
    s = Settings(_env_file=None)
    assert s.vllm_url == "http://vllm:8001/v1"
    assert s.vllm_model == ""
    assert s.max_output_tokens == 512
    assert s.request_timeout_s == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`/assertion on missing `vllm_url`.

- [ ] **Step 3: Add the settings**

In `config.py`, inside `class Settings`, add these four lines immediately after the existing `adapter_path: str = ""` line (before `temp_dir`):

```python
    vllm_url: str = "http://vllm:8001/v1"
    vllm_model: str = ""
    max_output_tokens: int = 512
    request_timeout_s: int = 120
```

- [ ] **Step 4: Update `.env.example`**

Append to `.env.example`:

```bash
# vLLM serving (worker is an HTTP client of this server)
VLLM_URL=http://vllm:8001/v1
# vLLM server launch flags (consumed by docker-compose, not the app):
#   QUANTIZATION=fp8 fits MedGemma-4B on an 8GB GPU; set empty for bf16 (cloud, full accuracy)
QUANTIZATION=fp8
MAX_MODEL_LEN=4096
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add config.py .env.example tests/test_config.py
git commit -m "feat: add vLLM client settings and env vars"
```

---

### Task 2: OpenAI-format prompt builder

**Files:**
- Modify: `worker/prompts.py` (`build_messages`)
- Test: `tests/test_prompts.py` (rewrite image-related parts)

**Interfaces:**
- Produces: `build_messages(domain: str, image_url: Optional[str], question: str) -> list[dict]`. Returns `[{"role": "user", "content": [...]}]`. When `image_url` is not None, content includes `{"type": "image_url", "image_url": {"url": image_url}}` followed by `{"type": "text", "text": f"{system}\n\n{question}"}`. When None, only the text part.

- [ ] **Step 1: Rewrite the failing tests**

Replace the entire contents of `tests/test_prompts.py` with (note: `image_url` is now a string, and image parts have `type == "image_url"`):

```python
from worker.prompts import build_messages

_IMG = "data:image/png;base64,QUJD"


def _text(msgs) -> str:
    """Extract the text content from the single user message."""
    return next(p["text"] for p in msgs[0]["content"] if p["type"] == "text")


def _image_parts(msgs):
    return [p for p in msgs[0]["content"] if p["type"] == "image_url"]


def test_radiology_analyze_prompt_has_all_fields():
    text = _text(build_messages("radiology", _IMG, ""))
    for field in ("FINDINGS:", "IMPRESSION:", "SEVERITY:", "CONFIDENCE:"):
        assert field in text


def test_dermatology_analyze_prompt_has_all_fields():
    text = _text(build_messages("dermatology", _IMG, ""))
    for field in ("CONDITION:", "SEVERITY:", "RECOMMENDATION:", "CONFIDENCE:"):
        assert field in text


def test_pathology_analyze_prompt_has_all_fields():
    text = _text(build_messages("pathology", _IMG, ""))
    for field in ("DIAGNOSIS:", "TISSUE_TYPE:", "SEVERITY:", "CONFIDENCE:"):
        assert field in text


def test_ophthalmology_analyze_prompt_has_all_fields():
    text = _text(build_messages("ophthalmology", _IMG, ""))
    for field in ("FINDING:", "AFFECTED_STRUCTURE:", "SEVERITY:", "CONFIDENCE:"):
        assert field in text


def test_dentistry_analyze_prompt_has_all_fields():
    text = _text(build_messages("dentistry", _IMG, ""))
    for field in ("FINDING:", "AFFECTED_AREA:", "SEVERITY:", "CONFIDENCE:"):
        assert field in text


def test_query_prompt_has_answer_and_confidence():
    text = _text(build_messages("radiology", None, ""))
    assert "ANSWER:" in text
    assert "CONFIDENCE:" in text


def test_query_mode_no_image_in_content():
    assert len(_image_parts(build_messages("radiology", None, "What causes pneumonia?"))) == 0


def test_image_in_content_when_provided():
    msgs = build_messages("radiology", _IMG, "")
    parts = _image_parts(msgs)
    assert len(parts) == 1
    assert parts[0]["image_url"]["url"] == _IMG


def test_question_in_content():
    assert "Is there a fracture?" in _text(build_messages("radiology", _IMG, "Is there a fracture?"))


def test_analyze_uses_domain_specific_prompt():
    assert _text(build_messages("radiology", _IMG, "")) != _text(build_messages("dermatology", _IMG, ""))


def test_query_uses_domain_specific_prompt():
    assert _text(build_messages("radiology", None, "")) != _text(build_messages("ophthalmology", None, ""))


def test_dermatology_prompt_uses_new_severity_values():
    text = _text(build_messages("dermatology", _IMG, ""))
    assert "low|moderate|high" in text
    assert "mild" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL — current `build_messages` emits `type == "image"`, so `_image_parts` finds 0 and `test_image_in_content_when_provided` fails.

- [ ] **Step 3: Rewrite `build_messages`**

Replace the `build_messages` function at the bottom of `worker/prompts.py` (and update the import line at the top) with:

```python
def build_messages(domain: str, image_url: Optional[str], question: str) -> list[dict]:
    system = _ANALYZE[domain] if image_url is not None else _QUERY[domain]
    content = []
    if image_url is not None:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    content.append({"type": "text", "text": f"{system}\n\n{question}"})
    return [{"role": "user", "content": content}]
```

At the top of `worker/prompts.py`, delete the now-unused line `from PIL.Image import Image as PILImage`. Keep the existing `from typing import Optional` line (line 1) — `build_messages` still uses `Optional`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add worker/prompts.py tests/test_prompts.py
git commit -m "feat: emit OpenAI image_url messages from build_messages"
```

---

### Task 3: Rewrite run_inference to call vLLM over HTTP

**Files:**
- Modify: `worker/inference.py` (imports + `run_inference`; parsers untouched)
- Modify: `requirements-worker.txt` (add `httpx`)
- Test: `tests/test_inference.py` (rewrite `run_inference` tests; parser tests untouched)

**Interfaces:**
- Consumes: `build_messages(domain, image_url, question)` from Task 2; `settings.vllm_url`, `settings.vllm_model`, `settings.model_id`, `settings.max_output_tokens`, `settings.request_timeout_s` from Task 1.
- Produces: `run_inference(domain: str, image: Optional[PIL.Image.Image], question: str) -> dict` returning `{"raw": str, "structured": dict | None}` (shape unchanged). Module-level `_client: httpx.Client`. Helper `_image_to_data_url(image) -> str`.

- [ ] **Step 1: Install httpx and add to requirements**

Run: `pip install httpx==0.27.2`
Then add this line to `requirements-worker.txt` (in the alphabetical/existing grouping, e.g. after `filetype==1.2.0`):

```
httpx==0.27.2
```

- [ ] **Step 2: Rewrite the `run_inference` tests**

In `tests/test_inference.py`: (a) change the top imports, (b) replace `_fake_inference_setup` and the three `test_run_inference_*` functions with the block below. **Leave every `test_parse_*` function unchanged.**

Replace the top import lines (currently `import torch` … through the `from worker.inference import (...)` block) with:

```python
import httpx
import pytest
from PIL import Image
from unittest.mock import MagicMock, patch
from worker.inference import (
    parse_radiology, parse_dermatology,
    parse_pathology, parse_ophthalmology, parse_dentistry, parse_query,
    run_inference,
)
```

Replace `_fake_inference_setup` and the three `test_run_inference_*` tests with:

```python
def _fake_response(content: str):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def test_run_inference_returns_raw_and_structured():
    expected_raw = "FINDINGS: Test finding\nIMPRESSION: Test impression\nSEVERITY: mild\nCONFIDENCE: high\n"
    img = Image.new("RGB", (4, 4))
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)) as mock_post:
        result = run_inference("radiology", img, "")
    assert result["raw"] == expected_raw
    assert result["structured"]["findings"] == "Test finding"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 512
    content = payload["messages"][0]["content"]
    assert any(p["type"] == "image_url" for p in content)


def test_run_inference_structured_none_on_parse_failure():
    img = Image.new("RGB", (4, 4))
    with patch("worker.inference._client.post", return_value=_fake_response("Unstructured response")):
        result = run_inference("radiology", img, "")
    assert result["raw"] == "Unstructured response"
    assert result["structured"] is None


def test_run_inference_text_query_no_image():
    expected_raw = "ANSWER: Pneumonia causes consolidation.\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)) as mock_post:
        result = run_inference("radiology", None, "What does pneumonia look like?")
    assert result["raw"] == expected_raw
    assert result["structured"]["answer"] == "Pneumonia causes consolidation."
    assert result["structured"]["confidence"] == "high"
    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert all(p["type"] != "image_url" for p in content)


def test_run_inference_raises_on_http_error():
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    with patch("worker.inference._client.post", return_value=resp):
        with pytest.raises(httpx.HTTPStatusError):
            run_inference("radiology", Image.new("RGB", (4, 4)), "")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_inference.py -v`
Expected: FAIL — `worker.inference` has no `_client`; the patch target is missing.

- [ ] **Step 4: Rewrite `worker/inference.py` imports + `run_inference`**

Replace the top import block (currently lines 1–9, ending at `log = structlog.get_logger()`) with:

```python
import base64
import io
import httpx
import structlog
from typing import Optional
from PIL import Image
from config import settings
from worker.prompts import build_messages

log = structlog.get_logger()

_client = httpx.Client(timeout=settings.request_timeout_s)
```

**Leave all `_RE` regexes, every `parse_*` function, and `_ANALYZE_PARSERS` exactly as they are.**

Replace the `run_inference` function at the bottom of the file with:

```python
def _image_to_data_url(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def run_inference(domain: str, image: Optional[Image.Image], question: str) -> dict:
    image_url = _image_to_data_url(image) if image is not None else None
    messages = build_messages(domain, image_url, question)
    payload = {
        "model": settings.vllm_model or settings.model_id,
        "messages": messages,
        "temperature": 0,
        "max_tokens": settings.max_output_tokens,
    }
    resp = _client.post(f"{settings.vllm_url}/chat/completions", json=payload)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parser = parse_query if image is None else _ANALYZE_PARSERS.get(domain)
    return {"raw": raw, "structured": parser(raw) if parser else None}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_inference.py -v`
Expected: PASS (all parser tests + the four run_inference tests)

- [ ] **Step 6: Commit**

```bash
git add worker/inference.py tests/test_inference.py requirements-worker.txt
git commit -m "feat: run inference via vLLM OpenAI HTTP endpoint"
```

---

### Task 4: Remove in-process model loader; add vLLM health-wait to worker startup

**Files:**
- Delete: `worker/model.py`
- Modify: `worker/start.py`
- Test: `tests/test_start.py` (create)

**Interfaces:**
- Consumes: `settings.vllm_url` from Task 1.
- Produces: `wait_for_vllm(base_url: str, retries: int = 60, delay: float = 5.0) -> None` in `worker/start.py`. Returns when vLLM `/health` returns 200; raises `RuntimeError` after exhausting retries. The worker bootstrap (health-wait + `SimpleWorker(...).work()`) runs only under `if __name__ == "__main__":`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_start.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from worker.start import wait_for_vllm


def test_wait_for_vllm_returns_when_healthy():
    ok = MagicMock()
    ok.status_code = 200
    with patch("worker.start.httpx.get", return_value=ok) as mock_get:
        wait_for_vllm("http://vllm:8001/v1", retries=3, delay=0.0)
    called_url = mock_get.call_args.args[0]
    assert called_url == "http://vllm:8001/health"


def test_wait_for_vllm_raises_after_retries():
    with patch("worker.start.httpx.get", side_effect=Exception("boom")), \
         patch("worker.start.time.sleep"):
        with pytest.raises(RuntimeError):
            wait_for_vllm("http://vllm:8001/v1", retries=2, delay=0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_start.py -v`
Expected: FAIL — importing `wait_for_vllm` fails (current `start.py` runs `get_model()` at import and has no such function).

- [ ] **Step 3: Rewrite `worker/start.py`**

Replace the entire contents of `worker/start.py` with:

```python
import time
import httpx
import structlog
from rq import Queue
from rq.worker import SimpleWorker
from config import make_redis, settings

log = structlog.get_logger()


def wait_for_vllm(base_url: str, retries: int = 60, delay: float = 5.0) -> None:
    """Block until the vLLM server's /health returns 200, or raise after retries."""
    health_url = base_url.rsplit("/v1", 1)[0] + "/health"
    for attempt in range(retries):
        try:
            resp = httpx.get(health_url, timeout=5.0)
            if resp.status_code == 200:
                log.info("vllm_ready", url=health_url)
                return
        except Exception:
            pass
        log.info("vllm_waiting", url=health_url, attempt=attempt + 1)
        time.sleep(delay)
    raise RuntimeError(f"vLLM not ready after {retries} attempts at {health_url}")


if __name__ == "__main__":
    wait_for_vllm(settings.vllm_url)
    conn = make_redis(decode_responses=False)
    q = Queue("troke-jobs", connection=conn)
    log.info("worker_starting", queue="troke-jobs")
    SimpleWorker([q], connection=conn).work()
```

- [ ] **Step 4: Delete the obsolete model loader**

Run: `git rm worker/model.py`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_start.py -v && python -c "import worker.start"`
Expected: both tests PASS; the import runs without launching a worker (no network, no model load).

- [ ] **Step 6: Commit**

```bash
git add worker/start.py tests/test_start.py
git commit -m "feat: wait for vLLM health on worker start; drop in-process model"
```

---

### Task 5: Slim the worker image (no CUDA/torch)

**Files:**
- Modify: `requirements-worker.txt` (remove ML libs)
- Modify: `Dockerfile.worker`

**Interfaces:** none (build/runtime change only).

- [ ] **Step 1: Trim `requirements-worker.txt`**

Remove these three lines (the worker no longer loads a model):

```
transformers>=4.50.0
accelerate>=0.34.2
peft>=0.12.0
```

Keep the rest (including `httpx==0.27.2` added in Task 3). Final file:

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-multipart==0.0.9
pydantic-settings==2.4.0
redis==5.0.8
rq==1.16.2
structlog==24.4.0
filetype==1.2.0
Pillow==10.4.0
httpx==0.27.2
```

- [ ] **Step 2: Rebase `Dockerfile.worker` on a slim Python image**

Replace the entire contents of `Dockerfile.worker` with:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY worker/ worker/
COPY config.py .
```

- [ ] **Step 3: Verify the worker imports with the slim dependency set**

Run: `python -c "import worker.inference, worker.start, worker.worker"`
Expected: no error (no `torch`/`transformers` import anywhere in the worker path).

Run: `pytest tests/test_inference.py tests/test_prompts.py tests/test_start.py -v`
Expected: PASS (regression check).

- [ ] **Step 4: Commit**

```bash
git add requirements-worker.txt Dockerfile.worker
git commit -m "chore: slim worker image, drop torch/transformers/peft"
```

---

### Task 6: Add the vLLM service to docker-compose; rewire the worker

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:** none (orchestration change). GPU reservation moves from `worker` to `vllm`.

- [ ] **Step 1: Add the `vllm` service and rewire `worker`**

In `docker-compose.yml`, add a new `vllm` service under `services:` and replace the existing `worker` service. The new/changed blocks:

```yaml
  vllm:
    image: vllm/vllm-openai:latest   # PIN to a tag with Gemma-3 multimodal support before first run (see Risks)
    command: >
      --model ${MODEL_ID:-google/medgemma-4b-it}
      --served-model-name ${MODEL_ID:-google/medgemma-4b-it}
      --port 8001
      --gpu-memory-utilization 0.9
      --max-model-len ${MAX_MODEL_LEN:-4096}
      --quantization ${QUANTIZATION:-fp8}
    env_file: .env
    environment:
      HUGGING_FACE_HUB_TOKEN: ${HF_TOKEN}
    ports:
      - "8001:8001"
    volumes:
      - hf_cache:/root/.cache/huggingface
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/health').status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 20
      start_period: 600s
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    command: python -m worker.start
    env_file: .env
    environment:
      REDIS_URL: redis://redis:6379
      VLLM_URL: http://vllm:8001/v1
    depends_on:
      redis:
        condition: service_started
      vllm:
        condition: service_healthy
    restart: unless-stopped
    volumes:
      - temp_data:/tmp/troke
    deploy:
      replicas: 4
```

Notes: the `worker` service **loses** its GPU `deploy.resources` block and its `hf_cache` volume (it no longer loads a model). The `volumes:` section at the bottom (`redis_data`, `temp_data`, `hf_cache`) stays as-is.

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (YAML parses, interpolation resolves; requires a `.env` with the Task 1 vars — `cp .env.example .env` first if needed).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add vLLM GPU service; worker scales as GPU-free replicas"
```

---

### Task 7: Update docs (README, CLAUDE.md, quickstart, api.md)

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/quickstart.md`, `docs/api.md`

**Interfaces:** none.

- [ ] **Step 1: Update `README.md`**

In the "How It Works" section, replace the line `Jobs are processed asynchronously by a separate worker process that owns the GPU. The API server never loads the model.` with:

```
Jobs are processed asynchronously: stateless worker replicas pull jobs and call a
dedicated vLLM server that owns the GPU and continuously batches requests. Neither
the API nor the workers load the model. Set QUANTIZATION=fp8 to fit on an 8GB GPU;
leave it empty for bf16 (full-accuracy, cloud).
```

- [ ] **Step 2: Update `CLAUDE.md`**

Replace the "Architecture" diagram block with:

```
Client → FastAPI (app/) → Redis queue → Worker replicas (HTTP client) → vLLM server (GPU) → MedGemma
                       ↑ poll status ↑
```

Under "Architecture" bullets, replace the `worker/` bullet with:

```
- **`worker/`** — Stateless HTTP client of vLLM. No GPU, no model. Pulls jobs, builds the
  OpenAI chat payload (`prompts.py`), calls vLLM (`inference.py`), parses the structured text.
  Run several replicas to feed vLLM's continuous batcher.
- **`vllm`** — Owns the GPU. `vllm/vllm-openai` serving MedGemma; FP8 locally, bf16 in cloud.
```

In "Commands", replace the "Start worker" / model lines with:

```bash
# Start vLLM server (owns the GPU)
vllm serve google/medgemma-4b-it --quantization fp8 --max-model-len 4096 \
  --gpu-memory-utilization 0.9 --port 8001

# Start one or more workers (HTTP clients; no GPU)
python -m worker.start
```

In "Testing", replace the `Mock get_model at worker.inference.get_model` line with:

```
- Mock the vLLM HTTP call at `worker.inference._client.post` — never hit a real server in tests
```

- [ ] **Step 3: Update `docs/quickstart.md`**

Replace any "start the worker" / model-download instructions with the Docker path:

```bash
cp .env.example .env        # set ADMIN_KEY and HF_TOKEN; QUANTIZATION=fp8 for an 8GB GPU
docker compose up --build   # starts redis, api, vllm (GPU), and 4 worker replicas
```

And the non-Docker path (run each in its own terminal): `redis-server`; the `vllm serve ...` command from Step 2; `uvicorn app.main:app --port 8000`; one or more `python -m worker.start`.

- [ ] **Step 4: Update `docs/api.md`**

The public endpoint surface is unchanged. Add one sentence where the processing pipeline is described: "Inference is served by a vLLM engine behind the workers; responses are unchanged."

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/quickstart.md docs/api.md
git commit -m "docs: describe vLLM serving architecture and run steps"
```

---

## Final regression check (run after all tasks)

Run: `pytest tests/ -v`
Expected: PASS. (`app/` route tests are untouched and still mock `Queue`; the job contract is intact.)

## Manual verification (requires the GPU — cannot be automated in CI)

These confirm the runtime behavior the unit tests mock out:

1. `cp .env.example .env`; set `ADMIN_KEY` and `HF_TOKEN` (MedGemma is gated — the token must have accepted the license).
2. `docker compose up --build` — watch the `vllm` service reach `healthy`; first boot downloads weights (slow). On the 8 GB 4060, confirm it loads under FP8 without OOM. If OOM: lower `--max-num-seqs`, reduce `MAX_MODEL_LEN`, or add `--enforce-eager`.
3. Create a key: `curl -X POST localhost:8000/v1/admin/keys -H "X-API-Key: $ADMIN_KEY"`.
4. Submit an analyze job and a query job; poll `/v1/jobs/{id}` until `completed`; confirm `structured` is populated and `raw` looks right.
5. Throughput smoke test: submit ~10 jobs rapidly; confirm they complete concurrently (vLLM batches them) rather than strictly serially.

## Risks / open items (from the spec)

- **vLLM image/version pin:** `vllm/vllm-openai:latest` is a starting point — pin a tag verified to serve MedGemma-4B (Gemma-3 multimodal) with `image_url` inputs. This is the #1 thing to confirm at Step 2 of the manual verification.
- **8 GB headroom** with vision prefill is tight; `--max-num-seqs` / `--enforce-eager` are the tuning levers.
- **FP8 + LoRA** interaction in vLLM is unverified; if an `ADAPTER_PATH` is used locally, validate, or keep adapters on the bf16 cloud path.
