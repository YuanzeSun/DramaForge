# DramaForge

A local short-drama workflow using **GPT Image for visual assets** and **MiniMax-H3 via LightX2V
for video and native audio**. Establish characters and sets, prepare shot keyframes, animate them,
and assemble review previews. Use deliberate coverage cuts and short continuations where useful.

The installed skill and CLI share one implementation. Production-specific scripts, images and
plans belong in a separate project; model weights and generated video never belong in this repo.

## Setup

Use an existing LightX2V Python environment, or install the workflow dependencies:

```bash
python -m pip install -r requirements.txt
python bin/drama.py --help
```

The image stage uses the conversation's built-in `image_gen` tool; it requires no OpenAI API key.
Python exports image jobs and imports results. It does **not** impersonate the conversation tool or
silently call a separately billed image API. MiniMax requires a running compatible LightX2V server
with a shared filesystem. The toolkit does not launch or stop accelerator services implicitly.

## Use

```bash
# Copy current plans and cast into a fresh project; preserve source plans and all existing media.
python bin/drama.py migrate /path/to/current/production /path/to/new/project
python bin/drama.py --project /path/to/new/project check
python bin/drama.py --project /path/to/new/project prepare --episode ep01
# Generate the exported jobs with built-in image_gen, importing references before keyframes.
python bin/drama.py --project /path/to/new/project import-image ep01_01_start /path/to/result.png
python bin/drama.py --project /path/to/new/project check --episode ep01 --ready
# Inspect requests without contacting a server, then explicitly render one episode.
python bin/drama.py --project /path/to/new/project render --episode ep01 --dry-run
python bin/drama.py --project /path/to/new/project render --episode ep01 --run take01   --deadline 2026-11-15T22:00+08:00 --preview-every
python bin/drama.py --project /path/to/new/project stitch --episode ep01 --run take01
```

`prepare` writes dependency-ordered `image-jobs.json` under the project. Complete each character or
set reference before generating its consumers; run `prepare` again to refresh reference paths.
Migration is a starting point: review inherited staging and the generated static-image prompts.
New projects can use the examples and format reference directly.

## Behavior

- A new setup starts from a registered keyframe; a continuation uses the previous clip's actual
  decoded tail. Optional end keyframes select `fl2av`.
- Prompt compilation includes stable speaker ids, appearance/voice descriptions, listeners and
  per-line mouth discipline. Silent shots remain possible and need audio review.
- Resumption checks request and image content, endpoint and continuation dependencies. Input
  changes in an existing run are rejected; select a new `--run` to preserve accepted takes.
- `fork --episode ep01 --source take01 --run repair01 --from-segment 03` retains independent
  completed setups while regenerating the affected shot and its continuations.
- Task ids persist immediately. An interrupted process reattaches; unknown submission outcomes
  require reconciliation. Failures stop the run without automatic rerolls.
- Rendering requires an explicit episode. Default runtime budget is one hour; a deadline without
  an offset uses Asia/Shanghai. A deadline/timeout cancels the active task; it does not unload the
  accelerator server. Stop only a service you own after production.
- Previews contain no added subtitles and apply one uniform crop/scale and audio leveling pass.
  Rejected-output retention follows the user's instruction; no mandatory archive is created.

## Files

- [Skill](skills/continuous-video-drama/SKILL.md): the production workflow and tool boundaries.
- [Project format](skills/continuous-video-drama/references/project-format.md): assets and plans.
- [Directing](skills/continuous-video-drama/references/directing.md): continuity, dialogue and review.
- `skills/continuous-video-drama/scripts/`: self-contained current CLI and optional utilities.
- `bin/drama.py`: repository launcher for the same CLI.
- `examples/`: project/plan examples and an 8-card inference configuration.
- `tests/`: offline integration tests with a local fake video service; no model calls.

Copy `skills/continuous-video-drama/` into `~/.codex/skills/` to install in Codex. The skill is also
usable in other agents that provide image generation and local shell access.
