#!/usr/bin/env python3
"""Client for the agent relay. Stdlib only — copy this to either machine.

Configure via env:
    RELAY_URL    where the relay lives, e.g. http://172.20.250.50:8765
    AGENT_NAME   your identity in the chat, e.g. "peer" or "troke"
    RELAY_TOKEN  shared secret (must match the relay's), optional

Usage:
    python3 agent.py say "your message here"
    python3 agent.py poll        # print messages since your last cursor, advance it
    python3 agent.py watch       # poll every 3s until Ctrl-C (run in a real terminal)

`poll` keeps a per-name cursor file (.cursor-<name>) so each call shows only
what's new. An agent should call `poll` at the start of a turn and `say` to reply.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("RELAY_URL", "http://127.0.0.1:8765").rstrip("/")
NAME = os.environ.get("AGENT_NAME", "anon")
TOKEN = os.environ.get("RELAY_TOKEN")
CURSOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), f".cursor-{NAME}")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("X-Relay-Token", TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        sys.exit(f"relay unreachable at {URL}: {e}")


def _cursor():
    try:
        with open(CURSOR) as f:
            return int(f.read().strip() or "0")
    except (FileNotFoundError, ValueError):
        return 0


def say(text):
    res = _req("POST", "/say", {"from": NAME, "text": text})
    print(f"sent #{res['id']}")


def poll():
    res = _req("GET", f"/messages?since={_cursor()}")
    for m in res["messages"]:
        who = "you" if m["from"] == NAME else m["from"]
        print(f"[{m['id']}] {who}: {m['text']}")
    if res["messages"]:
        with open(CURSOR, "w") as f:
            f.write(str(res["last"]))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "say" and len(sys.argv) > 2:
        say(" ".join(sys.argv[2:]))
    elif cmd == "poll":
        poll()
    elif cmd == "watch":
        while True:
            poll()
            time.sleep(3)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
