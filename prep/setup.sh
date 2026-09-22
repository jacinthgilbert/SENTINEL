#!/usr/bin/env bash
# One-time setup for the Step 2 geo-prep stack.
#   ./prep/setup.sh          then   ./prep/go.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}          # macOS has no bare `python`
command -v "$PY" >/dev/null || { echo "no $PY on PATH"; exit 1; }

[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --timeout 120 --retries 5 -r prep/requirements.txt
echo "ready — now run ./prep/go.sh"
