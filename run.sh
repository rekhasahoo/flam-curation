#!/usr/bin/env bash
# Usage: ./run.sh <raw_dir> <out_dir> [extra flags, see curate/cli.py]
# Works offline: no network access anywhere in the pipeline.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -lt 2 ]; then echo "usage: $0 <raw_dir> <out_dir> [flags]" >&2; exit 2; fi
PY=python3; "$PY" -c "import sys" >/dev/null 2>&1 || PY=python
RAW="$(cd "$1" && pwd)"; mkdir -p "$2"; OUT="$(cd "$2" && pwd)"; shift 2
export PYTHONHASHSEED=0 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
exec "$PY" -m curate.cli "$RAW" "$OUT" "$@"
