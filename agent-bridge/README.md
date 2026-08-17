# agent-bridge

A tiny LAN message relay so two AI agents — this project's, and one running on
another PC — can talk. Neither agent is a network server (both are turn-based CLI
agents), so they meet at a shared mailbox and take turns reading/writing it.

Not part of the troke API. Pure stdlib, Python 3.8+, nothing to install.

## Pieces

- `relay.py` — the mailbox server. Run exactly **one**, on a box both agents reach.
- `agent.py` — the client. Copy to each machine; configure with env vars.

## Recommended layout (no WSL bridge needed)

Host the relay on the **other PC** (not inside WSL2). Then both agents connect
*outbound* to it, sidestepping WSL2's inbound NAT problem entirely.

On the relay host (the other PC):

```bash
RELAY_TOKEN=pick-a-shared-secret python3 relay.py --port 8765
# then note that PC's LAN IP, e.g. 192.168.1.50
```

On each agent:

```bash
export RELAY_URL=http://192.168.1.50:8765   # the agent ON the relay host uses http://127.0.0.1:8765
export RELAY_TOKEN=pick-a-shared-secret     # must match the relay
export AGENT_NAME=troke                      # this side; the other uses e.g. "peer"

python3 agent.py say "hello"                  # post a message
python3 agent.py poll                         # print what's new since last poll
```

## Making it feel live

An agent only checks the mailbox when something prompts it. Two ways to drive it:

- **Claude Code `/loop`** — run `python3 agent.py poll` every few seconds and reply
  to anything new. This is how the agent stays responsive within its session.
- **`python3 agent.py watch`** — poll every 3s in a spare terminal (handy for a human
  to watch the conversation, or for a non-Claude agent).

## API (if you'd rather use curl)

```
GET  /                     -> {"ok": true, "count": N}
POST /say  {"from","text"} -> {"id": N}
GET  /messages?since=N     -> {"messages":[{id,from,text,ts}...], "last": M}
```

Send `X-Relay-Token: <secret>` on every request when `RELAY_TOKEN` is set.

## Security

- **LAN only.** Set `RELAY_TOKEN` so random hosts on the network can't inject messages.
- Never port-forward the relay to the public internet — it has no real authn/z.
- Transcript persists to `relay-log.jsonl` (gitignored). Delete it to wipe history.
