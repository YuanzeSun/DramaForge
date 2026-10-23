#!/usr/bin/env bash
# Progress of a frame-chained run: DRAMA_ROOT=/path/to/project ./status.sh
set -uo pipefail
ROOT="${DRAMA_ROOT:-$PWD}"
PY="${DRAMA_PYTHON:-python3}"
cd "$ROOT" || exit 1
echo "== $(date '+%F %H:%M %Z')"
[ -f runner.log ] && tail -3 runner.log
echo "== latest previews"
ls -1t ep*/ep*_*.mp4 2>/dev/null | head -5
echo "== per episode"
for d in ep*/; do
  [ -f "$d/plan.json" ] || continue
  n=$(ls "$d"[0-9][0-9].mp4 2>/dev/null | wc -l)
  t=$("$PY" -c "import json;print(len(json.load(open('$d/plan.json'))['segments']))" 2>/dev/null)
  printf "  %-6s %2s/%-2s%s\n" "${d%/}" "$n" "$t" "$([ -f "$d/EPISODE_DONE" ] && echo '  DONE')"
done
