#!/usr/bin/env bash
# Usage: ./download.sh [raw_dir]   (default ./raw)  -- the ONLY step that needs the network.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q "datasets>=2.19" pyarrow numpy
python3 download.py "${1:-raw}"
( cd "${1:-raw}" && find . -type f ! -name checksums.txt -print0 | sort -z | xargs -0 sha256sum > checksums.txt )
echo "raw data in ${1:-raw}; checksums in ${1:-raw}/checksums.txt"
