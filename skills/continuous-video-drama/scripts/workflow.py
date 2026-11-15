"""Project files and GPT Image handoff. No image service or API key is required."""
import hashlib
import json
import re
import shutil
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = read(self.root / "project.json")
        if self.config.get("version") != 2:
            raise ValueError("project.json must have version 2")
        self.cast = read(self.root / "cast.json")
        self.manifest = read(self.root / "assets.json")
        self.assets = self.manifest["assets"]
        self.output = (self.root / self.config.get("output", "renders")).resolve()
        self.speakers = {k: f"S{i + 1}" for i, k in enumerate(self.cast)}

    def plans(self, episode=None):
        paths = sorted((self.root / "episodes").glob("ep*/plan.json"))
        if episode:
            identifier(episode)
            paths = [p for p in paths if p.parent.name == episode]
        if not paths:
            raise ValueError(f"No episode plans found: {episode or self.root}")
        return [(p.parent.name, read(p)) for p in paths]

    def asset_path(self, key, required=True):
        identifier(key)
        asset = self.assets[key]
        if not asset.get("path"):
            if required:
                raise ValueError(f"Generate and import GPT Image asset first: {key}")
            return None
        path = (self.root / asset["path"]).resolve()
        if not path.is_file():
            raise ValueError(f"Missing asset: {key}: {path}")
        actual = file_hash(path)
        if asset.get("sha256") != actual or asset.get("spec_hash") != asset_spec_hash(asset):
            raise ValueError(f"Asset bytes or prompt changed; re-import asset: {key}")
        for ref in asset.get("references", []):
            ref_path = self.asset_path(ref)
            if asset.get("reference_hashes", {}).get(ref) != file_hash(ref_path):
                raise ValueError(f"Reference {ref} changed; review and re-import asset: {key}")
        return path


def asset_spec_hash(asset):
    return digest({k: asset.get(k) for k in ("kind", "prompt", "references")})


def validate(project, episode=None, ready=False, segment_count=None):
    """Validate a production plan without requiring video dependencies or a running server."""
    errors = []
    size = project.config.get("size", [1344, 768])
    if not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or n <= 0 or n % 16 for n in size):
        errors.append("size must be [height,width], positive multiples of 16")
    if project.config.get("fps", 24) != 24:
        errors.append("This H3 workflow expects the server to run at 24 fps")
    for key, asset in project.assets.items():
        identifier(key)
        if asset.get("kind") not in {"character", "scene", "keyframe", "cover"} or not asset.get("prompt"):
            errors.append(f"{key}: asset needs kind and prompt")
        for ref in asset.get("references", []):
            if ref not in project.assets or ref == key:
                errors.append(f"{key}: invalid reference {ref}")
    # References are a DAG: export lists them before their consumers.
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError(f"Cyclic asset reference: {key}")
        if key in visited or key not in project.assets:
            return
        visiting.add(key)
        for ref in project.assets[key].get("references", []):
            visit(ref)
        visiting.remove(key)
        visited.add(key)
    for key in project.assets:
        visit(key)
    for name, plan in project.plans(episode):
        if plan.get("version") != 2 or type(plan.get("seed")) is not int or not plan.get("segments"):
            errors.append(f"{name}: needs version 2, integer seed, nonempty segments")
            continue
        seen = set()
        for index, s in enumerate(plan["segments"]):
            sid = identifier(s["id"])
            label = f"{name}/{sid}"
            if sid in seen:
                errors.append(f"{label}: duplicate segment id")
            seen.add(sid)
            frames = s.get("frames")
            if type(frames) is not int or not 158 <= frames <= 362 or frames % 17 != 5:
                errors.append(f"{label}: H3 frames must be 158..362 and frames % 17 == 5")
            start = s.get("start", {})
            if start.get("mode") not in {"asset", "continue"}:
                errors.append(f"{label}: start.mode must be asset or continue")
            if index == 0 and start.get("mode") != "asset":
                errors.append(f"{label}: an episode must start from a GPT keyframe")
            if (s.get("new_scene") or s.get("coverage_cut")) and start.get("mode") != "asset":
                errors.append(f"{label}: scene/coverage cut needs an explicit keyframe")
            for key in [start.get("asset"), s.get("end_asset")]:
                if key and key not in project.assets:
                    errors.append(f"{label}: unknown asset {key}")
                elif key and ready and (segment_count is None or index < segment_count):
                    try:
                        project.asset_path(key)
                    except ValueError as exc:
                        errors.append(f"{label}: {exc}")
            if start.get("mode") == "asset" and not start.get("asset"):
                errors.append(f"{label}: start.asset required")
            visible, off = s.get("in_frame", []), s.get("offscreen", [])
            if "in_frame" not in s or not isinstance(visible, list) or not isinstance(off, list):
                errors.append(f"{label}: in_frame and offscreen must be lists")
                continue
            if len(set(visible + off)) != len(visible + off):
                errors.append(f"{label}: repeated or contradictory cast visibility")
            if any(k not in project.cast for k in visible + off):
                errors.append(f"{label}: unknown cast member")
            beats = s.get("beats", [])
            if not isinstance(beats, list) or not beats or "action" not in beats[0]:
                errors.append(f"{label}: beats must start with an action")
                continue
            for b in beats:
                if not isinstance(b, dict) or ("action" in b) == ("say" in b):
                    errors.append(f"{label}: each beat needs exactly one of action or say")
                    continue
                if "say" in b:
                    if b["say"] not in visible + off or not b.get("text"):
                        errors.append(f"{label}: dialogue speaker/text missing")
                    if b.get("to") and (b["to"] not in visible + off or b["to"] == b["say"]):
                        errors.append(f"{label}: invalid dialogue addressee {b['to']}")
                elif not b.get("action"):
                    errors.append(f"{label}: beat needs action or say/text")
    if errors:
        raise ValueError("\n".join(errors))


