#!/usr/bin/env python3
"""Start one LightX2V server across an explicit set of accelerators.

One large server beats several small ones for frame-chained work, which is sequential by nature:
two 4-card workers took ~390 s per segment on 8x Ascend 910B, one 8-card server took ~120 s.

    ./launch_server.py --devices 0,1,2,3,4,5,6,7 --config ../examples/server_8card.json

Check the cards are actually free first (npu-smi info / nvidia-smi) — other users' jobs live there
too. Stop it when the run ends: ./stop_server.sh. Generation finishing does not release the cards.
"""
import argparse
import os
import subprocess
from pathlib import Path

LIGHTX2V = Path(os.environ.get("LIGHTX2V_ROOT", Path.home() / "LightX2V"))

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="server", help="log/pid file prefix")
parser.add_argument("--devices", required=True, help="e.g. 0,1,2,3,4,5,6,7")
parser.add_argument("--port", type=int, default=8001)
parser.add_argument("--metrics", type=int, default=8002, help="must differ from --port")
parser.add_argument("--config", required=True, help="inference config JSON")
parser.add_argument("--logdir", default=".", help="where to write <name>.log and <name>.pid")
args = parser.parse_args()

nproc = len(args.devices.split(","))
logdir = Path(args.logdir).resolve()
logdir.mkdir(parents=True, exist_ok=True)
env = os.environ | {
    "ASCEND_RT_VISIBLE_DEVICES": args.devices,   # CUDA_VISIBLE_DEVICES on NVIDIA
    "CUDA_VISIBLE_DEVICES": args.devices,
    "NPROC": str(nproc),                         # start_server.sh must honour this
    "PORT": str(args.port),
    "METRIC_PORT": str(args.metrics),
    "CONFIG_JSON": str(Path(args.config).resolve()),
}
with (logdir / f"{args.name}.log").open("a") as log:
    process = subprocess.Popen(["bash", str(LIGHTX2V / "deploy_local/start_server.sh")],
                               env=env, cwd=str(LIGHTX2V), stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
(logdir / f"{args.name}.pid").write_text(f"{process.pid}\n")
print(f"{process.pid}  ({nproc} cards, port {args.port}, log {logdir/args.name}.log)")
print("model load takes a few minutes; poll /v1/service/status until it reports idle")
