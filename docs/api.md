# Troke API — Developer Guide

Troke is a medical inference API. Submit an image for visual analysis, or a text question for clinical Q&A — get back a job ID, then poll for the result. All inference runs asynchronously.

---

There are two ways to submit a job:
- **`/analyze`** — send an image (plus an optional question). Returns structured clinical findings.
- **`/query`** — send a text question with no image. Returns a direct medical answer.

Both use the same async pattern: submit → get job ID → poll for result.

Jobs are processed by a dedicated AI worker. The API never blocks waiting for inference. Inference is served by a vLLM engine behind the workers; responses are unchanged.

**Typical latency:** 30–90 seconds.

> **Clinical use disclaimer:** troke is a clinical decision support tool, not a diagnostic system. All output is preliminary pre-screening intended for review by a qualified healthcare professional. Results must not be used as the sole basis for any clinical decision. AI systems can produce errors, and no troke output should be acted upon without clinician oversight. troke is not a certified medical device.

---

## Base URL

```
http://<host>:8000/v1
```

---

## Authentication

Every request requires an API key in the header:

```
X-API-Key: <your-key>
```

Keys are provisioned by your Troke administrator. Without a valid key, all requests return `401`.

### Rate limits

- **60 submit requests/minute** per key — `/analyze` and `/query`
- **600 status-poll requests/minute** per key — `GET /jobs/{id}`, a separate and
  generous budget so polling your jobs never exhausts your submit budget
- **10 concurrent pending jobs** per key

Exceeding any limit returns `429`.

---

## Endpoints

### Submit a Radiology Analysis

```
POST /v1/radiology/analyze
```

Analyzes a chest X-ray or other radiology image.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | file | Yes | JPEG, PNG, or DICOM (`.dcm`). Max 10MB. DICOM is transcoded to PNG server-side. |
| `question` | string | No | Specific question about the image. Max 500 chars. If omitted, returns a general analysis. |

**Response** — `202 Accepted`

```json
{ "job_id": "3f2a1b4c-..." }
```

**Example**

```bash
curl -X POST http://localhost:8000/v1/radiology/analyze \
  -H "X-API-Key: $API_KEY" \
  -F "image=@chest_xray.jpg" \
  -F "question=Is there evidence of pneumonia?"
```

---

### Submit a Dermatology Analysis

```
POST /v1/dermatology/analyze
```

Analyzes a skin lesion or dermatology image. Same request/response shape as radiology.

---

### Submit a Pathology Analysis

```
POST /v1/pathology/analyze
```

Analyzes a histology or pathology slide image.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | file | Yes | JPEG, PNG, or DICOM (`.dcm`). Max 10MB. DICOM is transcoded to PNG server-side. |
| `question` | string | No | Specific question. Max 500 chars. |

**Response** — `202 Accepted`

```json
{ "job_id": "c3d8e2f1-..." }
```

---

### Submit an Ophthalmology Analysis

```
POST /v1/ophthalmology/analyze
```

Analyzes a fundus, OCT, or other ocular image. Same request/response shape as radiology.

---

### Submit a Dentistry Analysis

```
POST /v1/dentistry/analyze
```

Analyzes a dental X-ray or intraoral image. Same request/response shape as radiology.

---

### Submit a General Analysis

```
POST /v1/general/analyze
```

Domain-agnostic catch-all — analyzes any medical image (radiograph, skin photo,
histology slide, fundus, dental, etc.) without choosing a specialty. Same
request/response shape as radiology. This is the domain used by the built-in chat page.

### Submit an Orthopedics Analysis

```
POST /v1/orthopedics/analyze
```

Analyzes a musculoskeletal image (bone X-ray, etc.). Same request/response shape as radiology.

### Submit a Pulmonology Analysis

```
POST /v1/pulmonology/analyze
```

Analyzes a chest image (chest X-ray or CT). Same request/response shape as radiology.

### Submit a Neurology Analysis

```
POST /v1/neurology/analyze
```

Analyzes a neurological image (brain CT or MRI). Same request/response shape as radiology.

### Submit a Gastroenterology Analysis

```
POST /v1/gastroenterology/analyze
```

Analyzes an endoscopic or gastrointestinal image. Same request/response shape as radiology.

### Submit a Cardiology Analysis

```
POST /v1/cardiology/analyze
```

Analyzes a cardiac image (chest X-ray, echocardiogram, or angiogram). Structured result:
`finding`, `affected_structure`, `severity`, `confidence`.

### Submit a Hematology Analysis

```
POST /v1/hematology/analyze
```

Analyzes a peripheral blood smear or bone marrow image. Structured result:
`finding`, `cell_line`, `severity`, `confidence`.

### Submit a Rheumatology Analysis

```
POST /v1/rheumatology/analyze
```

Analyzes a musculoskeletal image (e.g. joint X-ray). Structured result:
`finding`, `affected_joint`, `severity`, `confidence`.

