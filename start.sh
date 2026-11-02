#!/usr/bin/env bash
# Start everything: ghost server, Ring stream, wave detector. Ctrl-C stops all.
# Needs CAM_ID set (find it with: cd ring && npm run cameras).
set -euo pipefail
cd "$(dirname "$0")"
: "${CAM_ID:?Set CAM_ID first, e.g. CAM_ID=123456789 ./start.sh}"
trap 'kill 0' EXIT
node ghost/server.mjs &
sleep 1
echo "Open http://127.0.0.1:8787 on the projector screen (fullscreen: press F; mirror: press M)."
(cd ring && CAM_ID="$CAM_ID" node stream.mjs) &
sleep 5
(cd detector && .venv/bin/python wave.py "$@") &
wait
