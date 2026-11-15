"""Local LightX2V video execution with provenance-aware resume."""
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from prompts import video_prompt
from workflow import digest, file_hash, read, validate, write


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def deadline_at(value):
    if not value:
        return now() + timedelta(hours=1)
    value = datetime.fromisoformat(value)
    return value.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if value.tzinfo is None else value


def compile_request(project, ep, plan, segment, index, directory, dry=False):
    start = segment["start"]
    chained = start["mode"] == "continue"
    def image(key):
        if dry:
            try:
                path = project.asset_path(key, required=False)
            except ValueError:
                path = None
            return str(path) if path else f"<asset:{key}>"
        return str(project.asset_path(key))
    first = (str(directory / (plan["segments"][index - 1]["id"] + ".last.png")) if chained
             else image(start["asset"]))
    payload = {"task": "fl2av" if segment.get("end_asset") else "i2av",
        "prompt": video_prompt(project, plan, segment, chained), "image_path": first,
        "seed": plan["seed"] + index, "num_frames": segment["frames"],
        "size": project.config.get("size", [1344, 768]),
        "save_result_path": str(directory / (segment["id"] + ".mp4"))}
    if segment.get("end_asset"):
        payload["last_frame_path"] = image(segment["end_asset"])
    return payload


def extract_last(output):
    import av
    last = None
    with av.open(str(output)) as container:
        for last in container.decode(video=0):
            pass
    if last is None:
        raise ValueError(f"No video frames in {output}")
    dest = output.with_suffix(".last.png")
    temporary = dest.with_name(dest.stem + ".tmp.png")
    last.to_image().save(temporary)
    temporary.replace(dest)
    return dest


def render(project, episode, run, deadline=None, timeout=1200, preview=False):
    import fcntl
    import requests
    validate(project, episode, ready=True)
    end = deadline_at(deadline)
    endpoint = project.config.get("endpoint", "http://127.0.0.1:8001").rstrip("/")
    root = project.output / run
    root.mkdir(parents=True, exist_ok=True)
    # Two local runners must not claim the same output or submit duplicate tasks.
    with (root / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"Another runner owns {root}")
        for ep, plan in project.plans(episode):
            directory = root / ep
            directory.mkdir(parents=True, exist_ok=True)
            previous_input = None
            for index, s in enumerate(plan["segments"]):
                payload = compile_request(project, ep, plan, s, index, directory)
                image_hashes = {k: file_hash(payload[k]) for k in ("image_path", "last_frame_path") if k in payload}
                semantic_payload = {k: v for k, v in payload.items()
                                    if k not in {"save_result_path", "image_path", "last_frame_path"}}
                input_hash = digest({"endpoint": endpoint, "payload": semantic_payload, "images": image_hashes,
                    "parent": previous_input if s["start"]["mode"] == "continue" else None})
                output = Path(payload["save_result_path"])
                state_path = output.with_suffix(".state.json")
                previous = read(state_path) if state_path.exists() else {}
                if previous and previous.get("input_hash") != input_hash:
                    raise ValueError(f"{ep}/{s['id']}: inputs changed. Use a new --run name to preserve existing takes.")
                if previous.get("status") == "completed" and output.exists():
                    if previous.get("output_hash") and previous["output_hash"] != file_hash(output):
                        raise ValueError(f"Completed video changed on disk: {output}")
                    actual = extract_last(output)
                    previous_input = digest({"input": input_hash, "last": file_hash(actual)})
                    print(f"RESUME {ep}/{s['id']}", flush=True)
                    continue
                if not previous.get("task_id") and now() + timedelta(seconds=min(timeout, 240)) >= end:
                    print(f"DEADLINE before {ep}/{s['id']}; no new submission", flush=True)
                    return False
                if previous.get("status") in {"submitting", "submission_unknown"}:
                    raise ValueError(f"Submission outcome unknown for {output}. Reconcile server tasks before retrying.")
                if previous.get("status") in {"failed", "cancelled", "stopped"}:
                    raise ValueError(f"Previous task failed for {output}; choose a new --run after fixing the cause")
                write(output.with_suffix(".request.json"), payload)
                state = dict(previous, input_hash=input_hash)
                if state.get("task_id") and state.get("status") in {"pending", "queued", "processing", "completed"}:
                    task_id = state["task_id"]
                    print(f"REATTACH {ep}/{s['id']} {task_id}", flush=True)
                else:
                    state.update(status="submitting", began=now().isoformat())
                    write(state_path, state)
                    try:
                        response = requests.post(endpoint + "/v1/tasks/video/", json=payload, timeout=60)
                        response.raise_for_status()
                        task_id = response.json()["task_id"]
                    except Exception:
                        state["status"] = "submission_unknown"
                        write(state_path, state)
                        raise
                    state.update(task_id=task_id, status="pending")
                    write(state_path, state)
                    print(f"SUBMIT {ep}/{s['id']} {task_id}", flush=True)
                began = datetime.fromisoformat(state.get("began", now().isoformat()))
                while state.get("status") != "completed":
                    response = requests.get(f"{endpoint}/v1/tasks/{task_id}/status", timeout=30)
                    response.raise_for_status()
                    state.update(response.json(), task_id=task_id, input_hash=input_hash)
                    write(state_path, state)
                    if state["status"] in {"failed", "cancelled", "stopped"}:
                        raise RuntimeError(f"Task {task_id}: {state}")
                    if state["status"] == "completed":
                        break
                    if now() >= end or (now() - began).total_seconds() >= timeout:
                        # Keep state if cancellation fails; next run can still reattach.
                        requests.delete(f"{endpoint}/v1/tasks/{task_id}", timeout=30).raise_for_status()
                        state["status"] = "cancelled"
                        write(state_path, state)
                        raise TimeoutError(f"Cancelled {task_id} at deadline/task timeout")
                    time.sleep(3)
                actual = extract_last(output)
                state["output_hash"] = file_hash(output)
                write(state_path, state)
                previous_input = digest({"input": input_hash, "last": file_hash(actual)})
                print(f"DONE {ep}/{s['id']} {output}", flush=True)
                if preview:
                    stitch(project, ep, plan, run, index + 1)
            write(directory / "episode.json", {"status": "completed", "completed_at": now().isoformat(),
                "plan_hash": digest(plan), "segments": len(plan["segments"])})
    return True


