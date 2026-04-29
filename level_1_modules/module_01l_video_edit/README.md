# Module 1l — Asset-conditioned video OUTPUT (async)

> **Curriculum:** Module 1 extension — closes the asset-input video-out diagonal (image-conditioned async + audio/video → video translation). Closes the matrix at all 16 cells. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension).

**Goal:** close the last three uncovered cells of the modality matrix
— `(image, video)`, `(audio, video)`, `(video, video)` — with one
module that holds two distinct internal paths. After 1l, the matrix
has no deferrals.

```
( image, video )   "make this still come alive for 4 seconds"  → Path A (condition)
( audio, video )   "render a music video for this clip"        → Path B (translate)
( video, video )   "extend / restyle this video"               → Path B (translate)
```

1l is the symmetric companion to 1j (and to 1k on the image side). 1j
covers `(text, video)`. 1l covers every non-text input that ends in
video.

## The two paths

### Path A — condition (input modality is image)

The image is passed to the composer as a conditioning reference:

- **OpenAI Sora-2:** `client.videos.create(input_reference=…, prompt=…, …)`
  — the `input_reference` parameter accepts a `(filename, bytes,
  mime_type)` tuple.
- **Google Veo:** `client.models.generate_videos(image=Image(image_bytes=…,
  mime_type=…), prompt=…, config=GenerateVideosConfig(…))` — `image`
  is a top-level kwarg on `generate_videos()`, NOT a config field.

The parser still runs, but with a CONDITIONING-shaped brief
(`PARSER_SYSTEM_CONDITION`): what the image establishes, what motion
to add, where the camera goes. The brief rides alongside the image.

We use the word "condition," not "edit." Video models don't truly
edit a source image — they treat it as a strong visual reference,
typically a first-frame anchor. The lab term varies (Sora calls it
`input_reference`, Veo calls it `image`); both behave as
conditioning, not editing.

### Path B — translate (input modality is audio or video)

There is no video-gen endpoint that accepts audio or video as
conditioning. So the parser's job changes shape:
**`PARSER_SYSTEM_TRANSLATE`** observes the asset and emits a normal
video brief. The composer then runs text-only async submit/poll.

`(video, video)` is the most expensive cell in the matrix — Gemini
parser must read the full input clip, then Veo or Sora renders new
video. A 4-second smoke test still costs ~$2 per cell.

`--edit-mode` controls path selection:

- `auto` (default): condition when input is image, translate otherwise.
- `condition`: force conditioning (errors on non-image input).
- `generate`: force translate path even on image input — useful for
  diffing a conditioned vs purely-text-described render of the same
  scene.

## What's new vs Module 1j

| Aspect | 1j | 1l |
|---|---|---|
| Input modalities | text only | image, audio, video |
| Parser-side capability gate | none | yes — anthropic excluded entirely; openai excluded from video |
| Composer endpoint | text-only `videos.create` / `generate_videos` | optionally with `input_reference=` (Sora) or `image=` (Veo) |
| Parser system prompt | one (video brief) | two (conditioning vs translate) |
| `--all` sweep | 14 cells | dynamic — only iterates parsers eligible for the detected input modality |
| Cost guard | none | `--yes-i-know-this-costs-money` required for `--all` (sweeps easily run $10–$20) |
| Async state machine | reused as-is | reused as-is |
| `job_id:` stderr line | yes | yes (dispatch.py extractor depends on it) |

## Setup

No new deps. Reuses 1j's OpenAI and `google-genai` SDKs and 1h's
`assets.fetch()`.

## Run

```sh
# (image, video) — image conditioning
.venv/bin/python level_1_modules/module_01l_video_edit/bilateral_l.py \
  --asset ./first_frame.png \
  --parser google-deep --composer openai-video \
  --duration 4 --size 1280x720 \
  "Animate this scene: gentle dolly forward, leaves rustling in a soft breeze."

# (audio, video) — parser translates audio → video brief
.venv/bin/python level_1_modules/module_01l_video_edit/bilateral_l.py \
  --asset s3://harness-eng/inputs/song-snippet.mp3 \
  --parser google-deep --composer google-video \
  --duration 4 --aspect-ratio 16:9 \
  "Render a 4-second music video that captures the mood of this audio."

# (video, video) — google-only parser, expensive
.venv/bin/python level_1_modules/module_01l_video_edit/bilateral_l.py \
  --asset s3://harness-eng/inputs/clip.mp4 \
  --parser google-deep --composer google-video \
  --duration 4 \
  "Restyle this clip in the visual language of 1970s Italian cinema."

# Compare condition vs generate on the same image
.venv/bin/python level_1_modules/module_01l_video_edit/bilateral_l.py \
  --asset ./first_frame.png --edit-mode generate \
  --duration 4 \
  "Animate the scene depicted: gentle dolly forward, leaves rustling."

# Sweep — REQUIRES the cost-acknowledgment flag
.venv/bin/python level_1_modules/module_01l_video_edit/bilateral_l.py \
  --asset ./first_frame.png --all \
  --yes-i-know-this-costs-money \
  --duration 4 \
  "Add gentle motion."
```

