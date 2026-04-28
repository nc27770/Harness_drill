# Module 1d — Bilateral with Modality

**Goal:** internalize what changes when the bilateral split has to handle a
non-text modality. Module 1c made the seam cross provider boundaries; Module
1d makes it cross *modality* boundaries — and at that point the seam stops
being optional.

Image input is the minimum-viable second modality. All three labs accept
images natively, so we can isolate the modality variable cleanly. Audio,
video, and PDF input belong in later modules; their adapter shapes diverge
even more sharply, but the principles introduced here generalize.

This is the third prototype piece of LIMBIC. See
[`docs/limbic-design.md`](../../docs/limbic-design.md) for the broader
design.

## What's new vs Module 1c

| Aspect | Module 1c | Module 1d |
|---|---|---|
| Input modality | text only | text + optional image |
| Asset source | (none) | local path, `https://...`, or `s3://harness-eng/...` |
| Adapter divergence | system prompt placement, usage shape | also: image content-block shape (3 different formats) |
| Composer sees | parser's text IR | parser's text IR (image *not* re-attached) |
| New file | — | `assets.py` — uniform fetch, ETag-cached for S3 |

The deliberate choice that **the composer never sees the image directly** is
where cost-aware modality routing first shows up: the parser eats the image
tokens once, distills them to text, and the composer pays only the text-IR
bill. This is exactly the pattern LIMBIC will eventually generalize across
all heavy modalities.

## Setup

```sh
.venv/bin/pip install -r requirements.txt
```

`boto3` is now in `requirements.txt` (added in this module).

You also need:
- An S3 bucket your IAM role can read (this curriculum assumes
  `s3://harness-eng/`, set up in the project's "where data lives" memory).
- At least one image at `s3://harness-eng/samples/<something>.png` (or
  `.jpg`) for the smoke test.

If you'd rather test against a local file or a public URL first, both work
without S3 setup:

```sh
.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py \
  --image /tmp/photo.jpg "What's in this image?"

.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py \
  --image https://upload.wikimedia.org/wikipedia/commons/.../foo.jpg \
  "What's in this image?"
```

## Run

### One configuration at a time

```sh
# default: parser=google-fast (cheap, native multimodal), composer=anthropic-deep
.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py \
  --image s3://harness-eng/samples/chart.png \
  "Summarize the trend in this chart in two sentences."

# anthropic-fast parser (Haiku has vision too, smaller context cost)
.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py \
  --parser anthropic-fast --composer anthropic-deep \
  --image s3://harness-eng/samples/chart.png \
  "Summarize the trend in this chart."

# baseline (one call, image attached directly)
.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py \
  --baseline --composer google-deep \
  --image s3://harness-eng/samples/chart.png \
  "Summarize the trend in this chart."
```

### All configurations on one image

```sh
.venv/bin/python level_1_modules/module_01d_modality/bilateral_m.py --all \
  --image s3://harness-eng/samples/chart.png \
  "Summarize the trend in this chart."
```

Runs 9 curated configurations: 3 single-call baselines (one per provider's
deep slot) plus 6 bilaterals (same-provider × 3, cross-provider × 3).
Compare cost, latency, and answer quality across the rows.

## What you should be able to explain

If any answer is hand-wavy, re-read the relevant adapter or comment:

1. The Anthropic adapter base64-encodes the image bytes; the OpenAI adapter
   does the same but wraps them in a `data:` URL; the Google adapter passes
   raw bytes. Why are these three different, and what would it take to
   unify them in the future LIMBIC IR?
2. Why does the parser's system prompt explicitly say *"the composer will
   not see the image"*?
3. The composer never receives the image. What does this save in cost?
   What does it cost in fidelity?
4. `assets.fetch()` caches S3 fetches by ETag. What happens if you upload a
   new image with the same key? What does this design guarantee that
   filename-based caching wouldn't?
5. Where do `boto3` credentials come from on this EC2, given there is no
   `~/.aws/credentials` file?
6. If you wanted the composer to *also* see the image (more expensive, more
   fidelity), where in the orchestrator would you change one line?

## Pitfalls deliberately within reach

- **Run `--all` on an image where the answer requires fine visual
  discrimination** (a chart with overlapping lines, a photo of similar
  objects, etc.) and study which parsers' VISUAL_OBSERVATIONS section
  flagged enough detail for the composer to answer correctly. The
  parsers that *understand the image* are the ones whose composers
  produce correct answers.
- **Use a deep slot as the parser** (e.g., `--parser google-deep`) on a
  hard image and compare to `--parser google-fast`. The thinking-token
  premium of the deep slot is sometimes worth it for visual perception
  even when the composer is the same.
- **Try the same image with the wrong question** (e.g., ask about color
  in a black-and-white chart) and see which configurations gracefully
  flag the mismatch in AMBIGUITIES vs which confabulate.
- **Watch the `[fetched: N bytes, media_type=...]` line.** If it says
  `application/octet-stream`, the source didn't surface a Content-Type
  and we fell back to extension-based guessing. Some providers reject
  unknown media types — explicit `.png` / `.jpg` extensions matter.

## Limitations of this module (still deliberate)

- **Image input only.** Audio and video belong in later modules. They
  exist on Gemini, Gemini-only for video, OpenAI for audio — the
  modality routing becomes *forced* in a way image doesn't quite
  illustrate (every slot here can do images).
- **One image per call.** Multiple images per call work in all three
  APIs but the curriculum benefit is small until we have a use case.
- **Composer is image-blind.** Architectural choice (cost), not a
  technical limitation. A future module can flip a flag and let the
  composer re-see the image when fidelity matters more than budget.
- **No streaming.** Every call is a synchronous round-trip. Streaming is
  a separate orthogonal axis that earns its own module.

## What this enables next

- **Module 1e — audio input.** Forces a single-provider parser route
  (only OpenAI accepts audio natively), giving us the first *truly
  forced* modality dispatch.
- **Module 4 — faculty-tagged eval set.** Stored in
  `s3://harness-eng/evals/`. With a bench of (prompt, image, expected
  faculty) tuples, `--all` becomes a real comparator instead of a
  one-shot.
- **Module 5 — telemetry sink.** Every call's request, response, and
  timing dumps to `s3://harness-eng/traces/<run-id>/`. The data LIMBIC
  will route on starts accumulating here.
