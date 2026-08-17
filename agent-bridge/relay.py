#!/usr/bin/env python3
"""Tiny LAN relay so two agents can pass messages. Stdlib only, Python 3.8+.

Run this on a machine BOTH agents can reach. Ideally NOT inside WSL2 — host it
on the other PC (or any plain LAN box) so both agents connect *outbound* and you
skip the WSL inbound-port bridge entirely.

    RELAY_TOKEN=somesecret python3 relay.py --port 8765

API (all JSON):
    GET  /                  -> {"ok": true, "count": N}            health
    POST /say  {"from","text"} -> {"id": N}                        post a message
    GET  /messages?since=N  -> {"messages": [...], "last": M}      everything after id N

Auth: if RELAY_TOKEN is set in the env, every request must carry header
      X-Relay-Token: <token>.  Leave it unset for an open channel (LAN only).
Persistence: appends to relay-log.jsonl beside this file, so history survives a
      restart. Delete that file to wipe the transcript.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay-log.jsonl")
TOKEN = os.environ.get("RELAY_TOKEN")

_lock = threading.Lock()
_messages = []  # [{"id", "from", "text", "ts"}]


def _load():
    if not os.path.exists(LOG_PATH):
        return
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    _messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip a corrupt line rather than refuse to start


def _append(msg):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg) + "\n")


class Handler(BaseHTTPRequestHandler):
    def _auth_ok(self):
        return not TOKEN or self.headers.get("X-Relay-Token") == TOKEN

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._auth_ok():
            return self._send(401, {"error": "bad_token"})
        u = urlparse(self.path)
        if u.path == "/":
            with _lock:
                return self._send(200, {"ok": True, "count": len(_messages)})
        if u.path == "/messages":
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            with _lock:
                out = [m for m in _messages if m["id"] > since]
                last = _messages[-1]["id"] if _messages else 0
            return self._send(200, {"messages": out, "last": last})
        return self._send(404, {"error": "not_found"})

    def do_POST(self):
        if not self._auth_ok():
            return self._send(401, {"error": "bad_token"})
        if urlparse(self.path).path != "/say":
            return self._send(404, {"error": "not_found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad_json"})
        sender = (str(data.get("from", "")).strip() or "anon")[:64]
        text = str(data.get("text", "")).strip()
        if not text:
            return self._send(400, {"error": "empty_text"})
        with _lock:
            msg = {"id": len(_messages) + 1, "from": sender, "text": text, "ts": time.time()}
            _messages.append(msg)
            _append(msg)
        return self._send(200, {"id": msg["id"]})

    def log_message(self, *args):  # quiet the default stderr access log
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    _load()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"relay up on {args.host}:{args.port} "
        f"({len(_messages)} msgs loaded)"
        + ("  [token required]" if TOKEN else "  [OPEN — no auth]")
    )
    srv.serve_forever()


if __name__ == "__main__":
    main()
