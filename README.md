# Harness Drill

A from-first-principles curriculum in harness engineering for agentic systems.
Build every pattern by hand before adopting frameworks. The repo is the artifact
of the journey — modules in order, each with reference code and notes.

## Layout

```
.
├── level_1_modules/         per-module reference implementations
│   └── module_01_bare_call/ (read this first)
├── level_2_strings/         cross-layer integrations (added when needed)
├── level_3_agents/          purpose-built agents (added when needed)
└── common/                  shared building blocks (added when patterns stabilize)
```

Per-module isolation makes lessons legible — diff Module 4 against Module 3 and
the change *is* the lesson. Strings prove composition; purpose-built agents
prove the muscle holds when the problem is yours.

## Setup

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in ANTHROPIC_API_KEY
```

## Workflow

Code is authored on branch `claude/plan-task-dxiRu`, pushed to GitHub, and
synced to the execution environment via `git`. To run a module:

```sh
git fetch origin
git checkout claude/plan-task-dxiRu
git pull
python level_1_modules/module_01_bare_call/bare_call.py "your question"
```

## Modules

| # | Module | Concept |
|---|---|---|
| 1 | [`module_01_bare_call`](level_1_modules/module_01_bare_call/) | The single model invocation. Stateless. No tools. |
| 1b | [`module_01b_bilateral`](level_1_modules/module_01b_bilateral/) | Split read from act — separate parser and composer models, two tiers each (Anthropic only). Prototype for the bilateral piece of LIMBIC. |
| 1c | [`module_01c_bilateral_x`](level_1_modules/module_01c_bilateral_x/) | Bilateral across three providers (Anthropic, OpenAI, Google). Adapter layer makes provider differences visible — the API-drift tax LIMBIC will amortize. |
| 1d | [`module_01d_modality`](level_1_modules/module_01d_modality/) | Bilateral with image input. Parser sees the image once, composer reads only the text IR. S3-backed asset fetch via `assets.py`. |
| 1e | [`module_01e_audio`](level_1_modules/module_01e_audio/) | Bilateral with audio input. Anthropic excluded from parser slots (capability matrix). First place where modality routing is *forced*, not optional. |
| 1f | [`module_01f_video`](level_1_modules/module_01f_video/) | Bilateral with video input. Single-provider parser (Gemini-only); composer is unconstrained. Modality forces parser; bilateral keeps composer free. |
| 1g | [`module_01g_audio_out`](level_1_modules/module_01g_audio_out/) | Bilateral with audio **output**. Composer must be OpenAI; capability matrix splits into input/output halves. Audio bytes uploaded to `s3://harness-eng/outputs/`. |
| 1h | [`module_01h_modality_matrix`](level_1_modules/module_01h_modality_matrix/) | Closes the modality matrix — any input modality (text/image/audio/video) × either output (text/audio). Dynamic `--all` generates valid configs per cell. |
| 1i | [`module_01i_image_out`](level_1_modules/module_01i_image_out/) | Bilateral with image **output**. Composer is a diffusion-transformer (gpt-image-1, gemini-2.5-flash-image); Anthropic excluded. IR becomes modality-shaped (subject, composition, style, lighting, aspect, negatives, safety). Cost arithmetic inverts — parser is a rounding error against per-image cost. |
| 1j | [`module_01j_video_out`](level_1_modules/module_01j_video_out/) | Bilateral with video **output**, **async**. Composer is Sora or Veo (submit/poll/fetch); Anthropic excluded. Refusal is a typed terminal state (`completed` / `failed` / `rejected`). Cost moves from cents to dollars per clip. Closes the input × output matrix at 16 cells. |

Subsequent modules are built on demand, in order.

## Routing intuitions — when to modulate, when not to

The bilateral split is not free. A parser stage adds latency, input
tokens, and coordination cost. Across modules 1–1g, recurring patterns
have emerged that any future LIMBIC router must encode — including the
patterns where bilateral *loses* and the right move is no modulation at
all.

**Where bilateral pays:**

- **Hard-to-parse input** — image, audio, video, or ambiguous text where
  the parser does real interpretive work.
- **Cheap-but-modality-capable parser → deep-prose composer** — for
  example `google-fast → anthropic-deep`. Asymmetric advantage at
  near-baseline cost.