def fork_run(project, episode, source, target, from_segment):
    """Create a repair take, retaining independent completed clips from a previous run."""
    validate(project, episode)
    if source == target:
        raise ValueError("Repair target must differ from the source run")
    ep, plan = project.plans(episode)[0]
    ids = [s["id"] for s in plan["segments"]]
    if from_segment not in ids:
        raise ValueError(f"Unknown repair segment: {from_segment}")
    start = ids.index(from_segment)
    destination = project.output / target / ep
    if destination.exists():
        raise ValueError("Repair destination already exists")
    original = project.output / source / ep
    retained = []
    affected = False
    for i, s in enumerate(plan["segments"]):
        if i == start:
            affected = True
        elif i > start and s["start"]["mode"] == "asset":
            affected = False
        if affected:
            continue
        state_path = original / (s["id"] + ".state.json")
        if not state_path.is_file() or read(state_path).get("status") != "completed":
            continue
        video = original / (s["id"] + ".mp4")
        if not video.is_file():
            raise ValueError(f"Missing retained video: {video}")
        retained.append(s["id"])
    destination.mkdir(parents=True)
    for sid in retained:
        for suffix in (".mp4", ".state.json", ".request.json", ".last.png"):
            path = original / (sid + suffix)
            if path.exists():
                shutil.copy2(path, destination / path.name)
    write(destination / "repair.json", {"source_run": source, "from_segment": from_segment,
          "retained_segments": retained})
    print(f"FORK {source} -> {target}; retained {', '.join(retained) or 'none'}", flush=True)
    return retained


def stitch(project, ep, plan, run, count=None):
    import imageio_ffmpeg
    directory = project.output / run / ep
    segments = plan["segments"][:count]
    if not segments:
        raise ValueError("No segments to stitch")
    paths = [directory / (s["id"] + ".mp4") for s in segments]
    if any(not p.is_file() for p in paths):
        raise ValueError("Render all requested segments before stitching")
    n = len(paths)
    inputs = [arg for path in paths for arg in ("-i", str(path))]
    h, w = project.config.get("size", [1344, 768])
    scale = project.config.get("scale", f"{w}:{h}")
    crop = f"crop={project.config['crop']}," if project.config.get("crop") else ""
    graph = ("".join(f"[{i}:v:0][{i}:a:0]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a];"
             f"[v]{crop}scale={scale}:flags=lanczos,setsar=1[vo];"
             "[a]dynaudnorm=f=150:g=15:p=0.9,alimiter=limit=0.95,aresample=48000[ao]")
    dest = directory / "preview.mp4"
    temp = directory / "preview.tmp.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", graph, "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "fast",
        "-crf", "19", "-threads", "8", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temp)], check=True)
    temp.replace(dest)
    print(f"PREVIEW {dest}", flush=True)
    return dest