def migrate(source, destination):
    """Copy plans into a clean project. Media and provider-specific code are never imported."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Migration destination must be empty")
    book = read(source / "cast.json")
    plans = sorted(source.glob("ep*/plan.json")) or sorted(source.glob("episodes/ep*/plan.json"))
    if not plans:
        raise ValueError("No source plans")
    assets = {}
    for key, description in book.items():
        identifier(key)
        assets[f"cast_{key}"] = {
            "kind": "character", "references": [],
            "prompt": "Character continuity reference for a live-action Chinese drama. "
                      + description.split(";", 1)[0] + ". Neutral relaxed pose, natural skin texture, "
                      "clear face and costume, simple neutral background. No lettering or watermark."}
    for path in plans:
        ep = identifier(path.parent.name)
        plan = read(path)
        for index, s in enumerate(plan["segments"]):
            sid = identifier(s["id"])
            s.setdefault("offscreen", [])
            s.setdefault("in_frame", [k for k in s.get("cast", plan.get("cast", [])) if k not in s["offscreen"]])
            s["in_frame"] = list(dict.fromkeys(k for k in s["in_frame"] if k not in s["offscreen"]))
            scene = s.get("scene", plan.get("scene", ""))
            prior_start = s.get("first_frame") or s.get("anchor_image")
            if index == 0:
                prior_start = prior_start or (plan.get("opening") or {}).get("image")
            needs_asset = index == 0 or s.get("new_scene") or s.get("coverage_cut") or bool(prior_start)
            if needs_asset:
                key = f"{ep}_{sid}_start"
                set_key = "set_" + digest(scene)[:12]
                assets.setdefault(set_key, {"kind": "scene", "references": [],
                    "prompt": "Empty set continuity master for a live-action Chinese drama. " + scene
                              + " Establish architecture, light sources, furniture and major props clearly. "
                              "No people, no collage, no captions or watermark. Keep geography reproducible."})
                action = next((b["action"] for b in s.get("beats", []) if isinstance(b, dict) and "action" in b), "")
                assets[key] = {"kind": "keyframe", "references": [f"cast_{k}" for k in s["in_frame"]] + [set_key],
                    "prompt": f"Create the opening still for a vertical live-action drama shot (4:7 portrait, "
                              f"target video 768x1344). Scene: {scene} Visible cast: "
                              + " ".join(book[k].split(";", 1)[0] + "." for k in s["in_frame"])
                              + f" Staging and action context: {action} Freeze the moment BEFORE the action; "
                              "this is one still image, no dialogue, no collage. Preserve reference identities, "
                              "costumes, set geometry and screen direction. No subtitles, logos or watermark."}
                s["start"] = {"mode": "asset", "asset": key}
            else:
                s["start"] = {"mode": "continue"}
            if s.get("last_frame"):
                end = f"{ep}_{sid}_end"
                assets[end] = {"kind": "keyframe", "references": [s["start"]["asset"]],
                    "prompt": f"Create the final still for this same shot. Preserve the reference's identities, "
                              f"costumes, set and camera axis. Final action: {s['beats'][-1].get('action', '')}. "
                              "Use natural posture and match the scripted prop positions. No text or watermark."}
                # Reusing one image at both ends is an intentional option, never the default.
                if s.get("last_frame") == prior_start:
                    s["end_asset"] = s["start"]["asset"]
                    del assets[end]
                else:
                    s["end_asset"] = end
            for key in ("first_frame", "last_frame", "anchor_image", "start_kf", "end_kf", "cast"):
                s.pop(key, None)
        plan.pop("opening", None)
        plan.pop("revision", None)
        plan["version"] = 2
        write(destination / "episodes" / ep / "plan.json", plan)
    write(destination / "project.json", {"version": 2, "name": source.name, "endpoint": "http://127.0.0.1:8001",
        "image_provider": "gpt-image", "image_execution": "built-in", "size": [1344, 768], "fps": 24,
        "output": "renders", "style": "Live-action Chinese drama, natural cinematic lighting, restrained believable acting."})
    write(destination / "cast.json", book)
    write(destination / "assets.json", {"version": 2, "assets": assets})
    validate(Project(destination))
    return len(plans), len(assets)


def export_jobs(project, destination, episode=None):
    validate(project, episode)
    wanted = set()
    for _, plan in project.plans(episode):
        for s in plan["segments"]:
            wanted.update(k for k in (s["start"].get("asset"), s.get("end_asset")) if k)
    ordered = []
    def add(key):
        if key in ordered:
            return
        for ref in project.assets[key].get("references", []):
            add(ref)
        ordered.append(key)
    for key in sorted(wanted):
        add(key)
    jobs = []
    for key in ordered:
        asset = project.assets[key]
        try:
            if project.asset_path(key, required=False):
                continue
        except ValueError:
            pass
        refs = []
        for ref in asset.get("references", []):
            try:
                path = project.asset_path(ref, required=False)
            except ValueError:
                path = None
            role = {"character": "authoritative identity and costume reference",
                    "scene": "authoritative set geometry and lighting reference",
                    "keyframe": "shot composition and end-state reference"}.get(project.assets[ref]["kind"], "visual reference")
            role = asset.get("reference_roles", {}).get(ref, role)
            refs.append({"asset": ref, "path": str(path) if path else None, "role": role})
        jobs.append({"id": key, "kind": asset["kind"], "prompt": asset["prompt"], "references": refs,
                     "execution": "built-in image_gen", "transparent_background": False,
                     "import_as": key})
    write(destination, {"provider": "gpt-image", "execution": "built-in", "jobs": jobs})
    return len(jobs)


def import_asset(project, key, source):
    from PIL import Image
    validate(project)
    identifier(key)
    asset = project.assets[key]
    source = Path(source).resolve()
    with Image.open(source) as img:
        img.verify()
    with Image.open(source) as img:
        width, height = img.size
        extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(img.format)
    if not extension:
        raise ValueError("Use PNG, JPEG or WebP")
    if asset["kind"] == "keyframe":
        h, w = project.config.get("size", [1344, 768])
        if abs((width / height) / (w / h) - 1) > .08:
            raise ValueError("Keyframe aspect differs from target by >8%; generate the intended composition first")
    sha = file_hash(source)
    reference_hashes = {ref: file_hash(project.asset_path(ref)) for ref in asset.get("references", [])}
    dest = project.root / "assets" / asset["kind"] / f"{key}-{sha[:16]}{extension}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source != dest:
        shutil.copy2(source, dest)
    asset.update(path=str(dest.relative_to(project.root)), sha256=sha, width=width, height=height,
                 provider="gpt-image", spec_hash=asset_spec_hash(asset), reference_hashes=reference_hashes)
    write(project.root / "assets.json", project.manifest)
    return dest
