# Shot design and review

## Visual development

A character bible should fix face, age, hairstyle, wardrobe and accessories. Separate identity from
performance: a new expression or angle does not imply a redesign. A set master should establish
entrances, windows, furniture, light sources and the camera axis. Generate each coverage keyframe
using the approved character and set masters. Compare the resulting geography before animation.
Describe the initial visible state rather than asking a still image to depict a whole action sequence.

Use only the required references for each shot. Too many unrelated images can introduce people,
props or costumes from another setup. When editing, identify the target and the authoritative
reference for identity or space. Preserve accepted scene geometry while changing the requested detail.

## Script and staging

Interleave action and dialogue in temporal order: a hand reaches, a warning is spoken, the hand
stops, the listener answers. Start with a small visual beat so speech does not begin at a clipped
frame zero. Short exchanges generally survive synthesis better than long written monologues;
split them at natural breaths when the user allows dialogue adaptation.

For each line, name the speaker, the intended listener and the performance. In a two-shot, turn
face, shoulders and gaze toward the listener. For an off-screen line, state that the speaker is not
visible and that the visible characters keep their mouths closed. Never place an off-screen
speaker in the keyframe just to make the audio prompt easier.

Keep visual appearance descriptions limited to visible characters. For a truly off-screen speaker,
use their name and voice descriptor only; do not repeat their face, hairstyle and costume as if
they should be rendered in the background. A silent person outside the crop needs no visual block.

Maintain an axis table when several angles share a room: who stands on which side, where each
looks, and which doorway each uses. Exiting the crop is different from exiting the room.
Important props must exist in the opening frame, with a plausible hand/owner/state. Never refer
to a small unreadable detail in several lines and hope the video model will invent it correctly.

Some cast entries represent groups. Count visible people from actual staging, not merely the
number of cast keys. Generic constraints must not suppress people required by the shot.

## Camera and motion

Pick camera movement that fits the dramatic beat. A static setup is useful for comparison or a
quiet exchange, but an entire episode need not be locked. Keep gestures, breathing and blinking
natural even when both endpoints match. Avoid prescribing a tiny handheld float alongside a
contradictory instruction that the camera is completely static.

Continue a real last frame when the next clip extends the same action/angle. Use a deliberate
coverage cut for a new angle. Long chains can accumulate identity and texture drift; cut or
re-anchor from approved originals when the material calls for it. A synthetic bridge cannot be
assumed to reconcile incompatible sets. If the actual tail is blurred or fading, trim the source
clip and extract the new tail before continuing; never silently replace a seam with another frame.

## Audio and text

Keep voice descriptions and speaker ids stable across the project. H3's three prompt sections are
`integrated_multimodal_description`, `overall_soundscape`, and `non_diegetic_music`. Dialogue tags
contain only the spoken words and language marker; performance direction stays outside them.
Check model-local prompt guides when changing the backend, since conventions are model-specific.

Silence has previously produced invented speech in this production. Treat that as a review concern,
not a reason to make every character talk. State no speech or vocalisation and room tone only.
For an intended silent shot with unusable audio, retaining the visual and replacing ambience in post
may be appropriate if the user accepts it. Garbled required dialogue needs a repaired take.

Request no model-rendered subtitles or watermarks. Make important signage and titles in post when
exact text is required. GPT Image cover lettering can be inspected separately; do not assume video
and image text capabilities are identical. Do not add subtitles to the user's delivery by default.

If captions persist, repeated stronger prohibitions can still fail. A bounded comparison can use
unquoted dialogue inside the audio tags (`quote_dialogue: false`) and a simple positive camera
description (`picture_rule`). Check both the resulting picture and speech rather than assuming
the change fixed either. Follow the current project policy for rerolls. When caption-free footage
is required, regenerate the affected clip before continuing from its tail. An explicit waiver for
an earlier episode does not waive later production. After repeated failures, change the shot
strategy instead of blindly repeating the same request; report unresolved captions truthfully.

## Human review and bounded repairs

A cumulative preview exposes seams better than individual clips. Review identities and wardrobes,
who is visible, speaker/listener gaze, entrances/exits, background extras, props, camera direction,
audio and joins. If the user asks to approve an episode before proceeding, finish that review first.
Otherwise avoid serial ASR and automated scoring that stall useful work without demonstrated value.

Record actionable defects briefly: shot, visible evidence, expected state and smallest repair.
After two or three unsuccessful attempts, change staging or the repair strategy instead of blindly
rerolling. A repair to one chained tail invalidates its continuations; a later independent keyframe
is a dependency boundary. Keep accepted takes and use a new run for changed inputs. Respect the
user's choice to delete rejected images, videos and logs; no mandatory archive policy applies.

## Local accelerator service

Check `npu-smi info` or `nvidia-smi` and process ownership before starting a server. For a single
frame chain, one large multi-card server may be faster than multiple smaller workers; measure on
the target setup. Historical 8x910B measurements are examples, not guarantees.

Read the actual adapter metadata for LoRA alpha/strength. A mismatched adapter alpha once corrupted
renders. Do not apply an example's value to another adapter. The bundled example uses TP4 x SP2,
8 steps and alpha 8 for its named adapter. Service stop is separate from generation completion;
stop only known owned processes, never a broad system-wide name match.
