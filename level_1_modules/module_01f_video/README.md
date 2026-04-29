# Module 1f — Bilateral with Video Input

> **Curriculum:** Module 1 extension — single-provider modality (video: Google only). Modality forces parser; composer choice stays free. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension) and [`docs/treatise.md`](../../docs/treatise.md) Part III.

**Goal:** internalize what changes when an input modality is *exclusive*
to one provider. Audio (Module 1e) was *restricted* — only 2 of 3 labs.
Video tightens to 1 of 3: only Google's Gemini natively accepts video in
our 3-lab universe.

This is the inverse pressure to Module 1e:

| | Audio (1e) | Video (1f) |
|---|---|---|
| Available providers | OpenAI, Google | **Google only** |
| Routing decision on parser | which of 2 labs? | which Google **tier**? |
| Why bilateral still earns its keep | cross-provider cost asymmetry | **decouples *who sees the modality* from *who writes the answer*** |

In other words: bilateral isn't dead just because the parser side is locked
to one provider. It's still useful because the *composer* can be anyone —
Gemini sees the video, distills it to text, and Claude or GPT-4o picks up
the IR and produces the final answer in their own prose style.

This is the LIMBIC vision in miniature: **modality forces parser choice;
composer choice stays free**.

## What's new vs Module 1e

| Aspect | Module 1e | Module 1f |
|---|---|---|
| Modality added | audio | video |
| Capable parsers | OpenAI + Google | **Google only** |
| OpenAI model rewriting | yes (audio-preview) | no (Gemini handles all modalities on same model id) |
| Inline size limit | none material | **20MB** for inline; larger needs `genai.upload_file()` (deferred) |
| `--all` baseline rows | 4 | 2 (only Google can baseline a video) |

## Setup

No new dependencies — `google-generativeai` already pulled in by Module 1c.
You'll need a video file ≤20MB at `s3://harness-eng/samples/<something>.mp4`.

## Run

```sh
# default: parser=google-fast, composer=anthropic-deep
.venv/bin/python level_1_modules/module_01f_video/bilateral_v.py \
  --video s3://harness-eng/samples/quarterly-revenue.mp4 \
  "Summarize what this video shows in two sentences."

# parser is forced — try Anthropic and watch it fail fast
.venv/bin/python level_1_modules/module_01f_video/bilateral_v.py \
  --parser anthropic-deep --composer openai-deep \
  --video s3://harness-eng/samples/quarterly-revenue.mp4 \
  "..."
# ERROR: --parser anthropic-deep does not accept video. Use google-fast or google-deep.

# baseline must also be Google
.venv/bin/python level_1_modules/module_01f_video/bilateral_v.py \
  --baseline --composer google-deep \
  --video s3://harness-eng/samples/quarterly-revenue.mp4 \
  "..."
```

### All video-capable configurations

```sh
.venv/bin/python level_1_modules/module_01f_video/bilateral_v.py --all \
  --video s3://harness-eng/samples/quarterly-revenue.mp4 \
  "Summarize what this video shows in two sentences."
```

6 configurations: 2 Google-only baselines + 4 bilaterals where a Google
parser drives a (sometimes non-Google) composer.

## What you should be able to explain

1. Why is the bilateral split *still useful* when only one provider can
   see the input? What problem does it solve that single-provider couldn't?
2. The Anthropic and OpenAI adapters guard against video with
   `NotImplementedError`, but the capability matrix in `call()` should
   already prevent the call from reaching them. Why have both layers?
3. What changes in the Google adapter between Module 1e (audio) and
   Module 1f (video)? Hint: very little. Why is Google so uniform across
   modalities while OpenAI needs `gpt-4o-audio-preview`?
4. The current Google adapter rejects videos >20MB. What would change
   to support large video — *just one extra code path*, two API calls,
   and a polling loop? Why is that acceptable to defer?
5. What does input-token count look like for video vs image vs audio
   on Gemini? Run `--all` and watch `[in=N]` in the parser telemetry.

## Pitfalls deliberately within reach

- **Send a >20MB video** and watch the adapter return a clean error
  pointing to `genai.upload_file()`. The deferral is documented, not
  hidden.
- **Run `--all` and notice that Gemini's input-token count for video is
  much higher than for image or audio.** Video is roughly tokenized at
  ~258 tokens per frame at 1fps — a 4-second clip at 1fps is ~1000
  input tokens before your prompt is added. Per-modality cost matters.
- **Compare `bilateral google-fast → google-deep` vs
  `bilateral google-fast → anthropic-deep`.** Same parser, same
  observations going to the composer; different prose. Read the two
  composer outputs side-by-side and notice the stylistic divergence.
- **Use `--parser google-deep`** on a complex video. Pro thinks before
  emitting transcript/observations — sometimes worth the extra tokens
  for ambiguous footage, sometimes not.

## Generating a test fixture

A small synthetic video (~4-second slideshow) can be made with `imageio`
+ `imageio-ffmpeg` (the latter bundles its own ffmpeg binary, no
sudo install needed):

```python
import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw

frames = []
for q, val, color in [("Q1", 1.2, (79,129,189)), ("Q2", 1.5, (79,129,189)),
                      ("Q3", 1.8, (79,129,189)), ("Q4", 2.4, (192,80,77))]:
    img = Image.new("RGB", (480, 270), "white")
    d = ImageDraw.Draw(img)
    d.text((50, 30), f"{q}: ${val}M", fill="black")
    d.rectangle([50, 80, 50 + int(val*60), 200], fill=color)
    frames.append(np.array(img))

iio.imwrite("/tmp/quarterly-revenue.mp4", frames, fps=1, codec="libx264")
# aws s3 cp /tmp/quarterly-revenue.mp4 s3://harness-eng/samples/
```

`imageio` and `imageio-ffmpeg` are NOT in `requirements.txt` — they're
fixture-only, used to generate test data. The module itself doesn't
depend on them.

## Limitations of this module (still deliberate)

- **Inline-only video upload.** ≤20MB. Larger files need
  `genai.upload_file()` + a polling loop for the `ACTIVE` state. Out of
  scope here; belongs in a future module focused on long-form video.
- **No frame-rate control.** Gemini samples at a default rate (1fps).
  A future module could expose `video_metadata.fps` to the API for
  finer-grained sampling.
- **No video output.** Both Anthropic and Google have separate
  video-generation models (Lyria, Veo, etc.) but they're not unified
  with the chat-completion endpoint we route through. Generating video
  is a different orthogonal axis — separate module.
- **Synthetic test fixture is trivial.** Real videos (long, with audio,
  motion-heavy, multi-scene) reveal much more about parser behavior. A
  4-frame slideshow is a smoke test, not an evaluation.

## What this enables next

- **Module 1g — audio output (composer-side modality).** The first
  module that routes the *output* modality, completing the input/output
  symmetry the bilateral architecture promises.
- **Module 1h — large-video upload path.** Pulls in
  `genai.upload_file()` + `wait_until_active`, which is the smallest
  taste of asynchronous orchestration the curriculum has met so far.
- **Module 4 — faculty-tagged eval set with video.** Once we have
  evals with video assets, `--all` on each row is a real measurement
  of "for tasks that require video understanding, what's the
  cost/quality crossover?"
