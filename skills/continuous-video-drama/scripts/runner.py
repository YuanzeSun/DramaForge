#!/usr/bin/env python3
"""Generate episodes back to back until a deadline, stitching a cumulative preview each time.

Walks ep*/plan.json under the working directory in order. Segment 01 of an episode starts from
`opening` (text-to-video by default, or image-to-video from a carried-over frame); every later
segment continues from the previous segment's real last frame. A segment marked `new_scene`
restarts the chain. Resumable: segments whose .last.png exists are skipped and in-flight tasks are
re-attached rather than resubmitted. Stops cleanly at the deadline without starting a segment it
cannot finish.

Configure with environment variables (all optional):
  DRAMA_ROOT      directory holding ep*/ and cast.json   (default: this script's directory)
  DRAMA_ENDPOINT  LightX2V-style server base URL          (default: http://127.0.0.1:8001)
  DRAMA_SIZE      "W,H" native generation size            (default: 1344,768 -> vertical 9:16)
  DRAMA_DEADLINE  "YYYY-MM-DDTHH:MM" local wall clock     (default: 24h from launch)
  DRAMA_STYLE     one-line global style sentence
  DRAMA_SHUTDOWN  shell command run once when the deadline stops the run, e.g. to free the GPUs

Requires cast.json beside the plans: {"key": "<description>; <voice descriptor>"}.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import av
import requests

import os

ROOT = Path(os.environ.get("DRAMA_ROOT", Path(__file__).resolve().parent))
ENDPOINT = os.environ.get("DRAMA_ENDPOINT", "http://127.0.0.1:8001")
SIZE = [int(x) for x in os.environ.get("DRAMA_SIZE", "1344,768").split(",")]
DEADLINE = (datetime.fromisoformat(os.environ["DRAMA_DEADLINE"]) if os.environ.get("DRAMA_DEADLINE")
            else datetime.now() + timedelta(hours=24))
SEGMENT_BUDGET = int(os.environ.get("DRAMA_SEGMENT_BUDGET", 240))   # don't start a segment past this margin
SHUTDOWN = os.environ.get("DRAMA_SHUTDOWN", "")                      # freeing the accelerators is NOT automatic

STYLE = os.environ.get("DRAMA_STYLE",
                       "live-action drama, vertical portrait, cinematic natural light, "
                       "realistic faces, restrained believable acting")

def cast_book():
    """Read cast.json fresh each call so new characters need no restart."""
    return json.loads((ROOT / "cast.json").read_text())



def log(msg):
    print(datetime.now().strftime("%m-%d %H:%M:%S"), msg, flush=True)


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def no_text_after_each_line(body):
    """Repeat the no-subtitle rule right after every spoken line.

    A single prohibition at the end of a long paragraph gets discounted: three of nine segments
    came back with the model's own captions burned in. Restating it next to each <d> block is the
    documented escalation for models with no negative-prompt field, which H3 does not have.
    """
    return body.replace("</d>", "</d> (clean frame, no words on screen)")


def wrap(body, scene, cast_keys, continuing):
    book = cast_book()
    who = " ".join(book[k] + "." for k in cast_keys)
    body = no_text_after_each_line(body)
    # Extras walking in is the most common content failure: a group shot grew four extra students
    # by its second half, and a bridge test invented a person present in neither source clip.
    people = f"Exactly {len(cast_keys)} people appear in this shot and no one else; no extra students, no passers-by, nobody enters the background. "
    # The cast block must appear in EVERY segment, continuations included: without it the model has
    # only bare (S1)/(S2) ids and guesses voices, which once gave the female teacher a male voice.
    head = ("Continue filming from this exact supplied frame, vertical portrait. The next moment of the same "
            f"unbroken take. Maintain the supplied frame's exact faces, hairstyles, costumes, object positions and lighting. {who} "
            if continuing else
            f"One continuous unbroken take, {STYLE}. {scene} {who} ")
    return (
        "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        if continuing else "") + (
        "integrated_multimodal_description: [Shot 1] " + head + body
        + " Everything happens in exactly the order described, at a natural everyday pace like real people talking, "
        "with no long silent pauses. Finish all speech by half a second before the end. "
        + people
        + "One continuous shot. No cuts, no crossfades, no transitions, no teleporting, no changing the set. "
        "No captions, no subtitles, no logos, no writing. Natural, lively, believable acting.\n\n"
        "overall_soundscape: Quiet continuous indoor room tone, distant schoolyard, footsteps and fabric movement, no music.\n\n"
        "non_diegetic_music: N/A")


def generate(episode, plan, segment, index, image):
    ident = segment["id"]
    output = episode / f"{ident}.mp4"
    continuing = image is not None
    payload = {"task": "i2av" if continuing else "t2av",
               "prompt": wrap(segment["beats"], segment.get("scene", plan.get("scene", "")),
                              segment.get("cast", plan.get("cast", [])), continuing),
               "seed": plan["seed"] + index, "num_frames": segment["frames"], "size": SIZE,
               "save_result_path": str(output)}
    if continuing:
        payload["image_path"] = str(image)
    save(output.with_suffix(".request.json"), payload)
    state_path = output.with_suffix(".state.json")
    previous = json.loads(state_path.read_text()) if state_path.exists() else None
    if previous and previous.get("status") in {"pending", "processing", "queued"}:
        task_id = previous["task_id"]
    else:
        r = requests.post(ENDPOINT+"/v1/tasks/video/", json=payload, timeout=60); r.raise_for_status()
        task_id = r.json()["task_id"]
    began = time.time()
    log(f"SUBMIT {episode.name}/{ident} {task_id}")
    while True:
        r = requests.get(f"{ENDPOINT}/v1/tasks/{task_id}/status", timeout=30); r.raise_for_status()
        state = r.json() | {"task_id": task_id, "elapsed": round(time.time()-began, 1)}
        save(state_path, state)
        if state["status"] == "completed":
            break
        if state["status"] in {"failed", "cancelled", "stopped"}:
            raise RuntimeError(state)
        time.sleep(3)
    with av.open(str(output)) as source:
        last = None
        for last in source.decode(video=0):
            pass
    last.to_image().save(output.with_suffix(".last.png"))
    log(f"DONE {episode.name}/{ident} {state['elapsed']}s")


def run_episode(episode):
    plan = json.loads((episode / "plan.json").read_text())
    image = None
    opening = plan.get("opening", {})
    if opening.get("image"):
        image = Path(opening["image"])
    done = 0
    for index, segment in enumerate(plan["segments"]):
        ident = segment["id"]
        if segment.get("new_scene"):
            image = None          # genuine scene change: restart the chain with t2av
        if (episode / f"{ident}.last.png").exists():
            image = episode / f"{ident}.last.png"
            done = index + 1
            continue
        if datetime.now().timestamp() + SEGMENT_BUDGET > DEADLINE.timestamp():
            log(f"DEADLINE reached before {episode.name}/{ident}; stopping")
            return False
        generate(episode, plan, segment, index, image)
        image = episode / f"{ident}.last.png"
        done = index + 1
        subprocess.Popen([sys.executable, str(ROOT/"stitch.py"), str(episode), str(done)],
                         stdout=(episode/"stitch.log").open("a"), stderr=subprocess.STDOUT)
    log(f"EPISODE COMPLETE {episode.name} ({done} segments)")
    return True


def main():
    while datetime.now().timestamp() + SEGMENT_BUDGET < DEADLINE.timestamp():
        pending = [d for d in sorted(ROOT.glob("ep*")) if (d/"plan.json").exists()
                   and not (d/"EPISODE_DONE").exists()]
        if not pending:
            log("No pending plans; waiting")
            time.sleep(60)
            continue
        for episode in pending:
            if not run_episode(episode):
                log("STOPPED at deadline")
                return shutdown()
            (episode/"EPISODE_DONE").write_text(datetime.now().isoformat()+"\n")
    log("STOPPED at deadline")
    shutdown()


def shutdown():
    """Run DRAMA_SHUTDOWN, if set, so the deadline also frees the accelerators.

    Learned the hard way: stopping generation is not the same as releasing the GPUs. A run that
    halted on time still left an 8-card server loaded and idle for hours.
    """
    if SHUTDOWN:
        log(f"SHUTDOWN: {SHUTDOWN}")
        subprocess.run(SHUTDOWN, shell=True)


if __name__ == "__main__":
    main()
