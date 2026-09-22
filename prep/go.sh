#!/usr/bin/env bash
# Run the geo-prep pipeline with the venv and .env loaded.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "no .env — copy .env.example and add your key"; exit 1; }
[ -x .venv/bin/python ] || { echo "run ./prep/setup.sh first"; exit 1; }
set -a; source .env; set +a
exec ./.venv/bin/python prep/run.py "$@"
