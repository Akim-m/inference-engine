#!/usr/bin/env bash
# Start the relay on this machine, reachable on the LAN once the Windows bridge
# (windows-bridge.ps1) is in place. Reads the shared secret from bridge.env.
set -euo pipefail
cd "$(dirname "$0")"
source ./bridge.env
exec python3 relay.py --host 0.0.0.0 --port "${RELAY_PORT:-8765}"
