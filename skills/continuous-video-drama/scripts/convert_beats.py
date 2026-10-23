#!/usr/bin/env python3
"""Prose beats -> structured beats, so the generator can enforce mouth discipline per line.

Reads each ep*/plan.json whose `beats` is still a prose paragraph and rewrites it as a list of
{"action": "..."} and {"say": "<cast key>", "text": "..."} entries, in the original order.

The speaker is resolved from explicit surface forms only, longest first, searched in the text
immediately preceding each <d> block. Earlier attempts auto-tokenised the cast descriptions and
matched the literal word "Chinese" out of the <d>[Chinese] tag itself, misattributing 68 of 321
lines. Never guess speakers from loose substrings.

Writes plan.json in place. Keep a copy of the originals first; run audit_plans.py afterwards.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Longest first: "Chen Jianguo" must win over "Chen".
FORMS = [
    ("Chen Jianguo", "jianguo"), ("Chen Xingye", "chen"), ("Chen's mother", "chenmu"),
    ("Su Xiaotang", "su"), ("Su's mother", "sumu"), ("Lin Zhixia", "lin"),
    ("Professor Zhou", "zhoujiao"), ("Zhao Dazhuang", "zhuang"), ("Principal Ma", "ma"),
    ("Teacher Song", "song"), ("older man's voice", "song"),
    ("Lu Yuan", "lu"), ("Zhou Yi", "zhou"), ("Old Qian", "qian"),
    ("vice-principal", "fuxiao"), ("invigilator", "jiankao"), ("administrator", "jiaowu"),
    ("schoolgirl", "girl"), ("competitor", "xuanshou"), ("judge", "caipan"),
    ("Jianguo", "jianguo"), ("Xingye", "chen"), ("Xiaotang", "su"), ("Zhixia", "lin"),
    ("Zhao", "zhuang"), ("Qian", "qian"), ("Chen", "chen"), ("Lin", "lin"),
    ("Lu", "lu"), ("Su", "su"), ("Ma", "ma"),
]
DIALOGUE = re.compile(r"<d>\[Chinese\]\s*(.*?)</d>", re.S)


SPEECH = r"(?:\s*\(S\d+\)|[^.]{0,80}?\b(?:says?|asks?|answers?|replies|adds?|protests?|announces?|"
SPEECH += r"shouts?|calls?|mutters?|murmurs?|recites?|reads?|demands?|objects?|cuts? in|continues?|"
SPEECH += r"explains?|retorts?|concludes?|reports?|admits?|rules?|snaps?)\b)"


def speaker_for(window, fallback):
    """Nearest cast name that is actually attached to a speech cue.

    Requiring the cue matters: a bare nearest-name search assigned the principal's lines to the
    teacher standing in front of his desk, because her name appeared closer to the quote. The cue
    is either an (S\\d) tag or a speech verb following the name.

    Returns (key, index) so the caller can scope later checks to this attribution only.
    """
    window = window.replace("[Chinese]", " ")
    best, pos = fallback, -1
    for form, key in FORMS:
        for m in re.finditer(r"\b" + re.escape(form) + r"\b" + SPEECH, window):
            if m.start() > pos:
                best, pos = key, m.start()
    return best, pos


OFFSCREEN = re.compile(r"off-screen|offscreen|off screen|from inside the room|through the phone|"
                       r"voice comes|comes from inside|on the phone", re.I)


def convert(beats, cast):
    out, cursor, last = [], 0, (cast[0] if cast else "lin")
    for m in DIALOGUE.finditer(beats):
        preceding = beats[cursor:m.start()]
        window = beats[max(0, m.start() - 260):m.start()]
        key, at = speaker_for(window, last)
        action = re.sub(r"[^.]*$", "", preceding).strip()   # drop the attribution tail
        if action:
            out.append({"action": action})
        line = {"say": key, "text": m.group(1).strip()}
        # Carry the prose's off-screen marker onto the line itself. Without this the generator was
        # told to frame one character alone AND that an absent character visibly moves her mouth,
        # and the model resolved the contradiction by pulling her into shot with broken eyelines.
        # Scope the check to THIS speaker's own attribution: a stage direction elsewhere in the
        # paragraph ("Lin is just offscreen on the left") otherwise marks every later line off too,
        # which emptied the frame of everyone including the character on camera.
        if at >= 0 and OFFSCREEN.search(window[at:]):
            line["off"] = True
        out.append(line)
        last, cursor = key, m.end()
    tail = beats[cursor:].strip().lstrip(".").strip()
    tail = re.sub(r"^(while|and)\b[^.]*\.\s*", "", tail)
    if tail:
        out.append({"action": tail})
    return out


def main():
    for path in sorted(ROOT.glob("ep*/plan.json")):
        plan = json.loads(path.read_text())
        cast = plan.get("cast", [])
        for segment in plan["segments"]:
            if not isinstance(segment.get("beats"), str):
                continue
            present = segment.get("cast", cast)
            beats = convert(segment["beats"], present)
            # Someone heard only as an off-screen voice is not in shot; everyone else is.
            heard_off = {b["say"] for b in beats if b.get("off")}
            on_screen = {b["say"] for b in beats if "say" in b and not b.get("off")}
            segment["in_frame"] = [k for k in present if k not in heard_off or k in on_screen]
            offscreen = [k for k in present if k in heard_off and k not in on_screen]
            if offscreen:
                segment["offscreen"] = offscreen
            segment["beats"] = beats
            segment.pop("cast", None)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
        spoken = sum(1 for s in plan["segments"] for b in s["beats"] if "say" in b)
        print(f"{path.parent.name}: {len(plan['segments'])} segments, {spoken} lines")


if __name__ == "__main__":
    main()
