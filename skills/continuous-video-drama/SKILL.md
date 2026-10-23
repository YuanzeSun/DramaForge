---
name: continuous-video-drama
description: Produce a multi-minute continuous narrative video (short drama, explainer, any dialogue scene) from a script using a frame-chained AI video model such as MiniMax-H3 on LightX2V. Use when the user asks for video longer than the model's single-clip limit, when separately generated shots look like unrelated scenes cut together, or when setting up a segment-by-segment generation pipeline on multi-GPU/NPU hardware.
---

# Continuous video drama

A video model generates 5–15 seconds at a time. A drama needs minutes. The gap between those two
facts is the whole problem, and almost every mistake below comes from solving it the
obvious-but-wrong way.

Findings are marked **[verified]** where this pipeline hit them directly, **[reported]** where they
come from published practice. Verified beats reported when they conflict.

## The core method: frame chaining

**Generate segment N+1 as an i2av (image-to-audio-video) continuation of segment N's actual last
frame.** Extract the final frame of each finished clip, pass it as `image_path` for the next
request, and the room, faces, costumes and lighting carry forward because they are literally the
same pixels.

What does not work, in order of how tempting it is:

1. **Generating shots independently from the same character reference, then cutting them
   together.** [verified] Faces and costumes stay roughly consistent; the set does not. The door
   moves, the window changes, the telescope is a different telescope. A viewer reads every cut as
   a scene change: *"片段拼接非常生硬，画面不是连续的，直接换幕了"*.
2. **Patching existing clips with first-frame/last-frame bridges.** [verified] Give the model the
   end of clip A and the start of clip B and ask for the motion between them. It invents whatever
   it needs to reconcile two incompatible spaces — in testing it panned to a blank wall, changed
   the telescope, and added a student who existed in neither clip.
3. **Crossfades and dissolves.** Hiding a discontinuity is not continuity. (Though see
   *Scene breaks* below — practitioners disagree about dissolves, and the disagreement is real.)

Frame chaining costs parallelism: segment N+1 needs segment N finished. Spend the freed capacity on
one larger server instead (see *Hardware*).

### Chain length and drift

Two distinct failures hide under "it degrades" [reported]:

- **Extension decay** — texture and colour degrade *within* a continuing shot, because each link
  conditions on a re-encoded lossy render. Errors compound multiplicatively.
- **Identity drift** — faces slowly change *across* shots. [verified: by segment 7–8 of a 9-segment
  chain the teacher reads as a different, older actor than in segment 1.]

Cures differ. Decay is cured by cutting rather than extending; drift is cured by re-grounding. The
strictest published rule is **chain length of one — never extend an extension**; looser practice
allows 2–3 links then a hard reset. This pipeline chains 8–10 segments and visibly pays for it.

**Re-anchor from the original master, never from the drifted frame** [reported] — repairing a
repaired frame accumulates new drift within 3–4 iterations. The hybrid worth trying: last frame →
image-edit pass with the character master attached → use the repaired frame as the next input.
Use a single-variable repair prompt: *"the master is the sole identity standard; everything is
already correct except the face shape; fix only that; keep composition, scene, pose, costume and
lighting unchanged; no redesign, no added accessories."* Fixing one defect at a time preserves what
is already right better than rerolling.

**Frame extraction hygiene** [reported]: don't take the literal final frame — many models end on a
fade or a motion-blurred in-between. Seek ~0.1–0.5 s before the end (`ffmpeg -sseof -0.5`) and
write a **lossless PNG at native resolution**; JPEG edge artifacts amplify downstream. (Checked on
this pipeline's output: no end-of-clip fade, luminance stable, so the literal last frame was
usable — but verify rather than assume.)

## Writing a segment

### Beats, not action-then-dialogue

The single highest-value prompt change in this project. [verified] The first format described all
the action, then listed dialogue at the end:

```
<action paragraph>  Chen says: <d>[Chinese] 别碰。</d>  Lin says: <d>[Chinese] 啊，抱歉抱歉。</d>
```

The model cannot tell which action goes with which line. The result was a boy saying "don't touch"
to a teacher who was not reaching for anything, who *then* reached. Interleave instead — one
chronological paragraph, each line sitting between the action before it and after it:

```
Her hand reaches toward the note. Just before her finger touches it, Chen (S1) turns his head and
says sharply: <d>[Chinese] 别碰。</d> Her hand stops in mid-air and pulls back without touching it.
Lin (S2) says in an off-screen voiceover: <d>[Chinese] 啊，抱歉抱歉。</d> while Chen's lips remain
completely closed.
```

