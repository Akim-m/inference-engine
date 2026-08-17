#!/usr/bin/env python3
"""Standalone, READ-ONLY live monitoring dashboard for the troke /chat service.

Separate process on its own port (8092), bound to 127.0.0.1 only. It only READS
Redis (scan_iter + LRANGE + TTL) — it never writes Redis, never imports the app,
and never touches the main stack (vLLM, FastAPI, worker, cloudflared).

Conversation memory lives in Redis at keys `chat:conv:<uuid>`, each a LIST of
JSON strings {"role": "user"|"assistant", "text": "..."} in chronological order.
Each key has a TTL that refreshes on every turn, so TTL descending == most
recently active first.

Run:
    /home/akim/Coding/troke/.venv/bin/python /home/akim/Coding/troke/scripts/monitor.py
"""
import datetime
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import redis

# Bound to 0.0.0.0 so WSL2 forwards Windows localhost:8092 to it (127.0.0.1 is not
# forwarded). Because 0.0.0.0 exposes the page on the LAN and it serves private medical
# conversations, EVERY request is gated behind a secret token (?t=<token>, then a
# cookie; constant-time compare). Set MONITOR_TOKEN to pin the token; otherwise a fresh
# one is generated each start and printed in the startup line / logs/monitor.log.
HOST = "0.0.0.0"
PORT = 8092
CONV_PREFIX = "chat:conv:"
TOKEN = os.environ.get("MONITOR_TOKEN") or secrets.token_urlsafe(18)

# One shared client. decode_responses so we get str back. This is a READ-ONLY
# consumer — the only Redis commands issued are SCAN, LRANGE and TTL.
_r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


