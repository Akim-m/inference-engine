#!/usr/bin/env bash
set -euo pipefail
#
# Expose the local troke API (and the /chat page) over a temporary public URL
# via Cloudflare Tunnel, so someone off your network can use it.
#
# Prerequisites:
#   - The full stack is running on :8000 (Redis + vLLM + workers + API).
#   - CHAT_API_KEY is set in .env, so the /chat proxy is enabled.
#   - cloudflared is installed (see README "Share with a friend").
#
# Usage:  bash scripts/expose.sh
# It prints a https://<random>.trycloudflare.com URL. Share <that-url>/chat.
# The URL is ephemeral — it changes every run. Ctrl-C to stop.

PORT="${TROKE_PORT:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install it (amd64 Linux):" >&2
  echo "  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \\" >&2
  echo "    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared" >&2
  exit 1
fi

echo "Exposing http://localhost:${PORT} — share the printed URL with /chat appended."
exec cloudflared tunnel --url "http://localhost:${PORT}"
