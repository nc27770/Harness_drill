# Module 1j — Video OUTPUT (async)

> **Curriculum:** Module 1 extension — first async control flow (submit/poll/terminal); refusal becomes a typed outcome. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension) and [`docs/limbic-image-video-generative.md`](../../docs/limbic-image-video-generative.md) §1.3.

**Goal:** prove the bilateral split holds under **async** generation,
introduce the async-job state machine as a first-class harness primitive,
and close the `(text, video)` cell. See
[`docs/limbic-image-video-generative.md`](../../docs/limbic-image-video-generative.md)
§1.3, §4.3, and §6 for the design grounding.

```
( text,  video )   "make me a 4-second clip of X"     ← 1j closes this
( image, video )   image-conditioned async submit     ← Module 1l
```

1j closes the `(text, video)` cell. Asset-conditioned video-out
(`image|audio|video → video`) is its sibling — see Module 1l, which
reuses 1j's async state machine and adds image conditioning on Sora
and Veo (Path A) plus parser-translates-asset for non-image inputs
(Path B).

## What's new vs Module 1i

| Aspect | Module 1i | Module 1j |
|---|---|---|
| Output modality | image (PNG bytes) | **video (MP4 bytes)** |
| Composer family | sync diffusion-transformer (image) | **async diffusion-transformer (video)** with poll loop |
| Control flow | sync request → response | **submit → poll → terminal state** |
| Terminal states | success / exception | **completed / failed / rejected (typed)** — refusal is a first-class outcome |
| Cost units | cents per image | **dollars per clip** ($0.40–$5+) |
| Latency | ~3–10s | **30s–several minutes** |
| Composer slots | OpenAI ✅, Google ✅, Anthropic ❌ | OpenAI ✅, Google ✅, Anthropic ❌ |
| Output destination | `s3://harness-eng/outputs/images/` | `s3://harness-eng/outputs/videos/` |

The structural shifts to feel:

1. **Async is a state machine, not a function call.** The composer
   submits a job, gets a job id back, polls a status endpoint, and
   eventually pulls bytes (or a refusal). The harness has to encode
   "in flight" as a real state, not an artifact of a long socket.
2. **Refusal is typed, not exceptional.** Image and video labs refuse
   prompts at much higher rates than text labs (real persons,
   trademarks, sensitive content). 1j returns `terminal_state="rejected"`
   with a reason — not a Python exception. This is the precursor to
   LIMBIC's `decline to modulate` first-class routing decision.
3. **Cost arithmetic moves another order of magnitude.** A single 4-second
   720p Sora clip is ~$0.40. A 1080p clip is ~$2. A 10-second 1080p
   clip is ~$5. The `--all` sweep at 14 configurations × ~$0.40 each
   is **$5+ per run**. The cost formatter (`_fmt_cost`) scales between
   micro-cents and dollars without losing visceral feedback.
4. **The parser is now a rounding error twice over.** It was a rounding
   error in 1i ($0.0001 vs $0.01–$0.17). It is *very obviously* one in
   1j ($0.0001 vs $0.40–$5). Bilateral is essentially always net-positive
   on cost at this cell — the routing question collapses to *quality*.

## Setup

No new deps if your `openai`, `google-genai`, and `anthropic` SDKs are
recent. Note the import:

```python
from google import genai as genai_v2
from google.genai import types as genai_types
```

The video composer uses Google's newer `google-genai` SDK (the one
exposing the Veo `generate_videos` long-running operation), distinct
from `google.generativeai` used by parser/composer in earlier modules.
If you don't have it:

```sh
.venv/bin/pip install google-genai
```

AWS credentials come from the EC2 instance role. Sora and Veo access
must be enabled on your respective lab projects — both gate video
generation behind allowlists / preview programs.

## Run

```sh
# Single bilateral run, default 4-second 720p clip (~$0.40 Sora / ~$2 Veo)
.venv/bin/python level_1_modules/module_01j_video_out/bilateral_j.py \
  "A koi pond at dusk, slow camera dolly in, gentle ripples."

# Pick parser and composer explicitly
.venv/bin/python level_1_modules/module_01j_video_out/bilateral_j.py \
  --parser google-deep --composer google-video \
  "A bookshop in autumn, warm interior light, static shot."

# Baseline (decline-to-modulate) — composer-only
.venv/bin/python level_1_modules/module_01j_video_out/bilateral_j.py \
  --baseline --composer openai-video \
  "A red apple on a wooden table, static shot."

# Sweep — DO NOT RUN CASUALLY. 14 configurations × ~$0.40 = $5+
.venv/bin/python level_1_modules/module_01j_video_out/bilateral_j.py --all \
  --duration 4 --size 1280x720 \
  "A futuristic city skyline at golden hour, slow pan."
```

