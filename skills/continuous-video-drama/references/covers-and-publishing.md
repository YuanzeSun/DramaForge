# Covers and publishing

Use this reference when the user requests thumbnails, publication titles or release packaging.
Read their latest brief and project policy before generating variants; cancelled formats and
superseded layouts should not remain in the current delivery set.

## Artwork

Use approved cast and useful scene references, then describe each reference's role. GPT Image
creates the artwork, expressions, cutout treatment and Chinese typography. A screenshot of sample
covers is a style reference, not a request to reproduce its celebrities, brands or full collage.

Keep three layers distinct: the recognizable series label, the episode number and the episode's
visual hook. Judge the series label in a small thumbnail preview. Enlarging a small label does not
imply making it the largest element or adding a full-width header. Preserve the user's hierarchy.

Generate directly for the requested aspect whenever practical. If multiple formats must come from
one mother image, plan their shared safe area, then crop that same final PNG mechanically. Do not
regenerate a separate layout for each ratio and call it a crop. Inspect actual crops for clipped
heads, lettering and story props; adjust framing or the mother art when necessary.

## Exact export

```bash
python scripts/drama.py cover --episode ep01 \
  --source /project/covers/masters/ep01.png \
  --out /delivery/covers/4x3/ep01.png --record /delivery/covers/review/ep01-export.json
```

`--aspect` defaults to `4:3`; another format requires an explicit choice. `--crop X Y WIDTH HEIGHT`
can select a composition-preserving region. The exporter accepts RGB/RGBA PNGs, checks the crop
bounds and exact ratio, verifies output pixels against the mother, and writes hashes/provenance.
It never rescales or redraws text. Existing outputs require `--overwrite` for authorized replacement.

## Publication titles

Write a release title from the actual episode beats, independently from the cover headline.
Cover copy is short and visual. A release title can instead develop the character's predicament,
a mystery, a relationship or an emotional turn. The two may complement one another without using
the same sentence or even the same scene. Do not invent plot events, audience numbers or outcomes.
Keep episode order and series naming easy to recognize.

A project can keep `publishing.json` with per-episode `cover_copy`, `publishing_title`, `video` and
`cover` fields, plus a readable Markdown or CSV index. Delivering these files does not authorize
uploading or publishing to an external account.

## Built-in or API execution

Follow the user's current-session instructions to choose the account's built-in image tool or the
OpenAI Image API. Neither route is a repository-wide requirement. Session instructions override
saved project settings; past generation records describe existing assets, not future routing.
Do not silently switch routes. For an API choice, use the installed image-generation CLI or the
user's requested HTTP workflow. An SDK is
an optional client convenience, not an API requirement. Read `OPENAI_API_KEY` from a trusted local
environment/secret source; do not hardcode, echo or commit a key. A sample HTTPS edit request is:

```bash
curl --silent --show-error --limit-rate 3000000 --max-time 600 --config - \
  --form 'model=gpt-image-2.6-sunburst' --form 'image=@/project/covers/input.png' \
  --form 'prompt=</project/covers/prompts/ep01.txt' \
  --form 'size=1600x1200' --form 'quality=high' --form 'n=1' \
  --form 'output_format=png' > /project/covers/response.json <<EOF
url = "https://api.openai.com/v1/images/edits"
header = "Authorization: Bearer ${OPENAI_API_KEY}"
EOF
```

The response contains `data[].b64_json`; save its decoded PNG before exporting. Use a currently
supported model selected for the project; the sample model is not a universal latest-model claim.
The current example model is documented at https://developers.openai.com/api/docs/models/gpt-image-2.6-sunburst.
Record the requested model, size, quality, request id and usage when returned. Do not describe a
built-in tool's hidden model version as identical to the API version without evidence. A trial
request authorizes one comparison image, not automatic regeneration of an existing cover set.
Continue into a paid batch only when that batch has been explicitly authorized. Do not
automatically repeat an uncertain paid request or
silently substitute another model/execution path after failure.

## Delivery and shutdown

Keep one current cover per episode/format, the selected mother artwork, actual prompts and a
release-title index. Verify replacements before removing obsolete outputs. Preview sheets are
for inspection, not alternative final covers. Finish a requested service shutdown by checking
ownership, stopping only the production service and confirming that its port/workers are gone.
Do not start a local video service just to generate covers or export images.
