# Module 1g — Bilateral with Audio OUTPUT

> **Curriculum:** Module 1 extension — first *output*-side modality routing (audio out: OpenAI only). Capability matrix splits into input + output halves. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension) and [`docs/treatise.md`](../../docs/treatise.md) Part III.

**Goal:** internalize what changes when a *modality constraint applies to
the output side* of the bilateral split. Modules 1d–1f routed input
modality (image, audio, video). Module 1g routes the **composer's output
modality** — the user wants to *hear* the answer, not read it.

In our 3-lab universe, only OpenAI's `gpt-4o-audio-preview` family emits
audio in a single chat-completion call. Gemini and Anthropic both have
separate TTS-style models, but they're not unified with the chat
endpoint we route through. This makes 1g the **output-side analogue of
1f** — single-provider modality routing, but on the composer half of the
seam.

After 1g, the bilateral pipeline is parameterized on both sides:

```
   parser modality (1d/1e/1f)            composer modality (1g)
   ──────────────────────────            ──────────────────────
   text   image   audio   video    →     text   audio    [video, image generation: future]
```

## What's new vs Module 1e

| Aspect | Module 1e | Module 1g |
|---|---|---|
| Modality side | input (parser) | **output (composer)** |
| Capability matrix | `SLOT_CAPABILITIES` (input only) | **split into `SLOT_INPUT_CAPABILITIES` + `SLOT_OUTPUT_CAPABILITIES`** |
| OpenAI model rewriting | gpt-4o → gpt-4o-audio-preview when audio in | same when audio out |
| Composer return | text | **text + audio bytes** |
| Where audio goes | n/a | uploaded to `s3://harness-eng/outputs/` |
| Composer prompt | "write the answer" | **"speak the answer — short conversational sentences"** |

The composer's system prompt also changes: speech doesn't render markdown
or bullet lists naturally, so the composer is told to write
conversationally, with numbers spelled out where it improves clarity.

## Setup

No new Python deps. The S3 bucket from earlier modules
(`s3://harness-eng/`) is the audio output destination.
Composer-emitted audio gets uploaded under `outputs/<timestamp>-<id>.mp3`.

## Run

```sh
# Default: parser=anthropic-deep (text in, text IR out),
#          composer=openai-deep with audio_out=True
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  "Explain in two sentences why TLS handshakes need both client and server randoms."

# Pick a different voice
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  --voice nova \
  "Explain..."

# Capability check — try a non-OpenAI composer
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  --composer anthropic-deep \
  "..."
# ERROR: --composer anthropic-deep cannot emit audio. Use openai-fast or openai-deep.

# Baseline (no parser stage, single call to composer with audio_out)
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  --baseline --composer openai-deep \
  "..."

# Skip the S3 upload (faster smoke testing)
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  --no-upload \
  "..."

# Disable audio_out — useful for parser-IR debugging
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py \
  --no-audio-out --composer openai-deep \
  "..."
```

After a run, the audio file lives at `s3://harness-eng/outputs/...`. To
listen on this EC2 (no audio device):

```sh
aws s3 cp s3://harness-eng/outputs/<filename>.mp3 /tmp/answer.mp3
# then SCP it to your laptop, or:
aws s3 presign s3://harness-eng/outputs/<filename>.mp3   # one-hour download URL
```

### All audio-out configurations

```sh
.venv/bin/python level_1_modules/module_01g_audio_out/bilateral_o.py --all \
  "Explain in two sentences why TLS handshakes need both client and server randoms."
```

6 configurations: 2 baselines (OpenAI-only, since composer must emit
audio) + 4 bilaterals with diverse parsers (Anthropic, Google, OpenAI)
all flowing into an OpenAI deep composer.

## What you should be able to explain

1. The capability matrix splits into INPUT vs OUTPUT halves. Why is one
   table not enough? Give an example slot whose input and output
   capabilities are *not* the same.
2. The composer's system prompt explicitly mentions speech ("avoid
   markdown, bullet points, headers"). Why does this matter? What
   happens if you remove it and run with `--audio-out`?
3. The OpenAI adapter only sets `modalities=["text", "audio"]` and the
   `audio` config when `audio_out=True`. Why not always? (Think about
   what `gpt-4o-audio-preview` does when you call it with no audio
   request.)
4. Audio bytes go to S3, not local disk. What's the architectural
   reason — i.e., what would go wrong if we wrote them to
   `~/projects/Harness_drill/outputs/` instead?
5. If you wanted to also expose Gemini's TTS as an audio-out option
   (separate model), where in this module would you add it, and what
   would `SLOT_OUTPUT_CAPABILITIES` change to?
6. The composer's `r.choices[0].message.audio.transcript` is also
   captured into `text`. Why is the transcript valuable to keep even
   when audio is the user-facing deliverable?

## Pitfalls deliberately within reach

- **Run with `--composer anthropic-deep --audio-out`** — see the
  capability check fail upstream of any model call.
- **Run `--all` and notice the cost spread** between baselines and
  bilaterals. Audio output is paid for per-token of generated audio
  (counted in the same `output_tokens` field as text), so longer
  spoken answers cost more. The composer's "spoken sentences" prompt
  is also a cost lever.
- **Try the same prompt with different voices** (alloy, echo, fable,
  onyx, nova, shimmer). The transcript is identical; the audio
  differs. Useful when the voice persona matters.
- **Run with `--audio-format wav`** and notice the file size — WAV is
  uncompressed and ~10× larger than MP3 for the same content. Choose
  format for the consumer.
- **Run with `--no-upload`** to feel the latency difference; the S3
  upload typically adds 100–300ms.

## Limitations of this module (still deliberate)

- **Audio output via OpenAI only.** Gemini and Anthropic each have
  separate audio-generation models, but they're not on the same
  chat-completion endpoint. Adding them would require a different
  adapter shape — a Module 1h-or-later concern.
- **No audio input + audio output in one call.** OpenAI supports it
  (audio in → audio out), but combining 1e and 1g is its own routing
  decision. Worth a future module focused on full-duplex voice.
- **No streaming.** Both audio in and out are synchronous, full-payload
  round trips. OpenAI's Realtime API is the streaming counterpart;
  it's a different module entirely.
- **No SSML.** The composer can hint at pacing/emphasis through prose
  ("…and importantly,…"), but we don't pass SSML. Future module if
  control-over-prosody matters.

## What this enables next

- **Module 1h — large-video upload (genai.upload_file).** Closes the
  loop on "all input modalities supported, even at scale."
- **Module 1i — full-duplex voice.** Audio in + audio out in one call,
  through OpenAI's audio-preview models. The simplest "spoken
  conversation" primitive.
- **Module 4 — faculty-tagged eval set with output modality.** The
  evals start having both an input asset *and* an expected output
  modality. The router LIMBIC will eventually be becomes legible at
  this point.
