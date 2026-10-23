#!/usr/bin/env bash
# Stop every LightX2V server rank and free the accelerators.
#
# Generation finishing is NOT the same as releasing the cards: a run that halted on its deadline
# still left an 8-card server loaded and idle for hours. Always run this when done.
#
# Matches an exact argv rather than using pkill -f, whose pattern also matches its own command
# line and has silently killed the wrong process here.
set -uo pipefail
pids=$(ps -eo pid,args | awk '/[t]orchrun --standalone|[l]ightx2v\.server --model_cls/{print $1}')
if [ -z "$pids" ]; then echo "no server running"; exit 0; fi
echo "stopping: $(echo $pids | tr '\n' ' ')"
kill $pids 2>/dev/null
for _ in $(seq 1 12); do
  sleep 5
  left=$(ps -eo args | grep -c "[l]ightx2v.server" || true)
  [ "$left" -eq 0 ] && { echo "stopped"; exit 0; }
done
echo "forcing"
ps -eo pid,args | awk '/[t]orchrun --standalone|[l]ightx2v\.server --model_cls/{print $1}' | xargs -r kill -9
sleep 5
echo "remaining ranks: $(ps -eo args | grep -c '[l]ightx2v.server' || true)"
