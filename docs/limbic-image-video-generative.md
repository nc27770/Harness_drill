# LIMBIC — Image and Video Generative

## Purpose and place in the doc layer

This is the third document in the design layer of Harness Drill, alongside
the README mechanics:

1. **[README.md](../README.md)** — what each module does (mechanical layer).
2. **[limbic-design.md](limbic-design.md)** — the LIMBIC router sketch
   (architectural layer).
3. **[measurement-seam.md](measurement-seam.md)** — the structural philosophy
   (the QM-measurement framing of the API boundary).
4. **This document** — the generative-modality background and the design
   grounding for [Module 1i (image output)](../level_1_modules/) and
   [Module 1j (video output)](../level_1_modules/).

Modules 1 → 1h have closed text and audio output. To complete the input ×
output capability matrix and prove the LIMBIC thesis under the hardest
modality, the curriculum needs image-out and video-out. Those modalities
are *not* like text. They look the same at the API surface; they are not
the same machine on the other side. This document is the background that
makes 1i and 1j buildable from first principles instead of cargo-culted
API calls.

The user-level claim this background grounds: **the goal is not to own a
foundation model. The goal is complete cognitive federation — any input
modality, any output modality, routed across multiple labs, presented as
a uniform harness.** 1i and 1j are the modules that prove this claim under
the modalities where it is hardest.

---

## 1. Why image and video are genuinely different from text

The bare-call model of inference (prompt in, autoregressive transformer,
eigenstate out) breaks for image and video generation in three concrete
ways. Naming them up front is what separates a designed harness from a
glued-together set of API calls.

### 1.1 The operator is not an autoregressive transformer

Text generation is autoregressive: given the previous tokens, sample the
next one from a softmax distribution. Image and video generation are
mostly **diffusion** processes: start from noise, run a learned denoising
network for many steps, end with a coherent pixel grid. The math is
different — a denoising step is conditional Gaussian regression, not a
softmax over a vocabulary. Inference compute scales with *number of
denoising steps* (typically 20–100) and *spatial / temporal resolution*,
not with token count.

Tied back to [measurement-seam.md](measurement-seam.md): for text and
image-input, you really are talking to the same operator inside the lab.
For image-out and especially video-out, you are talking to a **separate
operator behind the same API** — a diffusion-transformer stack that the
lab co-trained alongside their LLM, but which is genuinely a different
machine. The seam looks the same shape from the wire; the apparatus on
the other side is different. The QM analogy holds — preparation, basis,
projector, eigenvalue — but the projector is now a several-second
denoising chain instead of a softmax.

### 1.2 The output is not tokens

A text response is a token stream you can stop early, stream
incrementally, or sample one token at a time. An image is a 2D pixel
grid that materializes all-at-once at the end of denoising. A video is a
3D pixel volume (height × width × frames) — and the model has to
maintain temporal coherence across frames, which means frames are not
independently sampled the way tokens are.

Practically: there is no equivalent of `max_tokens`, no streaming, no
per-token sampling controls, no per-token cost accounting. The cost dial
is *seconds of generated video* or *megapixels of generated image*, not
tokens. The token-shaped intuitions Modules 1 → 1h built about cost,
latency, and stopping rules **do not transfer directly**. They have to
be re-derived under the new units.

### 1.3 The control flow is asynchronous

Text generation finishes in seconds and returns synchronously. Image
generation usually finishes in seconds and is also synchronous.
**Video generation runs for tens of seconds to minutes**, and on every
major API (Sora, Veo) it is *asynchronous*: you submit a job, get back a
job id, poll a status endpoint, and pull the result when it's ready.

This is the first place in the curriculum where the harness needs polling
loops, timeouts, partial-state handling, and orphaned-job detection. It
alone justifies giving 1j its own module rather than folding it into 1i —
the modality lesson and the async-control-flow lesson are different and
should not be conflated.

---

## 2. The historical lineage — and why "multimodal foundation model" is partly true and partly marketing

