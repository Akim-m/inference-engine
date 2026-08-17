#!/usr/bin/env bash
# Talk to the relay as "troke" (this agent's side). The relay runs locally, so we
# reach it over localhost. Usage:  ./troke.sh say "hello"   |   ./troke.sh poll
set -euo pipefail
cd "$(dirname "$0")"
source ./bridge.env
export RELAY_URL="http://127.0.0.1:${RELAY_PORT:-8765}"
export AGENT_NAME=troke
exec python3 agent.py "$@"
