#!/usr/bin/env bash
# Stop only the current user's server process group recorded by launch_server.py.
set -euo pipefail
exec python3 - "$@" <<'PYCODE'
import argparse
import os
import signal
import time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--pidfile',required=True)
p.add_argument('--force',action='store_true')
a=p.parse_args()
path=Path(a.pidfile)
pid=int(path.read_text().strip())
proc=Path('/proc')/str(pid)
if not proc.exists():
    path.unlink(missing_ok=True)
    raise SystemExit('Recorded server is no longer running')
cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
if proc.stat().st_uid!=os.getuid() or os.getpgid(pid)!=pid or not any(s in cmd for s in ['deploy_local/start_server.sh','torchrun','lightx2v.server']):
    raise SystemExit('Refusing: pid does not identify an owned server process group')
os.killpg(pid,signal.SIGTERM)
for _ in range(30):
    time.sleep(1)
    try:os.killpg(pid,0)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        raise SystemExit('Stopped owned server group')
if a.force:
    os.killpg(pid,signal.SIGKILL)
    path.unlink(missing_ok=True)
    raise SystemExit('Forced stop of owned server group')
raise SystemExit('Server group still exists; inspect it before retrying with --force')
PYCODE