The lineage matters because anyone reading this curriculum will be told
in passing that "the field converged on multimodal foundation models."
That statement is right at one altitude and wrong at another, and the
distinction is load-bearing for routing decisions.

### 2.1 Era 1 — separate research programs (≈ 2014–2020)

```
┌──────────────────────────────────────────────────────────┐
│ VAE             — variational autoencoders               │
│                   (Kingma & Welling, 2013)               │
│ GAN             — generative adversarial networks        │
│                   (Goodfellow, 2014)                     │
│ EBM             — energy-based models                    │
│ Autoregressive  — PixelRNN, PixelCNN                     │
│ Diffusion       — DDPM, score matching                   │
│                   (Ho et al., 2020)                      │
│ ViT             — vision transformer encoder             │
│                   (Dosovitskiy, 2020)                    │
└──────────────────────────────────────────────────────────┘
   Each had its own training recipe, its own loss, and its
   own production niche. Image generation was a GAN+VAE
   problem; image understanding was a CNN/ViT problem;
   video was a separate, much harder, mostly research-only
   frontier.
```

### 2.2 Era 2 — latent diffusion + transformer backbone won (≈ 2021–2023)

```
┌──────────────────────────────────────────────────────────┐
│ Stable Diffusion       — latent diffusion in VAE space   │
│ Imagen, DALL-E 2       — diffusion at scale              │
│ DiT                    — Diffusion Transformer (Peebles  │
│                          & Xie, 2022) — replaces U-Net   │
│ 3D causal VAE          — video latents that compress     │
│                          spatially AND temporally        │
└──────────────────────────────────────────────────────────┘
   One architectural family absorbed the field:
     - VAE survives as the encoder (compress pixels to
       latents).
     - Diffusion survives as the sampler (iterative
       denoising).
     - Transformer survives as the backbone (replacing
       U-Net for scaling).
   EBMs are largely retired for foundation-scale work.
   GANs survive in narrow niches (faces, fast inference)
   but lost the foundation-model race.
```

### 2.3 Era 3 — convergence at the foundation level (current)

```
Sora     (OpenAI)        DiT, 3D VAE latents
Veo      (Google)        DiT, 3D VAE latents
Kling    (Kuaishou)      DiT, 3D VAE latents
Dreamina (ByteDance)     DiT, 3D VAE latents
Runway   (Gen-3 / Gen-4) DiT, 3D VAE latents
Pika 2.x                 DiT family
Luma     (Dream Machine, Ray2)   DiT family
```

Architectural convergence is real. The differentiators are now:

1. **Training data composition** — how much, what license, what motion
   variety, what aesthetic priors.
2. **Compute budget** during training.
3. **Latent and conditioning tricks** — better motion priors, longer-clip
   stability, better text adherence, character/style consistency.
4. **Safety policy and filter strictness.**
5. **Product surface** — timeline editor (CapCut), motion brush
   (Runway), keyframe controllers (Kling), lip sync, music sync.

### 2.4 What this means for routing

When LIMBIC routes a video-generation call between Sora and Veo, it is
**not** picking between meaningfully-different architectural philosophies.
It is picking between *the same architecture trained at different labs
with different data and different policy*. That is a much narrower
decision than picking between Claude and Gemini for text, and it
concentrates the routing decision on a different axis: style fidelity,
motion quality, prompt adherence, safety posture, price-per-second of
video. The faculty axis (perception / intellect / expression) collapses
on the composer side because the composer is a single faculty —
expression, in the visual register.

This refines the LIMBIC routing model: for image-out and video-out, the
parser stage is doing nearly all the cognitive work, and the composer is
a stylistic and policy choice on top of capability. That is the opposite
weighting from text routing, where the composer often does the heavy
intellectual lift.

---

## 3. The current commercial landscape

There are three categories of players, and only the first is API-callable
in the way LIMBIC needs.

### 3.1 Category 1 — Foundation labs with token-shaped APIs

