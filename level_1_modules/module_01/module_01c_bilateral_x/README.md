# Module 1c — Bilateral, Cross-Provider

> **Curriculum:** Module 1 extension — bilateral seam crosses provider boundaries (Anthropic / OpenAI / Google). First place adapter cost and lab-shape divergence become load-bearing. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) (Module 1 extension) and [`docs/treatise.md`](../../docs/treatise.md) Part II.

**Goal:** internalize what changes when the bilateral seam crosses provider
boundaries. Module 1b proved the seam works within Anthropic's two tiers.
Module 1c lets parser and composer be drawn from any of three labs, in any
combination — and forces you to feel the *adapter cost* that LIMBIC will
eventually amortize.

If you can read every line of `bilateral_x.py` and explain *why* each
provider needed its own adapter, you've completed this module.

This module is the second prototype piece of LIMBIC. See
[`docs/limbic-design.md`](../../docs/limbic-design.md) for the broader design.

## What's new vs Module 1b

| Aspect | Module 1b | Module 1c |
|---|---|---|
| Providers | Anthropic only | Anthropic, OpenAI, Google |
| Slots | 2 (`fast`, `deep`) | 6 (`<provider>-<tier>`) |
| Adapters | 1 (Anthropic only) | 3 (one per lab) |
| `max_tokens` default | 1024 | **2048** (Gemini's hidden thinking eats budget) |
| Token accounting | uniform (input/output) | normalized — billable output may exceed visible output (Gemini) |
| Failure mode | one provider down = module broken | adapter errors caught and surfaced per-call |

Read `bilateral_x.py` alongside `bilateral.py` from Module 1b. The diff is
the lesson: most of the new code is in the three adapter functions, and
they are not symmetric. Each one bends in a different way to fit the same
internal `CallResult`.

## Setup

You already have `anthropic` and `python-dotenv` from Module 1.
Module 1c adds two more SDKs:

```sh
.venv/bin/pip install openai google-generativeai
```

Make sure `.env` has all three keys set:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```

Both OpenAI and Google require billing/credit on the respective accounts.
You'll know when one is misconfigured because `--all` will mark that row
with a `⚠` and surface the error inline.

## Run

### One configuration at a time

```sh
# default: parser=anthropic-fast, composer=anthropic-deep (same as 1b's default)
.venv/bin/python level_1_modules/module_01c_bilateral_x/bilateral_x.py "Why does TLS need both client and server randoms?"

# cross-provider: cheap parser elsewhere, deep composer here
.venv/bin/python level_1_modules/module_01c_bilateral_x/bilateral_x.py --parser google-fast --composer anthropic-deep "Why does TLS need both client and server randoms?"

# the inverse: deep understanding from Gemini, terse composition from Haiku
.venv/bin/python level_1_modules/module_01c_bilateral_x/bilateral_x.py --parser google-deep --composer anthropic-fast "Why does TLS need both client and server randoms?"

# baseline (single-call) — pick any slot
.venv/bin/python level_1_modules/module_01c_bilateral_x/bilateral_x.py --baseline --composer openai-deep "Why does TLS need both client and server randoms?"
```

### The full comparison

```sh
.venv/bin/python level_1_modules/module_01c_bilateral_x/bilateral_x.py --all "Why does TLS need both client and server randoms?"
```

This runs 12 curated configurations:

- 6 baselines (one per slot)
- 3 same-provider bilateral pairs (`fast → deep` within each lab — isolates the bilateral seam from provider differences)
- 3 cross-provider bilateral pairs (illustrative — read the table for cost/quality crossovers)

Total runtime: a few minutes. Total cost: usually under a cent per `--all`.

## What you should be able to explain

Hold yourself to this. If any answer is hand-wavy, re-read the relevant
adapter or comment in `bilateral_x.py`:

1. Why does the OpenAI adapter put `system` *inside* the messages array,
   while the Anthropic adapter puts it as a top-level field? Where is it
   on the Google adapter, and why?
2. What does Gemini's `usage_metadata.total_token_count` include that
   `prompt_token_count + candidates_token_count` does not?
3. Why is `max_tokens` set to 2048 (vs 1024 in Module 1b), and which
   provider would silently fail if it stayed at 1024?
4. The `CallResult` dataclass has both `output_tokens` and
   `visible_output_tokens`. Why does the cost calculation use the former?
5. What happens to the composer call when the parser fails, and why is
   that the right behavior for a comparison harness?
6. If you wanted to add a fourth provider (say, Mistral), what specifically
   would you have to write? What would you NOT have to write?

When you can answer all six without looking, you've understood the
adapter layer that Level 2 will eventually formalize.

## Pitfalls deliberately within reach

- **Run `--all` and read the comparison table from the bottom up.** The
  cross-provider bilateral rows are usually the most expensive and the
  slowest, but sometimes produce the highest-quality answers. Whether that
  premium is justified depends on your harness's needs.
- **Try a prompt where one provider has a structural edge.** Long context
  (Gemini), audio reasoning (OpenAI's GPT-4o), tool-use clarity (Anthropic).
  The bilateral split lets you exploit the strength without inheriting the
  weakness.
- **Use `--parser google-deep` on a complex prompt and watch the thinking
  tokens.** The telemetry will print `(visible=N, +thinking=M)` showing how
  much hidden reasoning you paid for. Compare to `anthropic-deep` parser
  on the same prompt.
- **Disable `--no-ir`** on a long, ambiguous prompt and study what the parser
  flagged in `AMBIGUITIES`. Different providers surface different ambiguities
  for the same input — that itself is information about how each model
  "perceives" the question.

## Limitations of this module (still deliberate)

- **Text only.** No image, audio, or video input. Modality routing is the
  natural next module, and it's where the bilateral split goes from
  *optional* to *forced* (only Gemini accepts video, only OpenAI emits
  audio, etc.).
- **Free-text IR.** The intermediate representation between parser and
  composer is still loosely-structured plain text. JSON IR with a typed
  schema remains an open question (see `docs/limbic-design.md` §6).
- **No memory.** Each run is a fresh stateless pair, like Module 1.
- **Errors fail loud per call but don't retry.** Production routing would
  add fallback chains and circuit breakers; this module deliberately does
  not, so the underlying provider differences remain visible.
- **Pricing is approximate.** The cost numbers are useful for relative
  comparison and visceral feedback. They are NOT authoritative for
  billing — verify against each provider's pricing page if it matters.

## What this enables next

Once cross-provider bilateral feels real, the natural extensions are:

- **1d — Modality routing.** Text in, text out is the easy case. Audio in
  forces parser=OpenAI; video in forces parser=Google; large-context in
  forces parser=Gemini. The router stops being optional.
- **2 — Memory across providers.** Whose conversation history grows when
  parser and composer are different labs? How do you keep them aligned
  without re-shipping the whole transcript twice?
- **2b — Provider-agnostic memory layer.** The first real Level-2 string —
  takes the messy adapter-by-adapter pattern of 1c and abstracts it
  behind a uniform conversation interface. This is where LIMBIC's IR
  starts becoming a real component.
- **Module 4 — Faculty-tagged evals.** Run `--all` over a fixed eval set
  with faculty tags, and now you have *data* to route on instead of
  guesses. This is the prerequisite for LIMBIC v0.

The progression remains cumulative. Each module isolates one new variable.
By Module 4, every routing decision will have an empirical defense.
