---
name: continuous-video-drama
description: Produce and revise narrative video with GPT Image visual assets and MiniMax-H3 via LightX2V. Use for short dramas, script-to-shot planning, character and set continuity, keyframe preparation, video generation and targeted repairs. Supports deliberate coverage cuts and short within-shot continuations.
---

# GPT Image + MiniMax narrative production

Use GPT Image to establish the visual world and supply shot keyframes. Use MiniMax-H3 for motion,
acting, dialogue and native audio. Keep the screenplay, visual assets, shot plans and generated
media separate. This skill does not require a particular story, accelerator or fixed shooting style.

## Start from the user's scope

Distinguish workflow engineering, visual development and actual video production. A request to
refactor the workflow does not authorize rendering a season or rewriting its screenplay. Preserve
accepted scripts and takes. Preserve the user's output retention preferences; do not archive
rejected material when they asked to delete it.

Read a project's `production-policy.json` when present. If the user accepts model-generated
captions, continue production without caption-specific review gates, removal or rerolls.

For an existing project, inspect its current plans and media before changing them. Choose one
canonical working project instead of keeping edited copies of runners in production folders.
The self-contained CLI is `scripts/drama.py`; run `--help` to discover commands. It does not
start servers or generate images implicitly.

## The production loop

1. **Story and shot plan.** Treat the screenplay as an outline when the user permits adaptation.
   Write chronological action/dialogue beats. Decide cast visibility, listener, screen direction,
   props, opening state, closing state and camera movement for each shot.
2. **Visual bible.** Establish character appearance/costume references and useful set masters
   with GPT Image. Keep voices in `cast.json` and stable image references in `assets.json`.
   Reuse the original approved references rather than repeatedly editing drifted images.
3. **Shot keyframes.** Generate each new setup from those references. Establish geography,
   eyelines, person count and important props in the picture before asking video to animate them.
   A shot requiring a precise final state can have a separate end keyframe.
4. **Video.** Submit an explicit episode to MiniMax-H3. Use image-to-video for an opening frame,
   first/last-frame conditioning when both endpoints matter, and a previous clip's actual decoded
   tail only for a continuation of the same setup. Preserve voices and shot constraints.
5. **Review and repair.** Assemble a cumulative preview. Let the user review as production
   continues unless they requested a review gate. Repair the earliest affected shot and its true
   dependents; preserve accepted independent setups. Stop on unreadable output or failed tasks.

Visual continuity comes from common identities, costumes, geography and editing decisions.
Long frame chains are an option for an uninterrupted take; they are not the default structure for
an entire episode. A motivated coverage cut or reverse angle is valid filmmaking. Do not ban cuts,
force static cameras, or invent dialogue solely to satisfy limitations seen in an earlier run.

## GPT Image execution and asset handoff

Use the available built-in `image_gen` tool by default. Consult the `imagegen` skill when available.
No `OPENAI_API_KEY` is needed for this built-in path. This CLI prepares and imports files; a shell
process cannot directly call the conversation's image tool. Do not claim fully unattended image
generation from the Python CLI.

```bash
python scripts/drama.py --project /path/to/project prepare --episode ep01
# Read project/image-jobs.json. Generate the prerequisite references before shot keyframes.
# Use image_gen with each job's prompt and the relevant reference images.
python scripts/drama.py --project /path/to/project import-image ep01_01_start /path/to/generated.png
python scripts/drama.py --project /path/to/project check --episode ep01 --ready
```

`prepare` exports jobs in dependency order. A reference path may be empty until its prerequisite
has been generated and imported; re-run `prepare` to obtain the current paths. For local reference
images, inspect them before passing their paths to the built-in tool. Use the tool's actual supported
arguments; prompts, references, transparency and output handoff are not interchangeable options.
Save selected generated files into the project through `import-image`, never solely in a temporary
or conversation-owned directory. Imports preserve the original bytes and record hashes/provenance.

When repairing an image, state the edit target, each reference's role, the one requested change,
and invariants: identity, costume, composition, set, lighting and props. Do not regenerate an
entire shot when a small edit can preserve the accepted staging. Inspect the result before import.

Use an API/CLI image path only if the user explicitly chooses it. Consult the installed `imagegen`
skill's bundled CLI instructions instead of building a second API runner. Never silently substitute
a model or assume that ChatGPT image access provides API billing or an API key.

## Canonical project and commands