| Lab | Image gen | Video gen | API shape |
|---|---|---|---|
| **OpenAI** | gpt-image-1, DALL-E | Sora (async) | REST + SDK; image sync, video async |
| **Google** | Imagen (Vertex), Gemini native image | Veo (async, Vertex / Gemini API) | REST + SDK; image sync, video async |
| **Anthropic** | — | — | text/image *input* only; no generative output |

These are the only three labs with a clean "prompt in, asset out" API
that fits inside a LIMBIC-style harness. Anthropic stays a parser
candidate (it reads images well) and a text-composer; it cannot serve as
an image-out or video-out composer at all.

### 3.2 Category 2 — Specialized generative labs (own foundation models, often product-shaped)

| Lab / product | Modality focus | Foundation model | API or product? |
|---|---|---|---|
| **Kling** (Kuaishou) | Video, image-to-video | Own (Kling 1.x → 2.x) | API + product |
| **Dreamina / Jimeng** (ByteDance) | Image + video | Own (Dreamina, Seedance) | Mostly product (consumer app), limited API |
| **Runway** | Video | Own (Gen-3, Gen-4) | API + strong product |
| **Pika** | Video | Own (Pika 2.x) | API + product |
| **Luma** | Video, 3D | Own (Dream Machine, Ray2) | API + product |
| **Hailuo** (MiniMax) | Video | Own | API + product |
| **Adobe Firefly Video** | Image, video | Own (licensed-content trained) | API + Creative Cloud product |
| **Suno / Udio** | Music | Own | API + product |

**Crucial nuance:** these are often *not* token-in / token-out tools.
They are **product experiences** — timeline editors, motion-brush UIs,
keyframe controllers, style locks — where the "AI call" is one button
inside a workflow, not a clean API contract. Even when they expose an
API, the product surface is where their differentiation lives. A
LIMBIC-style router cannot consume the product surface; it can only
consume the API surface, and on the API surface most of these labs look
like a Sora-shape or Veo-shape async job submitter.

This is why "you have three APIs and can model-switch between them" is
the right scope for the curriculum, and why adding Kling or Runway as a
fourth or fifth lab would not change the *lesson*. It would just expand
adapter surface and add quota and auth tax.

### 3.3 Category 3 — Orchestration tools (no foundation model of their own)

CapCut is the cleanest example: it's a video editor with AI features
where the AI features call ByteDance's own foundation models (Dreamina,
Seedance) plus various utility models (background removal, upscale, lip
sync). Other tools in this category include InVideo, Descript, and many
video-editor + AI plugins.

These tools *are* harnesses — that is the important point. CapCut is
exactly what Harness Drill is training a builder to construct, except
CapCut owns its underlying models. Your version, built on
{Anthropic, OpenAI, Google}, is a CapCut-lite where the operator side is
not yours.

That is not a weaker position. It is a deliberately scoped one. The
lesson Modules 1i and 1j are designed to teach is the *harness pattern*,
not the model quality — and the harness pattern is identical whether the
operator is yours or rented.

---

## 4. What this background changes about LIMBIC

Three updates to the LIMBIC design surface fall out of sections 1–3.

### 4.1 The capability matrix doubles

Before image-out and video-out, the matrix was 4 inputs × 2 outputs = 8
cells. After: **4 inputs × 4 outputs = 16 cells**, capability-filtered.
The two new output columns are heavily filtered:

- Image-out: OpenAI ✅, Google ✅, Anthropic ❌
- Video-out: OpenAI ✅, Google ✅, Anthropic ❌

Cross-product after filtering: in the image-out and video-out columns,
the composer slot has only two candidates. The parser slot still has
three. Bilateral combinatorics shrink on the composer side and stay rich
on the parser side — *the asymmetry the LIMBIC design predicted is now
forced by capability*.

### 4.2 Cost telemetry needs a new unit story

