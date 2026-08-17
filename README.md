# troke

A B2B REST API for medical analysis, powered by [Google MedGemma](https://huggingface.co/google/medgemma-4b-it).

Submit an image/query/image+query, get back structured clinical findings. Designed to be embedded into health apps, clinic workflows, or any product that needs medical image inference without running their own model.

## Supported Domains

Each domain supports two endpoints: `/analyze` (image + optional question) and `/query` (text only).

| Domain | Analyze output | Query output |
|---|---|---|
| Radiology | findings, impression, severity, confidence | answer, confidence |
| Dermatology | condition, severity, recommendation, confidence | answer, confidence |
| Pathology | diagnosis, tissue_type, severity, confidence | answer, confidence |
| Ophthalmology | finding, affected_structure, severity, confidence | answer, confidence |
| Dentistry | finding, affected_area, severity, confidence | answer, confidence |
| General | findings, impression, confidence | answer, confidence |
| Orthopedics | finding, affected_bone, severity, confidence | answer, confidence |
| Pulmonology | finding, affected_region, severity, confidence | answer, confidence |
| Neurology | finding, affected_region, severity, confidence | answer, confidence |
| Gastroenterology | finding, location, severity, confidence | answer, confidence |
| Cardiology | finding, affected_structure, severity, confidence | answer, confidence |
| Hematology | finding, cell_line, severity, confidence | answer, confidence |
| Rheumatology | finding, affected_joint, severity, confidence | answer, confidence |
| Oncology | finding, severity, recommendation, confidence | answer, confidence |
| Endocrinology | finding, affected_gland, severity, confidence | answer, confidence |
| Nephrology | finding, affected_structure, severity, confidence | answer, confidence |
| Urology | finding, affected_structure, severity, confidence | answer, confidence |
| Gynecology | finding, affected_structure, severity, confidence | answer, confidence |
| Pediatrics | finding, severity, recommendation, confidence | answer, confidence |
| Otolaryngology | finding, affected_area, severity, confidence | answer, confidence |
| Emergency | finding, severity, recommendation, confidence | answer, confidence |

Replies render as rich, sectioned **Markdown** (ChatGPT-style) in the chat; the legacy
structured fields above are still parsed when the model emits them, otherwise `structured`
is `null` and the Markdown answer is authoritative.

`general` is a domain-agnostic catch-all (any medical image, no specialty needed). It's the default in the built-in chat page, where a **department dropdown** lets the user target any specialty per message — see [Share via chat](#share-via-chat).

## How It Works

```
Client → POST image + question  →  /v1/{domain}/analyze  →  job_id
Client → POST text question     →  /v1/{domain}/query    →  job_id
Client → GET /v1/jobs/{job_id}  →  poll until completed
```

Jobs are processed asynchronously: stateless worker replicas pull jobs and call a
dedicated vLLM server that owns the GPU and continuously batches requests. Neither
the API nor the workers load the model. Run several workers (`WORKER_REPLICAS=N`
natively, or Compose `replicas`) to keep that batcher fed — vLLM stays a single
process. Set QUANTIZATION=fp8 to fit on an 8GB GPU; leave it empty for bf16
(full-accuracy, cloud).

## Quickstart

See [docs/quickstart.md](docs/quickstart.md). For the full API reference, see [docs/api.md](docs/api.md).

**Short version:**
```bash
cp .env.example .env   # set ADMIN_KEY
docker compose up --build
```

Then create an API key:
```bash
curl -X POST http://localhost:8000/v1/admin/keys \
  -H "X-API-Key: <your-admin-key>"
```

Interactive API docs at `http://localhost:8000/docs`.

## Share via chat

A built-in chat page at `http://localhost:8000/chat` lets a non-technical person use
the service with no job IDs and **no API key** — messages and image uploads run through
a chosen department (a **dropdown**, default `general`), and the page's async submit/poll
loop is hidden. Answers **stream token-by-token** (Server-Sent Events; first token
typically < 1 s on a direct/local connection) so there's no long blank wait, with automatic
fallback to polling if the stream drops. Note: Cloudflare **quick tunnels**
(`trycloudflare.com`) buffer SSE and deliver the whole answer at the end — over such a
tunnel the live typing effect is lost, but a **live elapsed-time counter** shows progress
so it never looks frozen. Use a non-buffering tunnel (ngrok, localtunnel) or a Cloudflare
named tunnel for true remote streaming. A **top status bar** shows model readiness (with a cold-start warmup progress
bar), and a **⚡ Stats** panel reports response speed (tokens/sec, latency). Image uploads
accept **JPEG, PNG, or DICOM (`.dcm`)** — DICOM is windowed and transcoded to PNG
server-side. The chat **remembers the conversation** (server-side, ~30-minute sliding TTL)
so follow-ups like "is that serious?" have context; the **New chat** button starts a fresh
thread. Tune the bounds with the optional `CHAT_MEMORY_CHAR_BUDGET` / `CHAT_MEMORY_MAX_TURNS`
/ `CHAT_MEMORY_TTL_SECONDS` env vars. To enable it:

1. Mint a shared key and set it as `CHAT_API_KEY` in `.env`, then restart the API. The
   server attaches this key to `/chat/api/*` requests, so it never reaches the browser.
   With `CHAT_API_KEY` empty, the chat proxy stays disabled (returns `503`).
2. Expose the server over a temporary public URL with Cloudflare Tunnel:
   ```bash
   # one-time install (amd64 Linux)
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
     -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
   # then, with the stack running on :8000
   bash scripts/expose.sh
   ```
   Share the printed `https://<random>.trycloudflare.com/chat` URL.

> The tunnel URL is the only thing gating access — treat it like a password, and note
> it also exposes `/v1/admin/keys` (gated by `ADMIN_KEY`, so keep that strong). Research
> demo only; don't send real patient data over an ephemeral tunnel.

## Adding a Domain

1. Add the domain to the `DOMAINS` list in `app/domains.py` — the single source of truth.
   `app/main.py` registers `/analyze` + `/query` from it and `app/routes/chat.py` builds
   the chat department dropdown from it, so they can't drift.
2. One line in the `_SPECIALIST` map in `worker/prompts.py` (specialist voice + image type)
3. (Optional) a regex parser in `worker/inference.py` — replies are rich Markdown by
   default, so `structured` is usually `null` and the parser is not required.
