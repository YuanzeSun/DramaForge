"""MiniMax-H3 prompts: stable voices, explicit listeners and image conditioning."""


def name(book, key):
    return book[key].split(",", 1)[0].strip()


def dialogue(beats, visible, offscreen, book, speaker_ids, quoted=True):
    result = []
    for beat in beats:
        if "action" in beat:
            result.append(beat["action"])
            continue
        key = beat["say"]
        speaker = name(book, key)
        manner = f", {beat['manner']}" if beat.get("manner") else ""
        target = beat.get("to")
        facing = ""
        if target:
            listener = name(book, target)
            facing = (f"{speaker} addresses {listener} directly, keeping the established screen direction. "
                      + (f"The speaker's face, shoulders and eyes are directed toward {listener}. "
                         if target in visible and key in visible and not beat.get("off") else ""))
        spoken = f'"{beat["text"]}"' if quoted else beat["text"]
        line = f'<d>[Chinese] {spoken}</d>'
        if key in visible and not beat.get("off"):
            result.append(f"{facing}{speaker} ({speaker_ids[key]}) alone speaks{manner}: {line}. "
                          f"Only {speaker}'s mouth moves in sync with these words.")
        else:
            result.append(f"{facing}{speaker} ({speaker_ids[key]}) says in an off-screen voiceover{manner}: "
                          f"{line}. The speaker is outside the frame for this line; nobody visible lip-syncs it.")
        quiet = [name(book, k) for k in visible if k != key or beat.get("off")]
        if quiet:
            result.append(f"{' and '.join(quiet)} remain silent with mouths closed during this line.")
    return " ".join(result)


def video_prompt(project, plan, segment, chained=False):
    visible, off = segment.get("in_frame", []), segment.get("offscreen", [])
    who = " ".join(f"{project.cast[k]} ({project.speakers[k]})." for k in dict.fromkeys(visible))
    # Describe off-screen speakers as sound only. Their full appearance/costume block can
    # otherwise prompt the model to insert a background actor who is meant to stay unseen.
    speaking_off = [k for k in dict.fromkeys(off) if any(b.get("say") == k for b in segment["beats"])]
    for key in speaking_off:
        voice = project.cast[key].partition(";")[2].strip() or "a natural off-screen voice"
        who += f" Off-screen AUDIO ONLY: {name(project.cast, key)} ({project.speakers[key]}), {voice}."
    head = ("Continue the next moment from the previous clip's actual final frame, with no cut. " if chained
            else "Begin exactly at the supplied opening keyframe. ")
    head += "Preserve the supplied face identities, costumes, set geometry, lighting and prop positions. "
    if segment.get("end_asset"):
        head += ("The supplied final keyframe defines the end state; move naturally between both frames. "
                 "Allow natural blinking, breathing and restrained gestures between them. ")
        if segment["start"].get("asset") == segment["end_asset"]:
            head += "The endpoint compositions are identical; this is a held setup, not a frozen still or a looping action. "
    body = dialogue(segment["beats"], visible, off, project.cast, project.speakers,
                    quoted=segment.get("quote_dialogue", True))
    picture_rule = segment.get("picture_rule", "Clean picture: no captions, subtitles, burned-in dialogue, logos or watermark.")
    silence = ""
    if not any("say" in b for b in segment["beats"]):
        silence = "No speech, murmuring, whispers, singing or vocalisations. Closed mouths, physical sounds and room tone only. "
    elsewhere = ""
    if speaking_off:
        elsewhere = ("Voices outside this camera view: " + ", ".join(name(project.cast, k) for k in speaking_off)
                     + ". Keep these speakers outside the image; no visible person lip-syncs their lines. ")
    return ("For the target video, at 0.00 seconds, <Picture 1> is fully referenced.\n\n"
            "integrated_multimodal_description: [Shot 1] " + project.config.get("style", "Live-action drama.")
            + " " + segment.get("scene", plan.get("scene", "")) + " " + head + who + " " + body + " "
            + elsewhere + silence
            + f"Only these visible cast members appear: {', '.join(visible) or 'none'}. No unplanned extras. "
            "One continuous take inside this segment. Keep the scripted camera motion; no unscripted cuts or zooms. "
            "Natural conversational pace, no long pauses; finish speech at least half a second before the end. "
            + picture_rule + "\n\n"
            "overall_soundscape: " + segment.get("soundscape", "Continuous room tone, natural physical sounds; no background speech.")
            + "\n\nnon_diegetic_music: " + segment.get("music", "N/A"))