Stdout: `s3://` URI of rendered video. Stderr: parser IR with a
`[path: condition]` or `[path: translate (asset→IR)]` tag, `job_id:
…` line, composer trace, comparison table.

## What you should be able to explain

1. **Conditioning is not text-with-an-image.** When you pass an image
   to Sora-2 via `input_reference=` or to Veo via `image=`, the model
   treats it as a strong visual anchor — usually a first-frame seed
   for diffusion. What does that mean concretely for the brief? Why
   does over-specifying the visual content of the conditioning image
   in the prompt often *degrade* output instead of helping?
2. **`(video, video)` is the most expensive cell.** Why? Decompose the
   cost: parser tokens for a 30-second video clip on Gemini Pro,
   composer cost for a 4-second Veo render. Where would you put a
   guardrail in a production deployment, and would you put it on the
   parser side or the composer side?
3. **`--edit-mode generate` on an image input.** What does the
   diffusion process do differently when handed a conditioning image
   vs handed only a text brief that describes the image? When would a
   product team want one over the other?
4. **Parser-side capability cascade.** `(video, video)` admits only
   google parsers. `(audio, video)` admits openai too. Why is the
   asymmetry on the *parser* side rather than the composer side, and
   what does this say about how multimodal intake has consolidated
   across labs?
5. **Where the curriculum is after 1l.** The matrix is closed at all
   16 cells. What does L2.2 (chat with memory) add on top of the now-
   complete dispatcher, and what is it deliberately *not* solving?

## Pitfalls deliberately within reach

- **Run a `(video, video)` smoke test once.** Watch the parser
  swallow tens of thousands of input tokens and the composer charge
  $2+ for a 4-second clip. This is the cost-acknowledgment cell — the
  rest of the matrix feels almost free in comparison.
- **Force `--edit-mode generate` on an image input** and diff against
  `auto`. Conditioning preserves identity (subject, palette, mood);
  generate produces a *new* clip that resembles the brief. Both
  legitimate; the choice is product, not default.
- **Try `--all` without `--yes-i-know-this-costs-money`.** It
  refuses. Good — that's the cost guard doing its job. Read the
  estimated ceiling printed before the guard fires.
- **Pass an image whose first-frame composition is at odds with the
  motion you're asking for.** Watch how the conditioning constrains
  the motion — Sora and Veo both respect the conditioning more than
  the prompt when they conflict. This is the lesson behind the brief
  field "WHAT_THE_IMAGE_ESTABLISHES."

## Limitations (deliberate)

- **No video-to-video edit.** `(video, video)` runs through Path B —
  the input video is described, not transformed. True video edit
  (style transfer applied frame-by-frame, restyle) is a different
  pipeline and not in scope here.
- **No first-frame-from-image then-extend chains.** One conditioning
  pass per run.
- **No multi-image conditioning** (Sora supports it; we don't expose
  it).
- **No control over which generated frame the conditioning image
  becomes** — both labs default to first-frame; that's outside our
  parameter surface.
- **Same per-second pricing for conditioned and text-only renders.**
  If labs diverge, split `VIDEO_PRICING` into condition and generate
  tables.

## What this enables next

`level_2_strings/string_01_dispatch/dispatch.py` already routes
`(image|audio|video, video)` through this module. With 1k and 1l in
place, **the 4 × 4 modality matrix has no deferrals — every cell has
a home**. The cognitive plane (Module 4 evals, Module 5 telemetry,
LIMBIC L3.1 routing) is the next frontier; Module L2.2 (chat with
memory) layers persistent threads on top of the now-complete
dispatcher.