```text
project.json                 version 2; endpoint, native [height,width], fps, output root, style
cast.json                    ordered character keys -> appearance and voice descriptions
assets.json                  GPT image specs, reference dependencies and imported-file hashes
assets/                      durable approved/reference image files
episodes/epNN/plan.json      chronological shot plans (version 2)
renders/<run>/epNN/           video requests, states, actual tail frames and preview.mp4
```

For a new project, use [references/project-format.md](references/project-format.md) and
[scripts/plan.schema.json](scripts/plan.schema.json). For an existing version 1 project:

```bash
python scripts/drama.py migrate /path/to/current/production /path/to/empty/project
python scripts/drama.py --project /path/to/project check
python scripts/drama.py --project /path/to/project render --episode ep01 --dry-run
```

Migration copies plans and cast, creates fresh image specs, and leaves all original scripts and
media untouched. It does not import old provider images. Review generated image prompts and
inherited staging before production; structural validation cannot prove visual correctness.

The first shot, a scene change and a coverage cut use `start: {"mode":"asset","asset":"id"}`.
Within a setup, `start: {"mode":"continue"}` uses the previous clip's real last frame. An optional
`end_asset` adds a pinned end state. Do not reuse the opening image as the end state by default:
that can turn a natural action into an uncomfortable return-to-pose loop.

Explicit production command, after checking the server and accelerator availability:

```bash
python scripts/drama.py --project /path/to/project render --episode ep01 --run take01   --deadline 2026-11-15T22:00+08:00 --preview-every
python scripts/drama.py --project /path/to/project stitch --episode ep01 --run take01
python scripts/drama.py --project /path/to/project status --run take01
```

An omitted deadline means a one-hour budget. Naive deadlines use Asia/Shanghai. The runner locks
its output run, persists a task id immediately, reattaches pending tasks, and fingerprints prompts,
input-image bytes, endpoint and continuation dependencies. It rejects changed inputs in the same
run; use a new `--run` for a changed take. It does not blindly trust old `.last.png` files.
For a targeted repair, fork a new run with
`fork --episode ep01 --source take01 --run repair01 --from-segment 03`. It retains completed shots
outside the affected continuation chain; then render the repair run. Reuse is still checked against
the current inputs, so a changed retained setup is rejected rather than silently accepted.
An uncertain submission outcome requires reconciling server tasks before retrying. Task timeout
or deadline cancels an active task; an interrupted local process leaves its id available to resume.
The runner does not automatically retry failed generations or move into another episode.

For a bounded trial, add `render --count 2 --preview-every`. Only the first two clips are rendered;
later image dependencies may remain ungenerated. A partial run is recorded as `sample_completed`,
so a trial cannot silently mark the whole episode finished.

Rendering finishing does not unload the server. Release only the server you own when the user
has requested it; inspect ownership and the server process before stopping anything.

## Directing and model constraints

Read [references/directing.md](references/directing.md) for dialogue, eyelines, motion, audio and
review practices. Keep these distinctions clear:

- GPT Image specifies the still composition; MiniMax specifies how it changes over time.
- Full appearance and voice descriptors belong in every video prompt. Speaker ids stay stable
  across a project; do not derive them from a shot's cast order.
- Bind each line to one mouth and, when relevant, a listener. Off-screen speakers stay off-screen
  for that line; visible actors do not lip-sync it. Put speech only inside `<d>[Chinese] "..."</d>`.
- A silent shot is allowed. Explicitly request room tone and no vocalisation, then review it for
  invented speech. Do not rewrite the story merely to add a line.
- MiniMax-H3 frames: 158..362 with `frames % 17 == 5`. LightX2V's `size` is **[height,width]**;
  `[1344,768]` produces a 768x1344 portrait frame. Check the installed backend before porting.
- Pictures do not guarantee identity or motion accuracy. Inspect faces, hands, eyelines, prop
  state and joins; describe results as reviewed only when the media was actually viewed.
- Keep review previews clean. Add subtitles, titles and sound finishing in post as requested.
  GPT Image may generate cover art directly; there is no need to render a silent video for a cover.

## Scope of bundled tools

`scripts/drama.py`, `workflow.py`, `prompts.py`, and `video.py` implement the current workflow.
`stitch.py`, `convert_beats.py`, `audit_plans.py`, and `check_speech.py` are optional standalone
utilities for existing files; ASR is never required for ordinary production. `runner.py` points to
the current CLI and cannot launch the superseded unattended loop.