### Submit an Analysis in the Additional Specialties

```
POST /v1/oncology/analyze
POST /v1/endocrinology/analyze
POST /v1/nephrology/analyze
POST /v1/urology/analyze
POST /v1/gynecology/analyze
POST /v1/pediatrics/analyze
POST /v1/otolaryngology/analyze
POST /v1/emergency/analyze
```

Each accepts the same `multipart/form-data` request and returns the same job shape as
radiology. The specialist voice and expected image type differ per domain (e.g. oncology
→ a staging CT/PET-CT/MRI of a tumor; endocrinology → a thyroid ultrasound or gland scan;
otolaryngology → an otoscopic/laryngoscopic/sinus-CT view; emergency → a trauma
radiograph, CT, or point-of-care ultrasound). Replies are rich Markdown, so `structured`
is typically `null`.

---

### Submit a Text Query

```
POST /v1/{domain}/query
```

Ask a clinical question without an image. Works for all domains: `radiology`, `dermatology`, `pathology`, `ophthalmology`, `dentistry`, `general`, `orthopedics`, `pulmonology`, `neurology`, `gastroenterology`, `cardiology`, `hematology`, `rheumatology`, `oncology`, `endocrinology`, `nephrology`, `urology`, `gynecology`, `pediatrics`, `otolaryngology`, `emergency`.

**Request** — `application/json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | Clinical question. 1–500 chars. |

**Response** — `202 Accepted`

```json
{ "job_id": "7a1b2c3d-..." }
```

**Example**

```bash
curl -X POST http://localhost:8000/v1/radiology/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the radiological signs of a tension pneumothorax?"}'
```

---

### Poll Job Status

```
GET /v1/jobs/{job_id}
```

Returns the current status and, when complete, the full result.

**Response**

| `status` | Meaning |
|----------|---------|
| `pending` | Queued, not yet picked up |
| `processing` | Actively running |
| `completed` | Done — `result` is populated |
| `failed` | Inference failed — `error` is populated |

**Completed response**

```json
{
  "status": "completed",
  "result": {
    "raw": "FINDINGS: ...\nIMPRESSION: ...\nSEVERITY: moderate\nCONFIDENCE: high\n\n<detailed explanation>",
    "structured": {
      "findings": "Right-sided pneumothorax with subcutaneous emphysema.",
      "impression": "Right-sided pneumothorax with subcutaneous emphysema.",
      "severity": "moderate",
      "confidence": "high"
    },
    "stats": {
      "completion_tokens": 865,
      "inference_ms": 80627,
      "tokens_per_second": 10.7
    }
  },
  "error": null
}
```

`stats` reports the model's own token count and speed for the response (`null` fields if
vLLM didn't return usage). The `/chat` UI surfaces it in the **⚡ Stats** panel.

**Failed response**

```json
{
  "status": "failed",
  "result": null,
  "error": "inference_failed"
}
```

> Results are available for **1 hour** after completion. After that, the job ID returns 404.

---

## Result Structure

### Radiology

`structured` fields when analysis succeeds:

| Field | Type | Values |
|-------|------|--------|
| `findings` | string | Observed abnormalities |
| `impression` | string | Clinical interpretation |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Dermatology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `condition` | string | Most likely diagnosis |
| `severity` | string | Typically `mild` · `moderate` · `severe` |
| `recommendation` | string | Suggested next step |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Pathology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `diagnosis` | string | Histopathological diagnosis |
| `tissue_type` | string | Tissue type |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Ophthalmology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary finding |
| `affected_structure` | string | Affected ocular structure |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Dentistry (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary dental finding |
| `affected_area` | string | Affected tooth or oral region |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### General (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `findings` | string | Key observations |
| `impression` | string | Overall clinical interpretation |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Orthopedics (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary musculoskeletal finding |
| `affected_bone` | string | Affected bone or joint |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Pulmonology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary pulmonary finding |
| `affected_region` | string | Affected lung region |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Neurology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary neurological finding |
| `affected_region` | string | Affected brain region |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Gastroenterology (`/analyze`)

| Field | Type | Values |
|-------|------|--------|
| `finding` | string | Primary gastrointestinal finding |
| `location` | string | Anatomical location in the GI tract |
| `severity` | string | Typically `normal` · `mild` · `moderate` · `severe` |
| `confidence` | string | Typically `low` · `medium` · `high` |

### Text Query (`/query`, all domains)

| Field | Type | Values |
|-------|------|--------|
| `answer` | string | Direct answer to the question |
| `confidence` | string | `low` · `medium` · `high` |

`structured` may be `null` if the model output couldn't be parsed — in that case, `raw` still contains the full text response.

---

## Error Responses

All errors follow the same shape:

```json
{ "error": "short_code", "message": "Human-readable description" }
```

| HTTP | `error` | Cause |
|------|---------|-------|
| 401 | `invalid_key` | Missing or invalid API key |
| 404 | `job_not_found` | Job doesn't exist, expired, or belongs to another key |
| 422 | `invalid_file` | File exceeds 10MB, or not a valid image |
| 429 | `rate_limited` | Over the submit (60/min) or poll (600/min) budget |
| 429 | `queue_full` | Over 10 pending jobs for this key |

---

## Polling Pattern

Poll every 5–10 seconds until `status` is `completed` or `failed`. Jobs typically finish in under 90 seconds.

```python
import time, httpx

