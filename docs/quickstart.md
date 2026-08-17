## Step 1 — Create your .env file

```bash
cp .env.example .env        # set ADMIN_KEY and HF_TOKEN; QUANTIZATION=fp8 for an 8GB GPU
```

Edit `.env` and set two values:
- `ADMIN_KEY` — the key you'll use to create API keys.
- `HF_TOKEN` — a Hugging Face access token. MedGemma is a gated model, so the token must belong to an account that has accepted the model license.

```
ADMIN_KEY=mysecretadminkey123
HF_TOKEN=hf_yourtokenhere
```

---

## Step 2 — Start the stack

**Docker (recommended):**

```bash
docker compose up --build   # starts redis, api, vllm (GPU), and 4 worker replicas
```

The vLLM service will take 1-2 minutes on first run while MedGemma downloads. Wait until it is healthy before submitting jobs.

**Without Docker** (run each in its own terminal):

```bash
redis-server
```

```bash
# Flags tuned for an 8GB GPU. On a bare `pip install vllm` (no CUDA toolkit on PATH),
# FlashInfer can't JIT-compile its kernels, so use the native sampler + FlashAttention.
VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN \
vllm serve google/medgemma-4b-it --quantization fp8 \
  --max-model-len 2048 --gpu-memory-utilization 0.85 --max-num-seqs 4 \
  --no-enable-prefix-caching --limit-mm-per-prompt '{"image": 1}' \
  --enforce-eager --port 8001
```

```bash
uvicorn app.main:app --port 8000
```

```bash
python -m worker.start
```

---

## Step 3 — Create an API key

```bash
curl -X POST http://localhost:8000/v1/admin/keys \
  -H "X-API-Key: mysecretadminkey123"
```

Response:
```json
{"key": "a3f9e2b1c4d5..."}
```

**Save that key** — it's shown only once.

---

## Step 4 — Submit your first job

```bash
curl -X POST http://localhost:8000/v1/radiology/analyze \
  -H "X-API-Key: <your-key-here>" \
  -F "image=@/path/to/your/xray.jpg" \
  -F "question=What abnormalities do you see?"
```

Response:
```json
{"job_id": "abc-123-..."}
```

---

## Step 5 — Poll for the result

```bash
curl http://localhost:8000/v1/jobs/abc-123-... \
  -H "X-API-Key: <your-key-here>"
```

Poll every few seconds until `status` becomes `completed`:
```json
{
  "status": "completed",
  "result": {
    "raw": "FINDINGS: ...\nIMPRESSION: ...",
    "structured": {
      "findings": "...",
      "impression": "...",
      "severity": "moderate",
      "confidence": "high"
    }
  }
}
```
