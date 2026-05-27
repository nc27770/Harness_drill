# Module 1h — Closing the Modality Matrix

> **Curriculum:** Module 1 extension — closes the text/audio output halves of the (input × output) modality matrix in one consolidated module. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension).

**Goal:** complete the input/output modality coverage **for text and
audio outputs** in a single consolidated module. Modules 1d–1g
instrumented 5 of 8 text/audio-output cells; 1h closes the remaining
3:

```
( image, audio )   "look at this and tell me out loud"
( audio, audio )   "respond to my speech with speech"
( video, audio )   "narrate this video"
```

After 1h, every (input modality, text|audio output) cell is routable
through the same CLI. Image-out and video-out close in 1i, 1j, 1k,
1l — different operator families on the composer side, different
modules.

## What's new vs Module 1g

| Aspect | Module 1g | Module 1h |
|---|---|---|
| Input modalities | text only | **text, image, audio, video** (auto-detected from asset URI) |
| Output modalities | text or audio | text or audio |
| Capability matrix | input/output split (text in, audio out subset) | **full input × output matrix consulted on every dispatch** |
| `--asset` flag | n/a | unified — accepts image, audio, OR video; modality detected from MIME type |
| `--all` configurations | static curated set | **dynamic** — generated from whatever (input modality, output modality) cell you're in |

## Setup

No new deps. The asset fetcher (`assets.py`) was extended in 1d/1e/1f
with the relevant MIME types. The S3 bucket from earlier modules
(`s3://harness-eng/`) holds the test fixtures.

## Run

The CLI auto-detects input modality from the asset's media type. Just
pass `--asset` and (optionally) `--audio-out`.

```sh
# (image, audio): see chart, speak the answer
.venv/bin/python level_1_modules/module_01h_modality_matrix/bilateral_h.py \
  --asset s3://harness-eng/samples/quarterly-revenue.png \
  --audio-out \
  "Based on this chart, what was Q4 revenue?"

# (audio, audio): hear question, speak answer
.venv/bin/python level_1_modules/module_01h_modality_matrix/bilateral_h.py \
  --asset s3://harness-eng/samples/quarterly-revenue.mp3 \
  --audio-out \
  "Repeat the Q4 figure mentioned in the recording, in one sentence."

# (video, audio): watch video, speak summary
.venv/bin/python level_1_modules/module_01h_modality_matrix/bilateral_h.py \
  --asset s3://harness-eng/samples/quarterly-revenue.mp4 \
  --audio-out \
  "Summarize what this video shows in two short sentences."

# Or skip --audio-out for text-out runs (works for any input modality)
.venv/bin/python level_1_modules/module_01h_modality_matrix/bilateral_h.py \
  --asset s3://harness-eng/samples/quarterly-revenue.mp4 \
  "Summarize what this video shows."
```

### `--all` is dynamic in 1h

`--all` generates configurations based on the (input, output) cell you
landed in. It enumerates every (parser, composer) pair where:

- Parser supports the detected input modality
- Composer supports the requested output modality
- Parser ≠ composer (same-slot bilateral is pure overhead — skipped)
- Plus baselines whenever a single slot supports BOTH input and output

So a run with `--asset *.mp4 --audio-out --all` produces the 4
configurations of cell `(video, audio)` automatically; a run with
`--asset *.png --audio-out --all` produces 14 configurations of cell
`(image, audio)`. Same code path; different cells.

## What you should be able to explain

1. Module 1h has TWO capability matrices (input and output) consulted
   per call. Why is it impossible to collapse them into one set?
2. The OpenAI adapter rewrites `gpt-4o → gpt-4o-audio-preview` when
   *either* audio input *or* audio output is present. Why is this
   correct rather than two separate rewrites?
3. `--all` is generated dynamically from the input modality. What
   would change in the code if Anthropic added audio input support
   tomorrow?
4. The same-slot bilateral case (e.g., `parser=openai-deep,
   composer=openai-deep`) is filtered out. What would it cost in
   tokens, dollars, and latency, and what would it gain in quality?
5. If a future module added `(text, video)` as an output cell (Sora-
   style video generation), how much of 1h would change?

## Pitfalls deliberately within reach

- **Run `--all` on the (video, audio) cell** — only 4 configurations
  exist (no baselines because no slot does both video-in and
  audio-out). Compare costs across the 4 — every row is a real
  cross-provider bilateral.
- **Run `--all` on the (image, audio) cell** — 14 configurations.
  Notice the 2 baselines (OpenAI's audio-preview models can both see
  images and emit audio, so they baseline naturally).
- **Notice that LIMBIC's "Goldilocks zones" depend on the cell.** The
  cheapest configuration in `(audio, text)` is openai-mini baseline;
  in `(video, audio)`, the only configurations are bilateral, so the
  cost floor is structurally higher. Per-cell economics differ by
  orders of magnitude.

## What this completes

After 1h, the **text and audio output halves** of the modality matrix
are fully instrumented (8 of 16 cells). The image and video output
halves close in 1i (text→image), 1j (text→video), 1k
(image|audio|video→image), and 1l (image|audio|video→video). The
remaining work toward LIMBIC v0 is then on the **axes orthogonal to
modality**:

- **Deeper Territory 6 — evaluation frameworks.** Replace anecdotes
  with measured performance per (perception, intellect, expression)
  faculty.
- **Module 11 — observability / traces.** Persist every call's request,
  response, and timing for offline analysis. The data the policy will
  eventually fit on.
- **LIMBIC L2.1 (forward-design) — rule-based router.** Static decision
  tree consulting the capability matrices and Goldilocks heuristics
  from the README. See [`docs/limbic-design.md`](../../docs/limbic-design.md).
- **LIMBIC v0 (L3.1, forward-design).** Faculty classifier + cost-aware
  bilateral router on top of the rule-based foundation, learning
  per-cell Goldilocks zones from the eval + telemetry data.

After 1l the modality plane is solved. The cognitive plane is the
next frontier.
