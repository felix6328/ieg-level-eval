#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${LEVEL_EVAL_PYTHON:-.venv/bin/python}" -m uvicorn levelgen.ieg.api:app --host 127.0.0.1 --port "${LEVEL_EVAL_PORT:-8872}"
