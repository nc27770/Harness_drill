# Module 1k — Asset-conditioned image OUTPUT

**Goal:** close three cells the dispatcher previously refused —
`(image, image)`, `(audio, image)`, `(video, image)` — with one module
that holds two distinct internal paths. The lesson is **edit when you
can, translate when you must**: the choice depends on input modality,
not on the composer.

```
( image, image )   "remix this image"           → Path A (edit)
( audio, image )   "draw what this song is about" → Path B (translate)
( video, image )   "render the closing frame as an oil painting" → Path B (translate)
```

1k is the symmetric companion to 1i. 1i covers `(text, image)`. 1k
covers every non-text input that ends in image.

## The two paths

### Path A — edit (input modality is image)

The asset goes directly to the composer's edit endpoint:

- **OpenAI:** `client.images.edit(model="gpt-image-1", image=…, prompt=…)`
- **Google:** Gemini's image model interprets a `(image_bytes, prompt)`
  pair as in-context edit; the asset is added as a part to the
  multimodal content.

The parser still runs, but with an EDIT-shaped brief
(`PARSER_SYSTEM_EDIT`): subject observed, intent, what to preserve,
what to change, negatives, safety flags. The brief rides alongside the
image in the edit call.

### Path B — translate (input modality is audio or video)

There is no edit endpoint that accepts audio or video. So the parser's
job changes shape: it **observes the asset and translates it into a
visual brief** (`PARSER_SYSTEM_TRANSLATE`). The composer then runs
text-only generation from that brief. The asset never reaches the
image generator.

This is the key lesson of 1k. For non-image asset → image-out, the
*parser* is doing modality conversion, not the composer. The composer
sees text only.

`--edit-mode` controls this:

- `auto` (default): edit when input is image, translate otherwise.
- `edit`: force edit endpoint (errors on non-image input).
- `generate`: force translate path even on image input — useful for
  comparing what the edit endpoint does vs what a brief-only render
  produces from the same image.

## What's new vs Module 1i

| Aspect | 1i | 1k |
|---|---|---|
| Input modalities | text only | image, audio, video |
| Parser-side capability gate | none (text always works) | yes — anthropic excluded from audio/video; openai excluded from video; mirrors 1h |
| Composer endpoint | `images.generate` only | `images.edit` (Path A) **or** `images.generate` (Path B) |
| Parser system prompt | one (image brief) | two (edit-brief vs translate-brief) |
| Composer prompt | parser IR | user prompt + parser IR (edit endpoint benefits from both) |
| `--all` sweep | 14 cells (6 parsers × 2 composers + 2 baselines) | dynamic — only iterates parsers eligible for the detected input modality |

## Setup

No new deps. Reuses 1i's OpenAI and Google SDKs and 1h's `assets.fetch()`.

## Run

```sh
# (image, image) — true edit
.venv/bin/python level_1_modules/module_01k_image_edit/bilateral_k.py \
  --asset ./red_apple.png \
  --parser anthropic-deep --composer openai-image \
  --quality low \
  "Remove the wooden table and replace it with a marble countertop. Keep the apple identical."

# (audio, image) — parser translates audio → visual brief
.venv/bin/python level_1_modules/module_01k_image_edit/bilateral_k.py \
  --asset s3://harness-eng/inputs/podcast.mp3 \
  --parser openai-deep --composer google-image \
  "Render an album-cover-style image that captures what this audio is about."

# (video, image) — google-only parser side
.venv/bin/python level_1_modules/module_01k_image_edit/bilateral_k.py \
  --asset s3://harness-eng/inputs/clip.mp4 \
  --parser google-deep --composer openai-image \
  --quality low \
  "Render the emotional climax of this clip as a cinematic still."

# Compare edit vs generate on the same image input
.venv/bin/python level_1_modules/module_01k_image_edit/bilateral_k.py \
  --asset ./apple.png --edit-mode generate \
  "Replace the table with a marble countertop."

# Sweep every legal (parser, composer) for the detected input modality
.venv/bin/python level_1_modules/module_01k_image_edit/bilateral_k.py \
  --asset ./apple.png --all --quality low \
  "Add a small bird perched on the apple."
```

Stdout: `s3://` URI of rendered image. Stderr: parser IR with a `[path:
edit]` or `[path: translate (asset→IR)]` tag, composer trace,
comparison table.

## What you should be able to explain

1. **`(audio, image)` cannot use the edit endpoint.** What is the
   parser actually doing in Path B? It is no longer "extracting
   structure from a question" — it is performing modality conversion.
   The asset's transcription / observation becomes the *image brief*
   the composer renders from. Why does that mean the parser's
   temperature should be lower for audio than for an image edit-brief?
2. Anthropic parser slots are valid for `(image, image)` but **not
   valid** for `(audio, image)`. Why does that constraint live on the
   parser side, given that Anthropic is never the composer in this
   module?
3. `--edit-mode auto` and `--edit-mode generate` produce visibly
   different outputs from the same image input. What is the
   diffusion-transformer doing differently when handed `(image,
   prompt)` via `images.edit` vs handed only a text brief that
   describes the image?
4. Safety-flag semantics shift between paths. Path A flags often catch
   "remove copyrighted character from this image"; Path B flags often
   catch "depict real person from audio description." Why are those
   two different failure modes, and why is each one's policy filter
   in a different place in the pipeline?
5. After 1k, the matrix has 13 of 16 cells covered. What does 1l add?
   What goes wrong if you tried to fold 1l into 1k as a third internal
   path?

## Pitfalls deliberately within reach

- **Run `--all` with an audio asset.** Watch how the parser's
  `ASSET_OBSERVATIONS` field varies across slots — the edit-vs-render
  outcome quality is downstream of how well the parser heard the
  asset, not how good the image model is.
- **Force `--edit-mode generate` on an image input** and diff the
  outputs. The edit endpoint preserves identity (subject geometry,
  composition); the generate path produces a *new image* that
  resembles the description. Both are valid; the choice is a product
  decision, not a default.
- **`--all` with a video asset is small** — only google parsers are
  eligible. Two parsers × two composers × two baselines = 6 cells.
- **Audio/video parsers cost more in input tokens.** A 1-minute audio
  clip can run thousands of input tokens through the parser; the
  inverted-cost-arithmetic from 1i still mostly holds, but the parser
  share grows with asset duration. Watch the comparison table.

## Limitations (deliberate)

- **No style-reference / inpainting masks.** `images.edit` accepts a
  `mask` parameter for region-targeted edits; 1k doesn't expose it.
  Add as a follow-up module if region-edit is the lesson you want.
- **No multi-image grids or reference sets.** One asset in, one image
  out.
- **No edit-then-refine loop.** Single composer call per run.
- **Same per-image pricing for edit and generate.** Provider edit
  pricing has historically tracked generate pricing within a few
  percent; if that diverges, split `IMAGE_PRICING` into edit and
  generate tables.
- **Aspect ratio on Gemini remains a prompt hint** (same caveat as 1i).

## What this enables next

`level_2_strings/string_01_dispatch/dispatch.py` already routes
`(image|audio|video, image)` through this module. With 1k and 1l in
place, the 4×4 modality matrix has no deferrals — every cell has a
home. Module L2.2 (chat with memory) layers persistent threads on top
of the now-complete dispatcher.