def analyze(api_key: str, image_path: str, domain: str = "radiology") -> dict:
    headers = {"X-API-Key": api_key}

    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"http://localhost:8000/v1/{domain}/analyze",
            headers=headers,
            files={"image": f},
            data={"question": "What is the primary finding?"},
        )
    resp.raise_for_status()
    job_id = resp.json()["job_id"]

    for _ in range(24):  # max ~2 min
        time.sleep(5)
        result = httpx.get(
            f"http://localhost:8000/v1/jobs/{job_id}",
            headers=headers,
        ).json()

        if result["status"] == "completed":
            return result["result"]
        if result["status"] == "failed":
            raise RuntimeError("Analysis failed")

    raise TimeoutError("Job did not complete in time")
```

---

## Chat UI

A ready-made chat page is served at:

```
GET /chat
```

It's a single self-contained page for non-technical users: type a question or attach an
image, pick a department, get an answer — no job IDs and **no API key entered in the
browser**. It calls server-side proxy routes that attach a shared key (`CHAT_API_KEY`)
and forward to the selected department (default `general`):

- `POST /chat/api/analyze` — `multipart/form-data` (`image` + optional `question`, `conversation_id`, `domain`). Accepts JPEG, PNG, **or DICOM (`.dcm`)** — DICOM is transcoded to PNG server-side.
- `POST /chat/api/query` — JSON `{ "question": "...", "conversation_id": "...", "domain": "..." }` (all but `question` optional)
- `GET /chat/api/jobs/{job_id}` — same status/result shape as `/v1/jobs/{job_id}`
- `GET /chat/api/domains` — `{ "domains": [...] }`, the department list for the dropdown
- `GET /chat/api/status` — `{ "model_ready": bool, "detail": "..." }`, drives the top status bar / warmup progress
- `GET /chat/api/stream/{job_id}` — **Server-Sent Events** of the answer's live token stream: `data:` frames of `{"t":"delta","text":"…"}` followed by `{"t":"done","stats":{…}}` (or `{"t":"error"}`). The page renders these live and falls back to job polling if the stream drops.

**Live streaming.** Answers stream token-by-token over SSE (first token typically < 1 s), so the UI shows text as it generates instead of waiting for the full response. (Cloudflare *quick* tunnels buffer SSE and deliver at the end; the chat shows a live elapsed-time counter in that case. Use a non-buffering tunnel for true remote streaming.)

**Response speed.** Completed results include a `stats` object (`completion_tokens`, `inference_ms`, `tokens_per_second`) surfaced in the chat's **⚡ Stats** panel.

**DICOM.** Upload a `.dcm` and the server applies the VOI/windowing LUT and renders it to PNG before inference. Non-image DICOMs (structured reports, RT plans, ECG waveforms) return `422 invalid_file`.

These are not part of the per-key public API — they use the server-configured shared key.
If `CHAT_API_KEY` is unset, the submit/poll routes return `503 chat_disabled`. See the
README's "Share via chat" for enabling it and exposing it over a tunnel.

**Department selector.** `domain` picks the specialty per message (validated against the
registered domains; unknown/absent → `general`, never an error). Conversation memory is
domain-agnostic, so switching department mid-thread just changes the next message's
specialty.

**Conversation memory.** When `conversation_id` is a valid UUID, the chat surface keeps
bounded server-side memory for that thread: prior turns are stored in Redis and threaded
into the model so follow-ups have context. The history is capped by a character budget
(~8000 chars) with a sliding 30-minute TTL; an invalid or absent `conversation_id` is
silently treated as a stateless single-shot (never an error). Image bytes are never
stored — an image turn is remembered only as a `[shared a medical image] <question>`
placeholder. The authed `/v1/<domain>/analyze` and `/query` endpoints remain stateless
single-shot; they accept but never forward a `conversation_id`.

---

## Admin: Key Management

These endpoints require the admin key, not a regular API key.

### Create a key

```
POST /v1/admin/keys
X-API-Key: <admin-key>
```

```json
{ "key": "a3f1..." }
```

Store this key securely — it is only returned once.

### Revoke a key

```
DELETE /v1/admin/keys/{key}
X-API-Key: <admin-key>
```

Returns `200` on success, `404` if the key doesn't exist.