Text cost is micro-cents. Image cost is single-cents to tens-of-cents per
image. **Video cost is dollars per clip.** The visceral-feedback intent
of printing cost on every call survives, but the formatting and the
warning thresholds need to scale. A naïve `cost=$0.000003` formatter
that prints `cost=$3.4200` for a 5-second video clip should also flag
the order-of-magnitude jump. This is its own small design decision and
should be made deliberately when 1j ships.

### 4.3 Async generation is a new control-flow primitive

Every prior module has been synchronous. Video output requires the
harness to:

- Submit a generation request and receive a job id.
- Poll a status endpoint at a sane interval (with exponential backoff).
- Handle three terminal states: `completed`, `failed`,
  `content-policy-rejected`.
- Pull the resulting bytes (or signed URL) and write to S3.
- Tolerate network failures mid-poll without losing track of the job.
- Have a timeout / abort path that doesn't leak charged-but-uncollected
  jobs.

This is genuinely new pattern surface, and it generalizes beyond video.
Any future module that needs long-running generation (long-form audio,
large-batch image generation, multi-step planning agents with chained
generations) will reuse this primitive. That is why it earns its own
module.

---

## 5. Module 1i — Image output (design)

**Goal:** prove the bilateral split holds when the composer's output
modality is image, and define the image-shaped IR.

### 5.1 Slots and pipeline

- **Composer slot:** OpenAI gpt-image-1 *or* Google Imagen / Gemini
  native image. Capability-filtered; Anthropic excluded.
- **Parser slot:** unconstrained — Anthropic, OpenAI, Google all
  candidates. Parsing intent is text-shaped even when the output is
  image.

```
user prompt ─► [parser model: any tier, any lab]
                          │
                          ▼
                IR (image-shaped, see 5.2)
                          │
                          ▼
        [composer model: OpenAI gpt-image-1 OR Google Imagen]
                          │
                          ▼
                image bytes → S3 (s3://harness-eng/outputs/)
                          │
                          ▼
                stdout: signed URL + metadata
```

### 5.2 The image IR is genuinely different

The text-output IR ([Module 1b](../level_1_modules/module_01b_bilateral/bilateral.py))
has fields for *literal question*, *expected answer shape*, *key facts*,
and *ambiguities*. Those fields make sense for prose. They do **not**
make sense for an image generator.

The image IR's load-bearing fields are:

- **Subject and composition** — what is in the frame, and where.
- **Style and aesthetic notes** — photographic / illustrated / painted;
  era; mood.
- **Lighting and color** — bright/dim, warm/cool, palette hints.
- **Aspect ratio / resolution hint** — 1:1, 16:9, 9:16, etc.
- **Negative prompts** — explicit "do not include" cues.
- **Safety-relevant flags** — does this prompt request a real person, a
  trademark, anything the policy filter is likely to refuse?

Designing this IR is itself part of the lesson. It is the first place in
the curriculum where the parser's output schema is dictated by the
*output modality*, not by an abstract notion of "structured analysis."
Future modules will generalize this: each output modality has its own
parser-IR schema.

### 5.3 The questions 1i is asking

1. Does the parser stage actually help an image generator? Image-gen
   models are heavily prompt-engineered already; does an LLM parser add
   or subtract quality?
2. Does cross-lab parser → composer pay off? (e.g. Claude parser →
   Imagen composer vs. Gemini parser → Imagen composer.)
