#!/usr/bin/env python3
"""Check structured plans for the defects that actually shipped broken video.

  1. a line whose speaker is listed neither in_frame nor offscreen
  2. a segment with no dialogue at all  (21 of 21 wordless segments came back as gibberish)
  3. a segment that opens on a line     (early lines get clipped; lead with a beat of action)
  4. shouted delivery                   (shouted lines garbled or dropped most often)
  5. leftover prose beats
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHOUT = re.compile(r"\b(shout\w*|scream\w*|bellow\w*|yell|yells|yelling)\b")


def main():
    problems = []
    for path in sorted(ROOT.glob("ep*/plan.json")):
        plan = json.loads(path.read_text())
        ep = path.parent.name
        for seg in plan["segments"]:
            where = f"{ep}/{seg['id']}"
            beats = seg.get("beats")
            if isinstance(beats, str):
                problems.append((where, "prose", "beats not converted"))
                continue
            present = set(seg.get("in_frame", [])) | set(seg.get("offscreen", []))
            spoken = [b for b in beats if "say" in b]
            for b in spoken:
                if b["say"] not in present:
                    problems.append((where, "speaker", f"{b['say']} not present: {b['text'][:28]}"))
            if not spoken:
                problems.append((where, "silent", "no dialogue — will invent gibberish"))
            if beats and "say" in beats[0]:
                problems.append((where, "opens-on-line", beats[0]["text"][:28]))
            for b in beats:
                text = b.get("action", "") + b.get("manner", "")
                if SHOUT.search(text.lower()):
                    problems.append((where, "shout", text[:40]))
    by_kind = {}
    for where, kind, detail in problems:
        by_kind.setdefault(kind, []).append((where, detail))
    for kind in ("prose", "speaker", "silent", "opens-on-line", "shout"):
        items = by_kind.get(kind, [])
        print(f"\n{kind}: {len(items)}")
        for where, detail in items:
            print(f"   {where:10} {detail}")
    print(f"\ntotal problems: {len(problems)}")


if __name__ == "__main__":
    main()