Then append: *"Everything happens in exactly the order described."*

### The frozen identity paragraph

**Every segment must carry the full description of every character in it, including a voice
descriptor — continuations included.** [verified, the hard way] Carrying only the speaker ids
`(S1)`/`(S2)` into continuation prompts, with descriptions only in the opening text-to-video
segment, made the model guess voices: the female teacher spoke an entire scene **in a man's
voice**. The description block belongs in the prompt for every segment, byte-identical each time
[reported: a "frozen identity paragraph" with only the action lines changing]:

```
Lin Zhixia, a 24-year-old Chinese female teacher with shoulder-length straight black hair, wearing
a pale blue cardigan over an ivory blouse; she speaks with a natural warm adult female Mandarin voice.
```

Keep it in a `cast.json` the generator reads **fresh on every call**, so adding a character never
requires restarting a long run.

### Say who is being spoken to

[verified] "Lu holds the card out toward Chen, who is off-screen right, and says: …" produced a man
delivering his offer to the wrong person entirely — the viewer reads him as talking to whoever is
on screen. Put both parties in frame and name the target inside the dialogue instruction:

> Lu turns his back on Lin and crouches to the boy's eye level, so the camera frames Lu and Chen
> together. Lu (S4) speaks **directly to Chen, looking at Chen's face the whole time**: …

### Follow the model's prompt conventions

MiniMax-H3 ships `docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md` and `..._ref_en.md` in the model
directory. Read them. What mattered:

- `<d>[Chinese] …</d>` wraps **only** the spoken words; speaker, delivery and action stay outside.
- Stable speaker ids `(S1)`, `(S2)`, `(S3)` — assign once, reuse across the whole production.
- For off-screen lines use the exact phrase **`says in an off-screen voiceover`**, then state
  immediately that the on-screen character's lips remain closed. Without this the visible actor
  lip-syncs someone else's dialogue. [verified]
