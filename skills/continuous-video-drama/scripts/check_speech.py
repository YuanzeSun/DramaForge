#!/usr/bin/env python3
"""Transcribe every generated segment and compare it against the scripted lines.

Usage:  check_speech.py [episode-dir ...]     (default: every ep*/ under DRAMA_ROOT)

This is the one automated check worth running on finished video. It found the single worst defect
in a 145-segment production: every segment written without dialogue had invented mumbled gibberish,
which the model then burned in as garbled captions. Twenty-one for twenty-one.

Reads each plan.json, extracts the expected text from the <d> blocks, transcribes the rendered mp4
with faster-whisper, and reports phonetic similarity. Interpret the output as:

  no scripted dialogue but speech detected  -> the model invented words; regenerate with a real line
  similarity < 0.80                         -> words dropped or garbled; regenerate
  similarity 0.80-0.95                      -> usually digit normalisation (四十秒 -> "40秒"); read it
  no speech detected                        -> a line went missing entirely

Needs faster-whisper, opencc, pypinyin, and a local whisper model (set DRAMA_WHISPER).
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from opencc import OpenCC
from pypinyin import lazy_pinyin

ROOT = Path(os.environ.get("DRAMA_ROOT", "."))
MODEL = os.environ.get("DRAMA_WHISPER", "/data/syz/models/faster-whisper-small")
LANG = os.environ.get("DRAMA_LANG", "zh")
CC = OpenCC("t2s")
DIALOGUE = re.compile(r"<d>\[[A-Za-z]+\]\s*(.*?)</d>", re.S)


def spoken_text(segment):
    """Expected words, from either structured beats or a prose paragraph."""
    beats = segment.get("beats")
    if isinstance(beats, list):
        return "".join(b["text"] for b in beats if "say" in b)
    return "".join(DIALOGUE.findall(beats or ""))


def normalise(text):
    return "".join(c for c in CC.convert(text) if c.isalnum())


def main():
    episodes = [Path(a) for a in sys.argv[1:]] or sorted(ROOT.glob("ep*"))
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=16, local_files_only=True)
    flagged, total = [], 0
    for episode in episodes:
        plan_path = episode / "plan.json"
        if not plan_path.exists():
            continue
        for segment in json.loads(plan_path.read_text())["segments"]:
            video = episode / f"{segment['id']}.mp4"
            if not video.exists():
                continue
            total += 1
            expected = spoken_text(segment)
            parts, _ = model.transcribe(str(video), language=LANG, beam_size=5, temperature=0,
                                        vad_filter=True, condition_on_previous_text=False)
            heard = "".join(CC.convert(p.text) for p in parts).strip()
            where = f"{episode.name}/{segment['id']}"
            if not expected:
                if heard:
                    flagged.append((where, "invented", heard[:60]))
                    print(f"{where}  INVENTED SPEECH  {heard[:60]}", flush=True)
                continue
            if not heard:
                flagged.append((where, "silent", expected[:60]))
                print(f"{where}  NO SPEECH        want {expected[:50]}", flush=True)
                continue
            score = difflib.SequenceMatcher(None, lazy_pinyin(normalise(expected)),
                                            lazy_pinyin(normalise(heard)), autojunk=False).ratio()
            mark = "  " if score >= 0.95 else ("~ " if score >= 0.80 else "! ")
            print(f"{where} {mark}{score:.2f}  {heard[:58]}", flush=True)
            if score < 0.80:
                flagged.append((where, "garbled", heard[:60]))
    print(f"\n{total} segments checked, {len(flagged)} need attention")
    for where, kind, detail in flagged:
        print(f"   {where:12} {kind:9} {detail}")


if __name__ == "__main__":
    main()
