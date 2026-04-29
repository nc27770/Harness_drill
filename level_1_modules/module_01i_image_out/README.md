# Module 1i — Image OUTPUT

**Goal:** prove the bilateral split holds when the composer's output
modality is image, define the **image-shaped IR**, and feel the cost
arithmetic invert. First module where the composer is *not* an
autoregressive transformer — it's a diffusion-transformer stack behind
the same API. See [`docs/limbic-image-video-generative.md`](../../docs/limbic-image-video-generative.md)
§1.1 for why that distinction is structural, not cosmetic.

```
( text,  image )   "draw me X"          ← 1i closes this
( image, image )   "remix this image"   ← Module 1k (asset-conditioned)
```

1i closes the `(text, image)` cell. Asset-conditioned image-out
(`image|audio|video → image`) is its sibling — see Module 1k, which
mixes a true edit endpoint (Path A) with parser-translates-asset
(Path B).

## What's new vs Module 1h

| Aspect | Module 1h | Module 1i |
|---|---|---|
| Output modality | text or audio | **image** (PNG bytes) |
| Composer family | chat models | **diffusion-transformer image generators** |
| Composer slots | 6 chat slots | **2 image slots** (OpenAI ✅, Google ✅, Anthropic ❌) |
| Composer cost unit | $/Mtoken | **$/image** (with quality-tier dial) |
| IR schema | task-shaped (literal question, expected shape, key facts, ambiguities) | **modality-shaped** (subject, composition, style, lighting, aspect ratio, negatives, safety) |
| Output destination | stdout (text) or `s3://harness-eng/outputs/*.mp3` (audio) | `s3://harness-eng/outputs/images/*.png` |

The two structural shifts to feel:

1. **The IR is dictated by the OUTPUT modality.** Until 1h, the parser
   IR was an abstract "structured analysis" of the input. From 1i
   forward, the IR's shape is a creative-director brief whose fields are
   defined by what the renderer needs. This is the first place in the
   curriculum where the parser's schema is downstream-driven.
2. **Cost arithmetic inverts.** In 1c–1h the parser was often a
   meaningful share of total cost; bilateral was a tradeoff. Here the
   parser is a *rounding error* against per-image generation cost
   ($0.011–$0.167 per image vs. ~$0.0001 for the parser). The Goldilocks
   math flips — bilateral is almost always cheap relative to baseline,
   and the question becomes whether it improves prompt adherence.

## Setup

No new deps. Reuses the OpenAI and Google SDKs already pulled in by
1c–1h. AWS credentials come from the EC2 instance role (`claude-agent-role`).

## Run

```sh
# Single bilateral run, default cheap quality (smoke test)
.venv/bin/python level_1_modules/module_01i_image_out/bilateral_i.py \
  "A red apple on a wooden table, soft morning light, photorealistic."

# Pick parser and composer explicitly
.venv/bin/python level_1_modules/module_01i_image_out/bilateral_i.py \
  --parser google-fast --composer openai-image \
  "A futuristic city skyline at golden hour, cinematic."

# Baseline (decline-to-modulate) — composer-only, no parser stage
.venv/bin/python level_1_modules/module_01i_image_out/bilateral_i.py \
  --baseline --composer openai-image \
  "A red apple."

# Sweep: 2 baselines + 12 bilaterals = 14 configurations
.venv/bin/python level_1_modules/module_01i_image_out/bilateral_i.py --all \
  "A bookshop in autumn, warm interior light, illustrated style."
```

Stdout prints the `s3://` URI of the rendered image (pipe-friendly).
Stderr carries the parser IR, costs, latencies, and a comparison table.

### Quality dial (OpenAI only)

`--quality low|medium|high` controls `gpt-image-1` cost:

| quality | cost / 1024×1024 |
|---|---|
| low | $0.011 |
| medium | $0.042 |
| high | $0.167 |

Default is `low` so `--all` smoke tests cost ~$0.15 (12 bilaterals + 2
baselines × $0.011 OpenAI + ~$0.039 × 7 Google), not $2+. Bump to
`medium` or `high` for serious comparison runs.

### Aspect ratio

`--size 1024x1024 | 1024x1536 | 1536x1024 | auto` for OpenAI;
`--aspect-ratio 16:9 | 9:16 | 1:1 | …` for Google (passed as a soft
prompt cue — Gemini's image SDK doesn't yet expose a clean aspect-ratio
parameter on every version).

## What you should be able to explain

1. The composer side of 1i is filtered to two labs (OpenAI + Google) and
   Anthropic is excluded entirely. Why is this filtering a *capability*
   fact rather than a policy choice the harness could override?
2. The image IR has fields like `LIGHTING_AND_COLOR` and
   `NEGATIVE_PROMPTS` that don't exist in the text IR. Why is the
   parser's output schema downstream-driven by the composer's modality
   here, when in 1b it was driven by the input shape?
3. In 1d (image input) the parser cost was a meaningful fraction of the
   total. In 1i (image output) it isn't. What changed about the cost
   arithmetic, and what does that imply for LIMBIC's "decline to
   modulate" decision in this cell?
4. The default parser temperature is **0.7**, not the `0.0` you'd want
   for reproducibility on a factual extract. Why is creative slack
   correct here when it was wrong in 1d?
5. OpenAI's `gpt-image-1` returns a `revised_prompt` field — the
   provider rewrites your prompt before rendering. Where does that
   rewrite sit in the measurement-seam picture? (Hint: it's a
   *third* prep stage between your IR and the diffusion run.)

## Pitfalls deliberately within reach

- **Run `--all` and watch the cost table.** All 14 rows finish within
  ~10× of each other. The bilateral overhead in $/run is dominated by
  the image cost. This is the inverted Goldilocks the README's
  "Routing intuitions" section will eventually need to encode.
- **Run the same prompt twice with `--baseline` then with bilateral.**
  Sometimes the IR helps prompt adherence (well-framed brief). Sometimes
  the parser over-specifies and the image gets *worse* — quantum Zeno
  shows up here too.
- **Try a prompt that includes a real named person or trademark.** The
  parser will flag it under `SAFETY_FLAGS`, but the composer will still
  attempt the render and may refuse silently. That refusal pathway is
  what 1j has to make a first-class outcome.
- **Use `--no-upload` and `--no-ir`** to keep the run quiet when you
  just want to compare costs/latencies across configurations.

## Limitations (deliberate, deferred)

- **Image-edit (image-in → image-out)** lives in Module 1k. It uses
  OpenAI's `images.edit` endpoint and Gemini's in-context image-edit
  mode, both with a different control flow than `images.generate` —
  which is why they earn their own module rather than a flag here.
- **Style references / IP guards / multi-image grids** are out of
  scope. They're product-surface features, not harness primitives.
- **Aspect ratio on Gemini is a prompt hint, not a hard parameter.**
  The SDK's parameter surface is moving; revisit when it stabilizes.

## What this enables next

Module 1j layers async control flow on top of this same shape. The IR
gains two fields (camera motion, duration); the composer becomes
submit-then-poll instead of sync; refusal becomes a typed outcome.
Module 1k generalizes 1i to asset-conditioned image-out — image-edit
(Path A) plus audio/video → image translation (Path B). After 1k and
1l, the input × output modality matrix is closed at 16 cells and the
curriculum's modality plane is solved. The cognitive plane —
faculty-tagged evals (Module 4), telemetry (Module 5), and LIMBIC v0
(Module L3.1) — is the next frontier.
