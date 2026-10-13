#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PBWORK_PYTHON:-}"
if [ -z "$PY" ]; then
    if [ -x "$REPO/.venv/bin/python" ] && "$REPO/.venv/bin/python" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
        PY="$REPO/.venv/bin/python"
    else
        PY=python3
    fi
fi
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUTF8=1
exec "$PY" -m pbwork "$@"
