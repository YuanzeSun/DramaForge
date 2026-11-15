#!/usr/bin/env bash
# Inspect the current workflow without contacting the video service.
set -euo pipefail
TOOLKIT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${DRAMA_PYTHON:-python3}" "$TOOLKIT_DIR/drama.py" --project "${DRAMA_ROOT:-$PWD}" status "$@"
