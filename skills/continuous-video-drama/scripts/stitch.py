#!/usr/bin/env python3
"""Stitch the first N segments of one episode into a cumulative review MP4.

Usage: stitch.py <episode-dir> <count>

One identical crop is applied to every segment. Never crop or zoom per segment: that reintroduces
exactly the shot-to-shot discontinuity frame chaining exists to avoid. No subtitles here — review
copies stay clean, and burned-in text cannot fix wrong audio.

  DRAMA_CROP   ffmpeg crop on the native frame   (default 756:1344:6:0, from 768x1344)
  DRAMA_SCALE  final output scale                (default 720:1280)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

CROP = os.environ.get("DRAMA_CROP", "756:1344:6:0")
SCALE = os.environ.get("DRAMA_SCALE", "720:1280")

episode = Path(sys.argv[1])
count = int(sys.argv[2])
plan = json.loads((episode / "plan.json").read_text())
segments = plan["segments"][:count]
inputs = [arg for s in segments for arg in ("-i", str(episode / f"{s['id']}.mp4"))]
graph = ("".join(f"[{i}:v][{i}:a]" for i in range(count)) + f"concat=n={count}:v=1:a=1[v][a];"
         f"[v]crop={CROP},scale={SCALE}:flags=lanczos,setsar=1[vo];"
         "[a]loudnorm=I=-18:TP=-1.5:LRA=9,aresample=48000[ao]")
title = plan.get("title", episode.name)
dest = episode / f"{episode.name}_{title}_01-{segments[-1]['id']}.mp4"
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
                "-filter_complex", graph, "-map", "[vo]", "-map", "[ao]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", "16",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dest)], check=True)
for old in episode.glob(f"{episode.name}_{title}_01-*.mp4"):
    if old != dest:
        old.unlink()
print("STITCHED", dest, flush=True)
