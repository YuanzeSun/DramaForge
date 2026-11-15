#!/usr/bin/env python3
"""GPT Image -> MiniMax-H3 production CLI. Local plans never invoke an image API."""
import argparse
import sys
from pathlib import Path

from workflow import Project, export_jobs, identifier, import_asset, migrate, read, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="directory containing project.json")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("migrate", help="copy existing plans into a clean version 2 project")
    command.add_argument("source")
    command.add_argument("destination")
    command = commands.add_parser("check", help="validate plans; --ready also requires imported keyframes")
    command.add_argument("--episode")
    command.add_argument("--ready", action="store_true")
    command = commands.add_parser("prepare", help="export dependency-ordered jobs for built-in image_gen")
    command.add_argument("--episode")
    command.add_argument("--out", default="image-jobs.json")
    command = commands.add_parser("import-image", help="copy a generated image into durable project storage")
    command.add_argument("asset")
    command.add_argument("file")
    command = commands.add_parser("render", help="explicitly render an episode, or inspect payloads with --dry-run")
    command.add_argument("--episode", required=True)
    command.add_argument("--run", default="main")
    command.add_argument("--deadline", help="ISO time; default zone Asia/Shanghai; default budget one hour")
    command.add_argument("--timeout", type=int, default=1200, help="per-task wall time in seconds")
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--preview-every", action="store_true")
    command = commands.add_parser("stitch")
    command.add_argument("--episode", required=True)
    command.add_argument("--run", default="main")
    command.add_argument("--count", type=int)
    command = commands.add_parser("fork", help="create a repair run, retaining independent completed shots")
    command.add_argument("--episode", required=True)
    command.add_argument("--source", required=True)
    command.add_argument("--run", required=True)
    command.add_argument("--from-segment", required=True)
    command = commands.add_parser("status", help="show registered images and tasks without contacting the server")
    command.add_argument("--run", default="main")
    args = parser.parse_args(argv)
    try:
        if args.command == "migrate":
            plans, assets = migrate(args.source, args.destination)
            print(f"MIGRATED {plans} episodes, {assets} image specifications -> {Path(args.destination).resolve()}")
            return 0
        project = Project(args.project)
        if hasattr(args, "run"):
            identifier(args.run)
        if args.command == "check":
            validate(project, args.episode, args.ready)
            print("READY" if args.ready else "PLANS VALID; images may still need generation/import")
        elif args.command == "prepare":
            count = export_jobs(project, project.root / args.out, args.episode)
            print(f"EXPORTED {count} jobs -> {project.root / args.out}")
        elif args.command == "import-image":
            print(import_asset(project, args.asset, args.file))
        elif args.command == "render":
            from video import compile_request, render
            if args.timeout <= 0:
                raise ValueError("--timeout must be positive")
            if args.dry_run:
                import json
                validate(project, args.episode)
                for ep, plan in project.plans(args.episode):
                    directory = project.output / args.run / ep
                    for i, s in enumerate(plan["segments"]):
                        print(json.dumps(compile_request(project, ep, plan, s, i, directory, dry=True), ensure_ascii=False))
            else:
                return 0 if render(project, args.episode, args.run, args.deadline, args.timeout, args.preview_every) else 2
        elif args.command == "stitch":
            from video import stitch
            if args.count is not None and args.count < 1:
                raise ValueError("--count must be positive")
            validate(project, args.episode)
            for ep, plan in project.plans(args.episode):
                stitch(project, ep, plan, args.run, args.count)
        elif args.command == "fork":
            from video import fork_run
            identifier(args.source)
            identifier(args.from_segment)
            fork_run(project, args.episode, args.source, args.run, args.from_segment)
        elif args.command == "status":
            imported = 0
            for key in project.assets:
                try:
                    imported += project.asset_path(key, required=False) is not None
                except ValueError:
                    pass
            print(f"IMAGES {imported}/{len(project.assets)} registered and current")
            for path in sorted((project.output / args.run).glob("ep*/*.state.json")):
                state = read(path)
                print(path.parent.name, path.name, state.get("status"), state.get("task_id", ""))
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