- On-screen text in double quotes: `a sticky note reading "今晚晴"`.
- Three sections: `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`.
- **Keep the spoken line in quotes on H3** [reported] — its native-audio guidance says unquoted
  lines degrade to mumbled syllables. (Google's Veo docs advise the opposite, no quotes, to avoid
  triggering text rendering. Resolve per model; don't port the convention blindly.)
- **Prompt expansion is on by default and rewrites what you wrote** [reported]: it inserts
  amplitude, speed, shot labels and timecodes whether or not you asked. Write amplitude and speed
  yourself to keep the decision. Three actions joined with "then" came back as three real cuts —
  always state "one continuous shot, no cuts" for a chained segment.

### Motion constraints are load-bearing

[reported, and consistent with what this pipeline saw] Omitting an explicit motion-constraint
section is what lets the model improvise: heads turn, **extras walk through the background**,
intended near-stasis evaporates. A six-block segment structure: subject & composition → material &
light → **motion constraints** → camera → atmosphere → negative. Pin speed adjectives explicitly.

[verified] Extra people appearing is the single most common content failure here: a pull-back for a
three-person group shot added four or five students by the second half of the clip; a bridge test
invented a student who was in neither source clip. Write "only these three people are in the room;
no other students" and still expect to pick frames from the early part of the clip.

### Counted beats, not verbs

[reported] "Actor walks across the room" → "Actor takes four steps to the window, pauses, and pulls
the curtain in the final second." Same for environment: "a beautiful street at night" → "wet
asphalt, zebra crossing, neon reflecting in puddles." This is a better expression of "prompt for
brisk pacing" than any adjective.

[verified] Pacing still needs stating outright. The first cut had 16 seconds of silence in 38
seconds of footage, because the model inserted slow camera moves between lines. Add: *"brisk,
natural everyday conversation like real people talking, each line starts right after the previous
one, no long silent pauses"* and *"finish all speech by half a second before the end"* so the clip
does not end mid-word. Post-production cannot recover that; only the prompt can.

### Camera vocabulary

[reported] Bracketed director tags — `[Push in] [Pull out] [Pan left/right] [Truck left/right]
[Tracking shot] [Static shot]` — placed **immediately after the description they apply to**, not at
the end. One move per clip; stacking them produces mush. Camera is static by default, but you must
still write "static camera, locked shot" to stop slow drift. Don't prompt a wide move from a
close-up input — it forces the model to invent off-frame bodies and produces anatomy errors.

### If the camera cannot see it, do not write dialogue about it

[verified] A sticky note on the telescope tube was referenced by four lines of dialogue. The
framing cropped the tube out, so the note was never visible and an actor appeared to point at
nothing and discuss it at length. Two regenerations with explicit "the note is clearly visible in
the left-centre of the frame" did not fix it reliably. The fix was to **cut the prop from the
script** — the scene became a short exchange about the telescope itself, visible in every frame,
carrying the same plot beat in two lines.

Before writing a prop into dialogue, check the incoming chain frame. If the object is not in it,
either rewrite the beat around something that is, spend a segment re-framing onto the object, or
composite it in post. Never hope.

### Treat the script as a story outline

[verified] Written dialogue is usually too formal and too slow when spoken by a generated actor:
*"不用和剧本一句不差的拍……剧本只是大致故事线，可以改"*. Rewrite for speech — contractions,
interruptions, filler, short replies; split one long formal line into two short exchanges. Keep the
plot beats and the jokes, discard the phrasing. Also drop running gags the client dislikes
*everywhere*, including callbacks in later episodes.

[reported] Duanju conventions worth knowing as a band, not a spec: hook with the conflict in the
first 3 seconds; a reversal roughly every 20 s; shot length 3–8 s; episodes 45–90 s; **single
dialogue lines ≤15 Chinese characters**; convert narration into dialogue and action.

## Frame counts and duration

MiniMax-H3 requires `num_frames ≡ 5 (mod 17)` — 158, 175, 192, 209, 226 … up to 362. At 24 fps that
is ~6.5–15 s. Assert this when building the plan; the server rejects anything else. Other models
have their own quantisation — find it before writing the plan.

[reported] Single shots beyond ~8 s drift regardless of technique, and timecodes are "a plan, not a
guarantee" — a line scheduled at 3.5 s landed at 5.8–6.4 s. Give early lines early timecodes and
keep preceding action brief.

## Scene breaks: when a cut is correct

Not every cut is a defect. The objection is to hard cuts *inside one continuous conversation*; a
genuine change of time or place is ordinary editing. Give the segment a `new_scene` flag that
restarts the chain with a text-to-video prompt and its own scene description.

[reported] Chain when a slow push-in or held beat would make a cut obtrusive, or you need 2–3 more
seconds of the same action. Cut when the beat runs past ~2× the model's comfortable clip length,
when faces or hands are large in frame, or when you are already one extension deep. **Cut on
action** — end A as the hand reaches the door, begin B with the door already moving.

Transition style is genuinely contested: one camp says straight cuts only, because dissolves draw
attention to the differences you are hiding; Chinese duanju practitioners recommend dissolves
precisely *because* the overlap blurs small identity differences. Test both on your material.

[reported] Also write a **screen-direction table** before generating (who moves left-to-right,
who enters from which side) and treat an axis flip as a continuity defect to fix in one frame,
not by regenerating the pair.

## Pipeline design

### Generate continuously, let the human review

[verified] The strongest workflow instruction in this project: *"你把方法探索差不多后，可以不用反复
检查了，你大部分时间浪费在检查上了；可以让我检查，然后你先继续下一步"*.

- Finish segment N → immediately submit N+1 → **in parallel**, stitch 1..N into a cumulative
  preview and report the path.
- No speech recognition, dual-candidate generation or automated scoring. An earlier version
  transcribed every clip with Whisper and compared pinyin similarity; it roughly doubled
  wall-clock time and never caught a problem the human did not catch faster by watching.
- Stop only for hard failures: task failed, file unreadable, server down.
- On an interruption: cancel the in-flight task, archive rejected segments to `rejected/` (never
  delete — they are the evidence for what the fix must change), fix the plan, restart from the
  first bad segment.

The cumulative preview matters more than per-segment files: continuity problems live at the seams.

[reported] If you *do* review systematically, two gates are worth stealing: an A-grade rate below
~30% of a batch means the prompt is the problem, not the volume; and failures should cluster in
known weak spots (hands) rather than faces. Declare an attempt ceiling before starting — after 2–3
failures change the approach rather than rerolling blind. Budget ~3 generations per usable shot.

### Make everything resumable

Write `<id>.request.json` and `<id>.state.json` beside every clip. On restart, skip any segment
whose extracted frame already exists, and re-attach to a task still `processing` rather than
submitting a duplicate. [verified] Restarts happen constantly — every interruption is one, and
re-attach saved several completed-but-unclaimed renders here.

Give long unattended runs a **deadline** and a per-segment budget, so the loop stops cleanly
instead of being killed mid-render.

### Caution when editing a running pipeline

[verified] A running Python process holds the code it started with. Two classes of bug came from
that: prompt-building fixes that silently did not apply until restart, and `pkill -f`/`pgrep -f`
patterns **matching their own shell command line**, killing the wrong process and leaving the
runner dead with the server still rendering. Match on an exact argv, or keep a pidfile.

## Hardware

Frame chaining is sequential, so per-segment throughput is what matters, not parallel jobs.

- **One big server beats two small ones.** [verified] Two TP4 workers across 8 cards took ~390 s
  per segment; one TP4×SP2 server across all 8 took ~120 s. The second worker was only useful for
  generating two candidates of the same segment, which the client did not want.
- Check attention heads divide by tensor-parallel size (MiniMax-H3 has 56 heads; TP4 and TP8 both
  work). Combine tensor with sequence parallelism to use the remaining cards.
- **Check who else is on the accelerators** before launching (`npu-smi info` / `nvidia-smi`).
  A root-owned vLLM server appeared mid-project taking ~22 GB per card. Never kill another user's
  job; ask, or fit alongside it.
- An 8-step distillation LoRA cut inference ~3.5× with no visible quality loss at 768p. Read the
  LoRA's own metadata for its `alpha` — this one wanted 8, while the widely-copied example config
  used 128, which produced corrupted output until corrected.
- Seeds: usable on local inference (LightX2V/ComfyUI). [reported] Hosted H3 exposes no seed
  control, so every hosted rerun is a fresh take.

## Assembly and post

Stitch with a single ffmpeg `concat` filter, applying **one identical crop to every segment** —
never a per-segment crop or zoom, which reintroduces the cut-to-cut feeling that frame chaining
exists to avoid. Generate at native resolution (768×1344 here) and scale once at the end; don't
call the upscaled output "native".

Keep subtitles and composited text out of review previews; add them only to the final master and
keep a clean master without them. Burned-in text cannot fix wrong audio — if a line is garbled,
regenerate the segment.

**All on-screen text goes in post.** [verified] Model-rendered Chinese is unreliable; phone
screens, signage and notes should be composited as a small inset over the continuing shot rather
than a cut to a full-screen graphic.

**The model may burn in its own subtitles anyway.** [verified] Three of nine segments came back
with captions despite an explicit prohibition. [reported] Escalation hierarchy: use a real negative
prompt field if the model has one (H3 does not — constraints must be plain sentences); place the
constraint **immediately after the spoken line**, not at the end of a long paragraph; escalate
phrasing from `no subtitles` to `clean frame, no words on screen, no burned-in text`; budget an
inpainting text-remover as fallback. For Wan-family models keep the negative prompt **in Chinese**
(`字幕` is the load-bearing token) and note negative prompts do nothing at CFG=1, so distilled
4-step configs ignore them silently.

[reported] Post order: upscale → deflicker/denoise → LUT for a unified grade → frame interpolation
at **1× only**. Mix dialogue ~6 dB above music; H3 output measured around −41 dB mean, so plan a
levelling pass. Limit to 3–4 distinct sounds.

## Covers and titles

With no image-generation tool, the video model *is* the image generator. [verified] Generate a
short **silent** clip for the key art — a prompt with no dialogue at all also avoids the burned-in
subtitles — then pick a frame and compose the cover with PIL. Draw all type in post. Check what CJK
fonts actually exist: with only a regular weight available, synthesise weight with stroke
rendering, and ask for a heavy font if the result needs to read as a poster.

## Files

- `scripts/pipeline.py` — frame-chained generation loop with resume and background stitching.
  Edit `ENDPOINT`, `SIZE`, `SCENE` and the cast block for your model and scene.
- `scripts/stitch.py` — cumulative preview assembly.
- `scripts/plan.schema.json` — the segment plan format, annotated.

The scripts assume a LightX2V-style HTTP API (`POST /v1/tasks/video/`, `GET /v1/tasks/{id}/status`,
`DELETE /v1/tasks/{id}`). Swap the three request functions for another backend; the structure is
unchanged.

## Sources for the [reported] items

MiniMax-H3 native audio guide (omniart.studio), H3 prompt measurements (fuser.studio), AI video
extension quality loss (screenweaver.ai), keyframe consistency for AI short drama (seektik.com),
Hailuo 3 prompt structure field notes (v2ex.com/t/1232829), Wan negative-prompt behaviour
(WanGP issue 1631, ambienceai.com), Veo dialogue conventions (prompt-architects.com), Sora
prompting guide (developers.openai.com), duanju shot/transition practice (bjxku.com, jxxy.net),
iterative generative drift research (arXiv 2605.20476, 2607.15772, 2512.07328).
