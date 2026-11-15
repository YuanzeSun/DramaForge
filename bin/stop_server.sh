#!/usr/bin/env bash
# Stop only the current user's server identified by the launch record.
set -euo pipefail
exec python3 - "$@" <<'PYCODE'
import argparse
import json
import os
import signal
import time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--pidfile',required=True)
p.add_argument('--force',action='store_true')
a=p.parse_args()
path=Path(a.pidfile)
meta_path=path.with_suffix('.meta.json')
meta=json.loads(meta_path.read_text()) if meta_path.exists() else None
uid=os.getuid()
if meta and meta['uid']!=uid:
    raise SystemExit('Refusing: server launch belongs to another user')
pid=int(path.read_text().strip()) if path.exists() else (meta or {}).get('pid')
if not pid:
    raise SystemExit('No server launch record')
targets=set()
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        if proc.stat().st_uid!=uid:continue
        args=(proc/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
        stat=(proc/'stat').read_text();fields=stat[stat.rfind(')')+2:].split()
        current=int(proc.name)
        if current==pid and any('deploy_local/start_server.sh' in s or 'torchrun' in s for s in args):
            targets.add(current)
        if not meta or fields[0]=='Z' or int(fields[19])<meta['start_ticks']:continue
        if '-m' not in args or args[args.index('-m')+1]!='lightx2v.server':continue
        if args[args.index('--config_json')+1]!=meta['config']:continue
        if args[args.index('--port')+1]!=meta['port']:continue
        targets.add(current)
    except (OSError,ValueError,IndexError):pass
if not targets:
    path.unlink(missing_ok=True);meta_path.unlink(missing_ok=True)
    print('Recorded server has no live owned processes')
    raise SystemExit(0)
print('Stopping owned server processes:',sorted(targets),flush=True)
for current in targets:
    try:os.kill(current,signal.SIGTERM)
    except ProcessLookupError:pass
for _ in range(30):
    left=[]
    for current in targets:
        try:
            stat=Path('/proc',str(current),'stat').read_text()
            if stat[stat.rfind(')')+2:].split()[0]!='Z':left.append(current)
        except OSError:pass
    if not left:
        path.unlink(missing_ok=True);meta_path.unlink(missing_ok=True)
        print('Stopped owned server processes')
        raise SystemExit(0)
    time.sleep(1)
if a.force:
    for current in left:
        try:os.kill(current,signal.SIGKILL)
        except ProcessLookupError:pass
    path.unlink(missing_ok=True);meta_path.unlink(missing_ok=True)
    print('Forced stop of remaining owned server processes')
    raise SystemExit(0)
raise SystemExit('Owned processes remain; inspect before retrying with --force')
PYCODE
