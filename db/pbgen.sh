#!/usr/bin/env bash
# Wrapper for the ParkBenchDB data generator: runs "python -m pbgen" from this repository.
#   usage: db/pbgen.sh <command> [options]      (see docs/data-generation.md)
# Python: $PBGEN_PYTHON if set, else the repo's .venv, else python3.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PBGEN_PYTHON:-}"
if [ -z "$PY" ]; then
    if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY="python3"; fi
fi
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m pbgen "$@"