- **Pre-distilling Gemini Pro composer work** — bilateral with a
  non-Gemini parser routinely *cuts* cost vs. Gemini Pro baseline,
  because the IR pre-distills work Pro would otherwise burn thinking
  tokens on (observed in 1c, 1d, 1f).

**Where bilateral is overhead — LIMBIC must decline to modulate:**

- **Trivial prompts** (e.g., "what is 2+2") — baseline single-call always
  wins; the bilateral overhead exceeds any quality lift.
- **`gpt-4o-mini` baseline on simple factual extracts** — so cheap that
  almost no bilateral can compete on cost (e.g., 1d's $0.000049 baseline
  vs. $0.003 for the cheapest bilateral on the same prompt).
- **Parser slot = composer slot** — pure overhead, no asymmetric
  advantage. Just route as baseline.

**The discipline:** LIMBIC's *first* decision is whether to modulate at
all. "Decline to modulate, dispatch single-call baseline" must be a
first-class routing outcome — not a fallback after a failed bilateral.

## The perception / intellect / expression triad

The bilateral seam maps cleanly to a 3-faculty cognitive model that's
sharper for routing than the 5-faculty taxonomy in `docs/benchmark-lens.md`
(which is sharper for *grading*, but conflates routing concerns):

| Faculty | Pipeline location | Tier choice driven by |
|---|---|---|
| **Perception** | parser stage | how hard the input is to understand (modality, noise, ambiguity, length) |
| **Intellect**  | wherever reasoning happens (often composer) | depth of reasoning required (factual recall vs. novel inference) |
| **Expression** | composer stage | output modality and prose quality required |

Each faculty has its own (modality × tier) Goldilocks zone:

- **Perception:** fast tier when input is clean (terse text, simple
  chart); deep tier when input is noisy/ambiguous (long context,
  hard-to-read audio, multi-scene video).
- **Intellect:** fast tier on retrieval-shaped questions; deep tier on
  novel reasoning, multi-step inference, or any task where a thinking
  model's hidden tokens earn their cost.
- **Expression:** fast tier on terse factual replies; deep tier on
  long-form prose, persuasive arguments, or spoken delivery (audio
  output where pacing and word choice matter).

LIMBIC's per-call routing decomposes into three orthogonal Goldilocks
lookups against this triad. Module 4 (faculty-tagged evals) is what
turns the lookups from heuristic to data-driven.

## Coverage map (modality × routing space)

Discrete dispatchable configurations across the bilateral × tier ×
modality space:

```
                       OUTPUT
              text   audio   image   video
            ┌────────────────────────────────┐
text        │  ✅    ✅      ✅      ✅      │
INPUT image │  ✅    ✅      ✅      ✅      │
      audio │  ✅    ✅      ✅      ✅      │
      video │  ✅    ✅      ✅      ✅      │
            └────────────────────────────────┘

16 modality cells (4 input × 4 output) × full bilateral expansion
                                        (capability-filtered)

Modules 1 → 1h closed the text and audio output halves (8 cells).
Module 1i closes (text → image).
Module 1j closes (text → video) and proves the async-job primitive.

Image-edit (image → image) and image-to-video (image → video) are
deliberate deferrals — different endpoint families, no new routing
lesson.
```

After 1j the modality plane is solved. The remaining LIMBIC work is on
axes orthogonal to modality: faculty-tagged evals (Module 4), telemetry
(Module 5), rule-based router (L2.1), LIMBIC v0 (L3.1).

See `docs/limbic-design.md` for the full LIMBIC sketch and
`docs/limbic-image-video-generative.md` for the design grounding behind
1i and 1j (why image and video are *not* the same machine as text on
the other side of the wire).

## Design notes

| Doc | Purpose |
|---|---|
| [`docs/limbic-design.md`](docs/limbic-design.md) | Future-project sketch — multi-axis dynamic router (direction × faculty × modality × cost). Module 1b is the prototype of its bilateral axis. |
| [`docs/measurement-seam.md`](docs/measurement-seam.md) | Philosophical lens — frozen-weight LLM inference as a quantum-mechanical measurement act. The structural fact that makes the harness/researcher/inference role split inevitable. |
| [`docs/limbic-image-video-generative.md`](docs/limbic-image-video-generative.md) | Design grounding for 1i and 1j — why generative image/video output is a different operator family, why control flow goes async, and why cost units shift from micro-cents to dollars per clip. |
