# Project format v2

All image asset paths are relative to the project. Output paths may be relative or absolute.
`project.json` uses LightX2V's native `[height,width]` order, not conventional image `(width,height)`.
The CLI supports MiniMax-H3 through a local/shared-filesystem LightX2V server. The server must be
able to read imported images and write the configured output directory at the same absolute paths.
It does not upload input images to an arbitrary remote machine.

```json
{
  "version": 2,
  "name": "My show",
  "endpoint": "http://127.0.0.1:8001",
  "image_provider": "gpt-image",
  "image_execution": "built-in",
  "size": [1344, 768],
  "fps": 24,
  "output": "renders",
  "style": "Live-action drama, natural light and believable acting."
}
```

Optional `crop` and `scale` are ffmpeg expressions applied uniformly during assembly. The runner
uses the server's configured fps; set the server to match `fps` (24 for the provided H3 example).

For native-quality delivery, set `delivery_mode: "native_video"`. Matching source video streams
are copied into the assembled MP4 without resizing or video re-encoding; audio is leveled and
encoded separately. This mode requires identical source codecs, dimensions and frame rates.

`cast.json` is an ordered object of stable ids to descriptions, for example
`{"alice":"Alice, ...; she speaks with a warm adult female Mandarin voice"}`. Insertion order assigns
`S1`, `S2`, etc. Append new characters without reordering established entries.

```json
{
  "version": 2,
  "assets": {
    "alice": {"kind":"character", "prompt":"Character reference ...", "references":[]},
    "room": {"kind":"scene", "prompt":"Set master ...", "references":[]},
    "opening": {"kind":"keyframe", "prompt":"Opening still ...", "references":["alice","room"]}
  }
}
```

Allowed asset kinds: `character`, `scene`, `keyframe`, `cover`. References form a directed acyclic
graph. `prepare` orders prerequisites before consumers. `import-image` adds `path`, `sha256`,
`spec_hash`, width, height and provider. Changing an asset's prompt requires another import; imports
use content-based filenames to preserve original bytes and existing takes. A keyframe whose aspect
ratio differs from the intended frame by over 8% is rejected instead of silently cropping it.

Use optional `reference_roles: {"asset_id": "costume only; do not copy this person's identity"}`
to state a reference's exact purpose. `prepare` preserves these roles in exported jobs; a school
uniform reference must not accidentally become an identity reference for another character.

A plan has version 2, a title, an integer seed, optional default scene/cast and ordered `segments`.
Each segment has an id, H3 frame count, `in_frame`, optional `offscreen`, chronological `beats`,
and an explicit `start`. See `scripts/plan.schema.json` for the JSON Schema.

- `start: {"mode":"asset","asset":"opening"}` starts a setup using a GPT image.
- `start: {"mode":"continue"}` extends the preceding clip from its actual decoded final frame.
- `end_asset: "end_pose"` optionally supplies `last_frame_path` and selects `fl2av`.
- `coverage_cut: true` or `new_scene: true` requires an asset start.
- Optional integer `seed` overrides the episode seed plus segment index for this shot only.
  For a targeted reroll, change that shot's seed and fork from it into a new run; independent
  retained setups keep their existing inputs, while true continuations follow the new tail.
- `camera` and staging directions belong in action beats; `scene` can override the plan default.
- A dialogue beat uses `say`, `text`, optional `to`, `manner`, and `off` (per-line off-screen override).
- `soundscape` and `music` optionally override audio instructions for that segment.
- `quote_dialogue` defaults to true; false leaves spoken words directly inside the audio tags.
  `picture_rule` can replace the default no-text sentence for a controlled prompting comparison.
  Neither option guarantees that the video model will suppress burned-in captions; review output.

There is no hidden text-to-video fallback: a missing keyframe blocks real rendering. `render
--dry-run` emits inspectable payloads with unresolved `<asset:id>` placeholders and contacts no
server. `check` validates structure; `check --ready` additionally checks image files and their hashes.
These checks do not approve acting, geography or image quality.
