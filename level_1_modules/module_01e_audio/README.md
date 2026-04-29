# Module 1e — Bilateral with Audio Input

> **Curriculum:** Module 1 extension — first *restricted* modality (audio: OpenAI + Google only). Capability matrix becomes explicit. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension) and [`docs/treatise.md`](../../docs/treatise.md) Part III.

**Goal:** internalize what changes when one of the modalities you want to
route is *not universally available*. Image input was a soft constraint
(every slot could do it; the question was cost). Audio is a hard
constraint (Anthropic doesn't accept it natively), and the harness has to
enforce that.

This is where LIMBIC's *"modality routing is forced, not optional"* claim
becomes load-bearing code. See
[`docs/limbic-design.md`](../../docs/limbic-design.md).

## What's new vs Module 1d

| Aspect | Module 1d | Module 1e |
|---|---|---|
| Modality | image (universal) | **audio (restricted to OpenAI + Google)** |
| Capability matrix | implicit | **explicit `SLOT_CAPABILITIES` dict** |
| Validation | none | fail-fast on incompatible slot/modality |
| OpenAI model selection | per slot | **rewritten to `*-audio-preview` variants when audio present** |
| `max_tokens` default | 2048 | 4096 (audio transcripts run longer) |
| Asset module | `assets.py` (local) | imported from 1d (shared primitive — DRY signal) |

The Anthropic adapter raises `NotImplementedError` on audio — the
upstream capability check should prevent the call ever reaching it, but
the defensive guard makes the constraint explicit if anyone bypasses
the harness.

## Setup

You already have the deps from earlier modules. Verify:

```sh
.venv/bin/python -c "import openai, anthropic; import google.generativeai as g; print('ok')"
```

You'll also want **at least one audio file in S3** for the smoke test.
The test fixture at `s3://harness-eng/samples/quarterly-revenue.mp3` was
generated using OpenAI's TTS API — see "Generating a test fixture"
below if you need to regenerate or create your own.

## Run

### One configuration

```sh
# default: parser=google-fast, composer=anthropic-deep — composer is text-only
.venv/bin/python level_1_modules/module_01e_audio/bilateral_a.py \
  --audio s3://harness-eng/samples/quarterly-revenue.mp3 \
  "What was Q4 revenue and did it exceed the target?"

# OpenAI audio parser
.venv/bin/python level_1_modules/module_01e_audio/bilateral_a.py \
  --parser openai-fast --composer anthropic-deep \
  --audio s3://harness-eng/samples/quarterly-revenue.mp3 \
  "What was Q4 revenue and did it exceed the target?"

# Anthropic as parser → fails fast (capability check)
.venv/bin/python level_1_modules/module_01e_audio/bilateral_a.py \
  --parser anthropic-deep --composer openai-deep \
  --audio s3://harness-eng/samples/quarterly-revenue.mp3 \
  "..."
# ERROR: --parser anthropic-deep does not accept audio.

# Single-call baseline (must be an audio-capable slot)
.venv/bin/python level_1_modules/module_01e_audio/bilateral_a.py \
  --baseline --composer google-deep \
  --audio s3://harness-eng/samples/quarterly-revenue.mp3 \
  "..."
```

### All audio-capable configurations

```sh
.venv/bin/python level_1_modules/module_01e_audio/bilateral_a.py --all \
  --audio s3://harness-eng/samples/quarterly-revenue.mp3 \
  "What was Q4 revenue and did it exceed the target?"
```

7 configurations total (4 baselines on audio-capable slots, 3 bilaterals
across cross-provider mixes). Anthropic baselines are deliberately absent
— if you wrote `--all` to include them, the adapter would refuse them at
runtime and pollute the comparison table. The capability matrix prevents
the misconfiguration upstream.

## What you should be able to explain

1. Why does `SLOT_CAPABILITIES` need to exist as a separate dict, when
   you could just let each adapter raise on unsupported modalities? (Hint:
   read the orchestrator. The matrix is consulted *before* the adapter is
   invoked.)
2. Why does the OpenAI adapter rewrite `gpt-4o` → `gpt-4o-audio-preview`
   only when audio is present, rather than always using the audio model?
   What does this preserve about cost and behavior for non-audio calls?
3. The composer slot can be Anthropic even though Anthropic can't accept
   audio. Why does that work? What invariant does it depend on?
4. Why is `max_tokens` bumped from 2048 to 4096 in this module
   specifically?
5. If you wanted to add a Whisper-style transcription preprocessing step
   so Anthropic *could* serve as an audio parser (via "audio → Whisper →
   text → Claude"), where would you add it, and what would the
   capability matrix change to?

## Pitfalls deliberately within reach

- **Try `--parser anthropic-deep` with `--audio`** — see the fail-fast
  message. That's the harness doing its job.
- **Compare `bilateral google-fast → anthropic-deep` (audio) against
  `bilateral google-fast → anthropic-deep` (image, Module 1d).** Same
  parser, same composer. The audio version produces a verbatim
  transcript in the IR; the image version produces visual observations.
  Both are flowing through the same composer, but the *quality* of the
  parser's distillation is what determines whether the answer is right.
- **Use Gemini Pro as the parser.** It thinks before it transcribes.
  Compare its TRANSCRIPT_OR_OBSERVATIONS section to Flash's — the extra
  thinking tokens often buy more careful disambiguation of unclear audio,
  but you pay for them.
- **Try with audio that has multiple speakers, accents, or background
  noise.** The TTS-generated fixture is clean lab speech; real audio
  surfaces parser differences much more dramatically. Worth uploading a
  short noisy clip of your own to `s3://harness-eng/samples/` and
  re-running `--all`.

## Generating a test fixture (TTS)

To create the canonical test audio (~15 seconds of synthesized speech) on
an empty S3 bucket:

```python
from openai import OpenAI
client = OpenAI()
script = (
    "Quarterly revenue results for fiscal year 2025. "
    "Q1 was 1.2 million dollars. "
    "Q2 was 1.5 million dollars. "
    "Q3 was 1.8 million dollars. "
    "Q4 was 2.4 million dollars, exceeding our 2 million dollar target."
)
r = client.audio.speech.create(model="tts-1", voice="alloy", input=script)
r.stream_to_file("/tmp/quarterly-revenue.mp3")
# then: aws s3 cp /tmp/quarterly-revenue.mp3 s3://harness-eng/samples/
```

OpenAI TTS pricing (`tts-1`) is ~$15 per 1M characters of input; this
script is under 200 chars, so the fixture costs a fraction of a cent.

## Limitations of this module (still deliberate)

- **No video.** Video is Gemini-only in our 3-lab universe, and the
  modality routing becomes *single-provider* — the bilateral split loses
  some of its expressive power. Worth its own module (1f) when needed.
- **No audio output.** Composer always returns text. OpenAI's GPT-4o can
  emit audio output, which is its own routing axis (composer modality vs
  composer text). Deferred.
- **No transcription preprocessing.** Anthropic stays excluded as a
  parser; we don't fall back to Whisper-then-Claude. That would shift
  Anthropic from "incapable" to "capable via composition" — which is
  exactly the kind of orchestration LIMBIC's eventual rule-based router
  should make explicit, in its own module.
- **TTS-generated audio is clean.** Real audio (background noise,
  multiple speakers, accents, music) reveals parser differences much more
  starkly. The fixture is deliberately easy so the smoke test is
  reliable; bring your own audio for real evaluation.

## What this enables next

- **Module 1f — video input.** Tests single-provider modality routing
  (only Gemini accepts video natively), the inverse pressure to 1e's
  multi-provider audio.
- **Module 1g — audio output (composer-side modality).** Routes the
  composer's modality, not just the parser's. First time the bilateral
  split is parameterized on the *output* side too.
- **Module 1h — transcription preprocessing.** Adds an optional
  "transcribe → text → any-parser" step so Anthropic and other
  audio-blind models can re-enter the audio routing graph. First taste
  of multi-step orchestration the rule-based router (LIMBIC L2.1) will
  generalize.