Stdout prints the `s3://` URI of the rendered video. Stderr carries the
parser IR, the job id, the terminal state, costs, latencies, and a
comparison table.

### Knobs that change cost dramatically

| Flag | Effect |
|---|---|
| `--duration N` | Linear: cost scales with N. Default 4. Max ~8–10s on preview tiers. |
| `--size 1920x1080` | OpenAI: ~5× the cost of `1280x720`. |
| `--all` | **Multiplies per-clip cost by 14**. Use a tiny duration when sweeping. |
| `--poll-timeout` | Doesn't change cost, but shorter timeouts can leak charged-but-uncollected jobs. Default 600s. |

## What you should be able to explain

1. The async control flow has three terminal states: `completed`,
   `failed`, `rejected`. Why is `rejected` modeled separately from
   `failed`, and how does it relate to LIMBIC's *decline to modulate*?
2. The poll loop uses exponential backoff with a 15-second cap. Why both
   — why not just poll every 2 seconds, or every 15? What does each
   side of the dial buy you?
3. The video IR shares 6 fields with the image IR and adds 2
   (`CAMERA_MOTION`, `DURATION_SECONDS`). Why is the IR sibling-shaped
   to the image IR's by design rather than a generic "structured
   analysis"? What does that imply about LIMBIC's IR registry?
4. A 1080p 10-second Sora clip is ~$5. The parser stage on the same run
   is ~$0.0001. Why does this *prove* the bilateral pattern holds at
   this cell, and what would *break* the pattern (i.e., where would the
   parser's *latency* become the load-bearing tax instead of cost)?
5. The harness uploads completed videos to S3 but does **not** cancel
   in-flight jobs on timeout. What's the failure mode that creates, and
   what's the right fix in a production version?

## Pitfalls deliberately within reach

- **Submit a prompt with a trademarked character.** Watch the terminal
  state come back as `rejected` rather than as an exception. That typed
  outcome is the precursor to LIMBIC routing around predicted refusals
  cheaply.
- **Set `--poll-timeout 30`** on a real video job. The harness will
  raise `TimeoutError` and return — but the job is still running on the
  lab's side and will still be billed when it completes. This is the
  "leaked job" problem the design doc flags.
- **Compare submit_latency to poll_latency.** Submit is ~1s. Poll can be
  60s+. The async-control-flow tax dwarfs the parser latency tax — the
  bilateral split is essentially free on the wall-clock side at this
  cell.
- **Run the same prompt twice with the same parser → composer.**
  Diffusion-transformer composers are *less* reproducible than text
  composers even at temperature=0, because the latent noise seed
  changes. The parser's IR is reproducible; the rendering isn't.

## Limitations (deliberate, deferred)

- **No image-to-video / asset-conditioned video.** Module 1l covers
  it — image conditioning via Sora `input_reference=` and Veo `image=`,
  plus parser-translates-asset for audio/video inputs. 1l reuses this
  module's async state machine.
- **No job cancellation on timeout.** Charged-but-uncollected jobs are
  documented as a pitfall but not fixed. A production version would
  call the lab's cancel endpoint on timeout and attribute the partial
  cost.
- **No retry-with-refined-prompt on rejection.** When the composer
  refuses, 1j surfaces the refusal and stops. A production agent would
  loop back to the parser with the refusal reason and let the parser
  rewrite. That's Module 3 / Module L3 territory.
- **No persistent job log.** If the harness process dies during a poll,
  the job id is lost (the lab still completes and bills). Fix: write
  the job id to a local journal before polling, reconcile on restart.
  Pattern stabilizes when Module 5 (telemetry sink) lands.
- **`common/async_job.py` not yet extracted.** The poll-and-terminal
  state machine lives inside `bilateral_j.py`. When a second module
  needs it (large-batch image gen, multi-turn agent loops), the
  pattern earns extraction into `common/`.

## What this completes

After 1j the **text-input column** of the modality matrix is fully
covered. Asset-input columns to image and video close in 1k and 1l
respectively. The full grid after 1l:

```
                       OUTPUT
              text   audio   image   video
            ┌────────────────────────────────┐
text        │  1c    1h      1i      1j      │
INPUT image │  1h    1h      1k      1l      │
      audio │  1h    1h      1k      1l      │
      video │  1h    1h      1k      1l      │
            └────────────────────────────────┘
```

What the curriculum has demonstrated end-to-end through 1j:
- Any input modality can feed a parser stage.
- Any output modality can be served by a capability-filtered composer.
- Cross-lab composition works wherever capability allows.
- Async generation is a first-class harness primitive.
- Refusal is a typed outcome, not an exception.

After 1l the modality plane is solved. The cognitive plane —
faculty-tagged evals (Module 4), telemetry sink (Module 5),
rule-based router (L2.1), LIMBIC v0 (L3.1) — is the next frontier.