3. Where does *decline to modulate* land? On simple prompts ("a red
   apple"), is the parser pure overhead?
4. What does the cost matrix look like? (Likely: the parser is a
   rounding error against the image cost, which inverts the bilateral
   tradeoff arithmetic from earlier modules.)

### 5.4 Files (proposed)

- `level_1_modules/module_01i_image_out/image_out.py`
- `level_1_modules/module_01i_image_out/README.md`
- Reuses `assets.py` from 1d for S3 writes.

---

## 6. Module 1j — Video output (design)

**Goal:** prove the bilateral split holds under *async* generation, and
close the input × output modality matrix at 16 cells.

### 6.1 Slots and pipeline

- **Composer slot:** OpenAI Sora *or* Google Veo. Capability-filtered;
  Anthropic excluded.
- **Parser slot:** unconstrained.

```
user prompt ─► [parser model]
                      │
                      ▼
              IR (video-shaped, see 6.2)
                      │
                      ▼
              [composer model: submit async job]
                      │
                      ▼
              job id ─► [poll loop]
                              │
                              ├─ completed   → fetch bytes → S3
                              ├─ failed      → surface error
                              └─ rejected    → surface policy
                                               refusal as a
                                               first-class outcome
                              │
                              ▼
              stdout: signed URL + metadata + total wall time
```

### 6.2 The video IR

Adds two fields to the image IR:

- **Camera motion / shot type** — static, dolly, pan, tracking;
  close-up vs. wide.
- **Duration** — how many seconds. (Both Sora and Veo cap clip length;
  the parser should normalize to a feasible value.)

Other fields (subject, composition, style, safety flags) carry over.
The IR is intentionally similar to the image IR — they are siblings,
and 1j should make that visible by structuring the schema accordingly.

### 6.3 The new harness primitives 1j introduces

1. **Async job state machine** — submit, poll, succeed/fail/reject.
   This becomes the prototype for any later long-running generation
   module.
2. **Timeout policy** — what's the upper bound on poll time? What does
   abort do? What does abort cost? Sora and Veo both bill on
   *completion*, not submission, but a leaked job that nobody collects
   is still wasted lab compute and may count against quota.
3. **Refusal-as-outcome** — content-policy refusals must be a typed
   result, not a Python exception. This is also the precursor to
   LIMBIC's "decline to modulate" first-class routing decision in
   text-side routing.
4. **Cost accounting at orders-of-magnitude jump** — telemetry has to
   handle "this call cost $4.20" without losing the visceral-feedback
   property the curriculum has cultivated since Module 1.

### 6.4 The questions 1j is asking

1. Is the parser stage worth its latency tax when the composer is
   already taking 60+ seconds? (Its *relative* cost is even smaller
   than in 1i, but its latency adds to a wall time the user is already
   waiting on.)
2. Does the parser materially improve prompt adherence, motion
   plausibility, or style fidelity in the rendered video?
3. How does the harness handle a failed generation gracefully — retry
   with a refined prompt? Surface and stop?
4. Where does video-out's "decline to modulate" sit? (Plausible answer:
   never. The parser is too cheap relative to the video render to ever
   be worth skipping.)

### 6.5 Files (proposed)

- `level_1_modules/module_01j_video_out/video_out.py`
- `level_1_modules/module_01j_video_out/README.md`
- Shared async-job utility — likely `common/async_job.py` once the
  pattern stabilizes (matches the README's policy of moving shared
  building blocks into `common/` once they earn it).

---

## 7. Why 1i and 1j on Gemini + OpenAI is the right scope (not Kling, not Runway)

A reasonable reader question: if Kling and Runway are state of the art,
why not include them in the matrix?

Three reasons.

1. **The lesson is the harness, not the model.** The pattern of bilateral
   routing across an asymmetric capability matrix is identical whether
   the composer is Sora, Veo, Kling, or Runway. Two operators are
   sufficient to demonstrate the routing logic. A third or fourth would
   be repetition, not new lesson.

2. **API uniformity matters for the curriculum.** OpenAI and Google
   already have established adapter coverage from Modules 1c–1h. Bringing
   in Kling or Runway means a new adapter, new auth flow, new quota
   story. That is adapter-tax work, not lesson work, and it belongs in a
   Level-2 string ("media production agent") if it ever happens.

3. **Specialized labs are often product-shaped.** Their differentiation
   lives in UIs that LIMBIC cannot consume. Routing them via API gives
   you the model but not the product, which is the worst-of-both-worlds
   for a real production media tool. The honest framing is: if you ever
   want CapCut-shaped output quality, you build the product layer on
   top of the harness — you do not extend the harness sideways into more
   labs.

