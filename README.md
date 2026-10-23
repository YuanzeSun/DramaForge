# Frame-chained narrative video

Toolkit for producing multi-minute narrative video from a script with a frame-chained AI video
model — built against MiniMax-H3 served by LightX2V, but the structure ports to any backend with an
image-to-video endpoint.

General-purpose: nothing here is tied to a particular production. Per-show material (character
sheets, episode plans, anchor frames, covers) belongs in its own repo alongside this one.

## What's here

```
skills/continuous-video-drama/   drop into ~/.claude/skills/ to install as a Claude Code skill
  SKILL.md                       the method: what works, what fails, and why
  scripts/runner.py              frame-chained generation loop (resumable, deadline-aware)
  scripts/stitch.py              cumulative review preview
  scripts/plan.schema.json       annotated segment-plan format
  scripts/audit_plans.py         flag the defects that shipped broken video
  scripts/check_speech.py        transcribe finished segments against the script
bin/
  launch_server.py               start one multi-card LightX2V server
  stop_server.sh                 stop it and free the accelerators
  status.sh                      progress of a running job
  make_cover.py                  compose a 16:9 cover from a generated vertical frame
examples/
  server_8card.json              8x Ascend 910B, TP4xSP2, 8-step turbo LoRA
```

`SKILL.md` is the actual content. The scripts are a working reference implementation of what it
describes; read the skill first.

All paths in this document are relative to this folder, so the folder can be renamed or moved
freely. (`skills/continuous-video-drama/` keeps its name because a Claude Code skill's directory
must match the `name:` in its frontmatter — rename both together or neither.)

## The one-paragraph version

Generate each segment as image-to-video from the **previous segment's real last frame**. The set,
faces, costumes and lighting carry forward because they are literally the same pixels.
Independently generated shots cut together read as unrelated scenes, and no bridge, dissolve or
reference image fixes that after the fact. Write each segment as one chronological paragraph with
dialogue interleaved into the action, repeat every character's full description and voice in every
single segment, and let a human review the cumulative stitch while generation continues.

## Quick start

```bash
# 0. check nobody else is on the cards
npu-smi info          # or nvidia-smi

# 1. one server across all cards
./bin/launch_server.py --devices 0,1,2,3,4,5,6,7 --config examples/server_8card.json --logdir /tmp/run
curl -s http://127.0.0.1:8001/v1/service/status     # wait for "idle"

# 2. lay out a project somewhere of your own
mkdir -p ~/myshow/ep01
cp skills/continuous-video-drama/scripts/{runner.py,stitch.py} ~/myshow/
#    write ~/myshow/cast.json  -> {"alice": "<appearance>; she speaks with <voice>"}
#    write ~/myshow/ep01/plan.json per scripts/plan.schema.json

# 3. run it, with a deadline that also frees the cards
TOOLKIT=$PWD
cd ~/myshow
DRAMA_ROOT=$PWD \
DRAMA_DEADLINE=2026-10-24T08:00 \
DRAMA_SHUTDOWN="$TOOLKIT/bin/stop_server.sh" \
  setsid nohup python -u runner.py >> runner.log 2>&1 &

# 4. watch
DRAMA_ROOT=~/myshow $TOOLKIT/bin/status.sh
```

Previews land at `epNN/epNN_<title>_01-NN.mp4` and are rewritten after each segment.

## Environment variables

| variable | default | purpose |
| --- | --- | --- |
| `DRAMA_ROOT` | script's directory | holds `ep*/` and `cast.json` |
| `DRAMA_ENDPOINT` | `http://127.0.0.1:8001` | server base URL |
| `DRAMA_SIZE` | `1344,768` | native generation size (vertical 9:16) |
| `DRAMA_DEADLINE` | 24h from launch | `YYYY-MM-DDTHH:MM`, local clock |
| `DRAMA_SEGMENT_BUDGET` | `240` | don't start a segment within this many seconds of the deadline |
| `DRAMA_STYLE` | generic drama line | global style sentence |
| `DRAMA_SHUTDOWN` | unset | shell command run when the deadline stops the run |
| `DRAMA_CROP` / `DRAMA_SCALE` | `756:1344:6:0` / `720:1280` | stitch crop and output size |
| `DRAMA_FONT` | Droid Sans Fallback | CJK font for covers |
| `DRAMA_PYTHON` | `python3` | interpreter `status.sh` shells out to |
| `LIGHTX2V_ROOT` | `~/LightX2V` | LightX2V checkout |

## Porting to another machine

Needs: a LightX2V checkout whose `deploy_local/start_server.sh` honours `NPROC`, `PORT`,
`METRIC_PORT`, `CONFIG_JSON`; model weights; and a Python env with `av`, `requests`, `pillow`,
`numpy`, `imageio-ffmpeg`. Set `LIGHTX2V_ROOT` and fix `model_path` inside the config JSON. Nothing
else in this repo hardcodes a path.

## Operational notes worth not relearning

- **Stopping generation does not free the GPUs.** Pass `DRAMA_SHUTDOWN` or run `stop_server.sh`
  yourself — a run that halted exactly on its deadline still left an 8-card server loaded and idle
  for hours afterwards.
- **A running Python process holds the code it started with.** Edits to prompt-building take effect
  only after a restart. Restart at an episode boundary so no render is wasted.
- **Never match processes with `pkill -f` / `pgrep -f` on a loose pattern** — it matches its own
  command line too. Match an exact argv or keep a pidfile; both scripts here do.
- **Archive rejected output, don't delete it.** It is the evidence for what the next fix must
  change.