def collect_feed():
    """Return the feed payload: conversations sorted by TTL descending."""
    conversations = []
    for key in _r.scan_iter(match=f"{CONV_PREFIX}*", count=100):
        conv_id = key[len(CONV_PREFIX):]
        try:
            raw_entries = _r.lrange(key, 0, -1)
            ttl = _r.ttl(key)
        except redis.RedisError:
            continue
        turns = []
        for entry in raw_entries:
            try:
                obj = json.loads(entry)
            except (ValueError, TypeError):
                continue
            role = obj.get("role", "")
            text = obj.get("text", "")
            if not isinstance(text, str):
                text = str(text)
            turns.append({"role": role, "text": text})
        conversations.append({
            "id": conv_id[:8],
            "ttl": ttl if isinstance(ttl, int) else -1,
            "turns": turns,
        })
    # Most recently active (highest TTL) first. TTL of -1/-2 sorts to the bottom.
    conversations.sort(key=lambda c: c["ttl"], reverse=True)
    return {
        "conversations": conversations,
        "generated": datetime.datetime.now().astimezone().isoformat(),
    }


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>troke chat monitor</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #171a21;
    --panel-2: #1d212a;
    --border: #262b36;
    --text: #e6e9ef;
    --muted: #8b93a3;
    --user-bg: #244a63;
    --user-text: #eaf4fb;
    --bot-bg: #21262f;
    --bot-text: #e6e9ef;
    --accent: #4ea1d3;
    --live: #4ec98a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
  }
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(15, 17, 21, 0.92);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex;
    align-items: baseline;
    gap: 18px;
    flex-wrap: wrap;
  }
  header h1 {
    font-size: 16px;
    margin: 0;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  header .dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--live);
    margin-right: 8px;
    box-shadow: 0 0 0 0 rgba(78, 201, 138, 0.6);
    animation: pulse 2s infinite;
    vertical-align: middle;
  }
  @keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(78, 201, 138, 0.5); }
    70%  { box-shadow: 0 0 0 7px rgba(78, 201, 138, 0); }
    100% { box-shadow: 0 0 0 0 rgba(78, 201, 138, 0); }
  }
  header .stats { color: var(--muted); font-size: 13px; }
  header .stats b { color: var(--text); font-weight: 600; }
  header .updated { margin-left: auto; color: var(--muted); font-size: 12px; }
  main {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 18px;
    align-items: start;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    max-height: 78vh;
  }
  .card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 11px 14px;
    background: var(--panel-2);
    border-bottom: 1px solid var(--border);
  }
  .card-head .cid {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    color: var(--accent);
    font-weight: 600;
  }
  .card-head .meta {
    font-size: 11px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  .card-head .active-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--live); display: inline-block;
  }
  .card-head .active-dot.stale { background: var(--muted); }
  .turns {
    padding: 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
  .bubble {
    max-width: 88%;
    padding: 8px 12px;
    border-radius: 14px;
    font-size: 13.5px;
    line-height: 1.45;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: anywhere;
  }
  .bubble .role {
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.6;
    margin-bottom: 3px;
  }
  .bubble.user {
    align-self: flex-end;
    background: var(--user-bg);
    color: var(--user-text);
    border-bottom-right-radius: 4px;
  }
  .bubble.assistant {
    align-self: flex-start;
    background: var(--bot-bg);
    color: var(--bot-text);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
    white-space: normal;
  }
  .bubble.assistant h2 { font-size: 12.5px; margin: 11px 0 5px; color: var(--accent);
    border-bottom: 1px solid var(--border); padding-bottom: 3px; }
  .bubble.assistant h3, .bubble.assistant h4 { font-size: 12.5px; margin: 9px 0 4px; }
  .bubble.assistant p { margin: 0 0 7px; }
  .bubble.assistant ul, .bubble.assistant ol { margin: 0 0 7px; padding-left: 17px; }
  .bubble.assistant li { margin: 2px 0; }
  .bubble.assistant li::marker { color: var(--accent); }
  .bubble.assistant strong { color: #fff; }
  .bubble.assistant code { background: #2a3542; padding: 1px 4px; border-radius: 4px; font-size: 12px; }
  .bubble.assistant hr { border: 0; border-top: 1px solid var(--border); margin: 9px 0; }
  .bubble.assistant .role + * { margin-top: 0; }
  .bubble.assistant > :last-child { margin-bottom: 0; }
  .empty {
    grid-column: 1 / -1;
    text-align: center;
    color: var(--muted);
    padding: 80px 20px;
    font-size: 15px;
  }
  .empty .big { font-size: 34px; margin-bottom: 12px; opacity: 0.5; }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-thumb { background: #333a47; border-radius: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
</style>
</head>
<body>
<header>
  <h1><span class="dot"></span>troke chat monitor</h1>
  <div class="stats" id="stats">&hellip;</div>
  <div class="updated" id="updated">connecting&hellip;</div>
</header>
<main id="feed"></main>
<script>
(function () {
  var lastData = null;
  var lastFetch = null;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Minimal, XSS-safe Markdown -> HTML (escape first, then format). Mirrors the chat page.
  function renderMarkdown(src) {
    function inline(s) {
      return esc(s)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    }
    var lines = String(src == null ? "" : src).replace(/\r/g, "").split("\n");
    var html = "", i = 0;
    function isUL(l) { return /^\s*[-*+]\s+/.test(l); }
    function isOL(l) { return /^\s*\d+[.)]\s+/.test(l); }
    function isH(l) { return /^#{1,4}\s+/.test(l); }
    function isHR(l) { return /^\s*([-*_])\1{2,}\s*$/.test(l); }
    while (i < lines.length) {
      var line = lines[i];
      if (/^\s*$/.test(line)) { i++; continue; }
      var h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) { var lvl = Math.min(h[1].length + 1, 4); html += "<h" + lvl + ">" + inline(h[2]) + "</h" + lvl + ">"; i++; continue; }
      if (isHR(line)) { html += "<hr>"; i++; continue; }
      if (isUL(line)) { html += "<ul>"; while (i < lines.length && isUL(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*[-*+]\s+/, "")) + "</li>"; i++; } html += "</ul>"; continue; }
      if (isOL(line)) { html += "<ol>"; while (i < lines.length && isOL(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*\d+[.)]\s+/, "")) + "</li>"; i++; } html += "</ol>"; continue; }
      var para = [];
      while (i < lines.length && !/^\s*$/.test(lines[i]) && !isH(lines[i]) && !isUL(lines[i]) && !isOL(lines[i]) && !isHR(lines[i])) { para.push(lines[i]); i++; }
      html += "<p>" + para.map(inline).join("<br>") + "</p>";
    }
    return html;
  }

  function fmtTtl(ttl) {
    if (ttl == null || ttl < 0) return "no expiry";
    var m = Math.floor(ttl / 60), s = ttl % 60;
    return "expires in " + m + "m " + s + "s";
  }

  function render(data) {
    var main = document.getElementById("feed");
    var convs = (data && data.conversations) || [];
    var totalMsgs = 0;
    for (var i = 0; i < convs.length; i++) totalMsgs += (convs[i].turns || []).length;

    document.getElementById("stats").innerHTML =
      "<b>" + convs.length + "</b> conversation" + (convs.length === 1 ? "" : "s") +
      " &middot; <b>" + totalMsgs + "</b> message" + (totalMsgs === 1 ? "" : "s");

    if (!convs.length) {
      main.innerHTML =
        '<div class="empty"><div class="big">&#128173;</div>No conversations yet' +
        '<br><small>Live /chat sessions will appear here as they happen.</small></div>';
      return;
    }

    var html = "";
    for (var c = 0; c < convs.length; c++) {
      var conv = convs[c];
      var ttl = conv.ttl;
      // A conversation whose TTL is close to the ~1800s max was just active.
      var stale = (ttl != null && ttl >= 0 && ttl < 1500);
      var turns = conv.turns || [];
      var bubbles = "";
      for (var t = 0; t < turns.length; t++) {
        var role = turns[t].role === "user" ? "user" : "assistant";
        var label = role === "user" ? "user" : "assistant";
        // User turns are plain text (escaped); assistant turns render as Markdown.
        var body = role === "user" ? esc(turns[t].text) : renderMarkdown(turns[t].text);
        bubbles +=
          '<div class="bubble ' + role + '">' +
          '<span class="role">' + label + '</span>' +
          body +
          '</div>';
      }
      html +=
        '<section class="card">' +
        '<div class="card-head">' +
        '<span class="cid">' + esc(conv.id) + '</span>' +
        '<span class="meta">' +
        '<span class="active-dot' + (stale ? " stale" : "") + '"></span>' +
        esc(fmtTtl(ttl)) +
        '</span></div>' +
        '<div class="turns">' + bubbles + '</div>' +
        '</section>';
    }
    main.innerHTML = html;
  }

  function tickUpdated() {
    var el = document.getElementById("updated");
    if (!lastFetch) return;
    var secs = Math.round((Date.now() - lastFetch) / 1000);
    el.textContent = "updated " + secs + "s ago";
  }

  function load() {
    fetch("/feed", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        lastData = data;
        lastFetch = Date.now();
        render(data);
        tickUpdated();
      })
      .catch(function () {
        document.getElementById("updated").textContent = "feed unreachable — retrying";
      });
  }

  load();
  setInterval(load, 3000);
  setInterval(tickUpdated, 1000);
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "trokeMonitor/1.0"

    def _send(self, code, body, content_type, cookie=None):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def _authed(self):
        # Token supplied via ?t=<token> or the mon_token cookie; constant-time compare.
        supplied = parse_qs(urlparse(self.path).query).get("t", [None])[0]
        if supplied is None:
            for part in self.headers.get("Cookie", "").split(";"):
                part = part.strip()
                if part.startswith("mon_token="):
                    supplied = part[len("mon_token="):]
                    break
        return supplied is not None and hmac.compare_digest(supplied, TOKEN)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if not self._authed():
            self._send(
                403,
                json.dumps({"error": "forbidden",
                            "message": "add ?t=<token> to the URL (see logs/monitor.log)"}),
                "application/json; charset=utf-8",
            )
            return
        if path == "/feed":
            try:
                data = collect_feed()
                self._send(200, json.dumps(data), "application/json; charset=utf-8")
            except Exception as exc:  # never crash the handler thread
                self._send(
                    500,
                    json.dumps({"error": "feed_failed", "message": str(exc)}),
                    "application/json; charset=utf-8",
                )
        elif path == "/":
            # Set a token cookie so the page's /feed polling stays authorized.
            self._send(200, PAGE, "text/html; charset=utf-8",
                       cookie=f"mon_token={TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        else:
            self._send(
                404,
                json.dumps({"error": "not_found"}),
                "application/json; charset=utf-8",
            )

    def log_message(self, *args):  # quiet: no per-request logging
        pass


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"monitor (token-gated) on http://localhost:{PORT}/?t={TOKEN}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
