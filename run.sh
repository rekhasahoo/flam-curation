#!/usr/bin/env bash
# Usage: ./run.sh <raw_dir> <out_dir> [extra flags, see curate/cli.py]
# Works offline: no network access anywhere in the pipeline.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -lt 2 ]; then echo "usage: $0 <raw_dir> <out_dir> [flags]" >&2; exit 2; fi
RAW="$(realpath "$1")"; OUT="$(mkdir -p "$2" && realpath "$2")"; shift 2
export PYTHONHASHSEED=0 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
exec python3 -m curate.cli "$RAW" "$OUT" "$@"