The honest curriculum-level claim: **Modules 1i and 1j prove cognitive
federation across the modalities you can reach with the three-lab API
substrate.** They do not claim to be the best image or video generator
on the market. They claim to demonstrate that the bilateral pattern, the
LIMBIC routing axis, the capability matrix, and the async control flow
all hold up when output modality moves from text to image to video.
That is the curriculum-level claim, and it is testable.

---

## 8. The post-1j coverage map

After 1j, the matrix is closed:

```
                       OUTPUT
              text   audio   image   video
            ┌────────────────────────────────┐
text        │  ✅    ✅      ✅      ✅      │
INPUT image │  ✅    ✅      ✅      ✅      │
      audio │  ✅    ✅      ✅      ✅      │
      video │  ✅    ✅      ✅      ✅      │
            └────────────────────────────────┘
              16 cells, capability-filtered
              parser slot (input side):  Anthropic / OpenAI / Google
              composer slot (output side):
                text    : Anthropic / OpenAI / Google
                audio   : OpenAI (per Module 1g matrix)
                image   : OpenAI / Google
                video   : OpenAI / Google
```

After 1j the curriculum has demonstrated:

- **Any input modality** can feed a parser stage.
- **Any output modality** can be served by a capability-filtered
  composer.
- **Cross-lab composition** is functional across all 16 cells where
  capability allows.
- **Async generation** is a first-class harness primitive, not a one-off
  hack.
- **Refusal handling** is wired in as a typed outcome — a precursor to
  LIMBIC's *decline to modulate* first-class routing decision.

That is the substrate LIMBIC needs to do its real job at Level 3. With
it in place, faculty-aware routing (Module 4), telemetry (Module 5), and
LIMBIC v0 (Module L3.1) all have the data and the dispatch primitives
they need.

This is what **complete cognitive federation** looks like at the harness
level — not a single mega-model serving every modality, but a harness
that knows what each lab can do, routes accordingly, and presents a
uniform interface to the application built on top. It is the answer to
the question "if you do not own a foundation model, how far can you go?"
The answer this curriculum gives, ending at 1j: *all the way to a
modality-complete, multi-lab harness that a CapCut-lite could be built
on top of.*

---

## 9. Open questions specific to image and video routing

Carrying forward the spirit of `limbic-design.md §6` — these do not yet
have good answers. Each will need a real answer before LIMBIC v0 ships
with image/video support.

1. **Where does the image/video IR live in the LIMBIC IR?** The text IR
   in Module 1b is free-text labeled sections. The image IR is more
   structured. The video IR is more structured still. Does LIMBIC carry
   one IR shape per modality, or one extensible IR with modality-shaped
   sub-schemas?

2. **What is the right cost-comparable unit across modalities?** Tokens
   for text. Megapixels for images. Seconds-of-video for video. LIMBIC's
   cost-per-faculty story (`limbic-design.md §2.3`) needs a unifying
   normalization so a routing decision can compare a $0.001 text call
   to a $4.00 video call without mishandling the scale.

3. **How does refusal-handling generalize?** Image and video labs refuse
   prompts at much higher rates than text labs. Should LIMBIC pre-route
   away from likely refusals (cheap to predict, lossy on borderline
   cases), or let the lab refuse and fall back to a different lab
   (expensive, but more accurate)? The answer probably differs by
   prompt category.

4. **Does video output fit the bilateral split at all?** The parser is
   tiny relative to the composer. It may be that video-out is a place
   where bilateral is *always* the right call (no decline-to-modulate
   case), which would itself be a meaningful finding from 1j.

5. **Where does audio output sit on this background?** The README says
   1g constrains the composer to OpenAI, but Google's Gemini also has
   native audio output now. The audio-out capability matrix may need
   revisiting once 1i and 1j are in flight, since the same questions
   (own-vs-rented, product-vs-API, async-vs-sync) apply at smaller
   scale to audio.

These belong in this document because they are modality-specific. The
LIMBIC-general open questions live in `limbic-design.md §6`.
