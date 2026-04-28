# Module 1b — The Bilateral Split

**Goal:** internalize what changes when you split *understanding the input*
from *composing the output*. Module 1 collapsed both into one model call.
Module 1b separates them and lets you assign different models (different
tiers, different costs) to each role.

If you can run all six configurations on the same prompt and articulate *why*
you would prefer each one in some specific harness context, you've completed
this module. The bar is not "ran without crashing" — it's "felt the seam."

This is the prototype for the bilateral piece of LIMBIC. See
[`docs/limbic-design.md`](../../docs/limbic-design.md) for the broader design
and why we are starting here.

## What's new vs Module 1

| Aspect | Module 1 | Module 1b |
|---|---|---|
| Model calls per turn | 1 | 1 (baseline) or 2 (bilateral) |
| System prompt | optional, default empty | load-bearing — defines parser vs composer roles |
| Tiers | hard-coded sonnet | `fast` (haiku) and `deep` (sonnet) |
| Telemetry | per-call | per-call **plus** total across the pipeline |

Read `bilateral.py` top-to-bottom alongside Module 1's `bare_call.py`. The
diff is the lesson.

## Setup

You already did this for Module 1. Confirming:

```sh
# from the repo root
.venv/bin/python -c "import anthropic; print(anthropic.__version__)"
```

Should print a version string (anything ≥ 0.97). If not, re-run the Module 1
setup.

## Run

### One configuration at a time

```sh
# default: parser=fast (haiku), composer=deep (sonnet)
.venv/bin/python level_1_modules/module_01b_bilateral/bilateral.py "Explain why TLS handshakes need both random nonces."

# flip the assignment
.venv/bin/python level_1_modules/module_01b_bilateral/bilateral.py --parser deep --composer fast "Explain why TLS handshakes need both random nonces."

# baseline (single-call, no parser) — same as Module 1 but with telemetry
.venv/bin/python level_1_modules/module_01b_bilateral/bilateral.py --baseline --composer deep "Explain why TLS handshakes need both random nonces."
```

The final answer goes to stdout. The parser's intermediate analysis (IR) and
all telemetry go to stderr — same convention as Module 1, so you can pipe
the answer downstream without the trace polluting it.

### All configurations at once (the comparison)

```sh
.venv/bin/python level_1_modules/module_01b_bilateral/bilateral.py --all "Explain why TLS handshakes need both random nonces."
```

This runs all six configurations on the same prompt and prints a comparison
table at the end — token counts, total cost, total latency. The lesson is in
*which configuration won at what*. Often:

- **`bilateral fast/deep`** — parser cheap, composer smart. Often the cost
  sweet spot when the composer is the bottleneck on quality.
- **`bilateral deep/fast`** — parser smart, composer cheap. Useful when the
  question is hard to *understand* but easy to *answer once understood*.
- **`baseline deep`** — usually the quality ceiling, sometimes the cost ceiling.
- **`bilateral fast/fast`** — usually the cost floor. Quality varies.

There is no universally best configuration. Which one wins depends on whether
the prompt's hard work is parsing or composing — and that is *exactly* what
LIMBIC will eventually route on.

## What you should be able to explain

Hold yourself to this. If any answer is hand-wavy, re-read the relevant code
or comment in `bilateral.py`:

1. Why does the parser have its own system prompt, and why does it explicitly
   say "do not answer the question"?
2. What does the composer see as `messages[0].content`? (Hint: it is *not*
   the user's original prompt.)
3. Why is the parser's text put on stderr instead of stdout?
4. Why are the parser and composer latencies *added*, not maxed?
5. What happens to total cost when you swap parser tier from `deep` to
   `fast`? When does this matter, and when does it not?
6. For what kind of prompt would you expect `bilateral deep/fast` to beat
   `baseline deep` on quality? When would it lose?

When you can answer all six without looking, you understand the seam.

## Pitfalls deliberately within reach

- **Run `--all` on a prompt that's structurally easy** (e.g., "What is 2+2?")
  and you'll see all configurations produce essentially the same answer at
  wildly different costs. Lesson: bilateral split is overhead, not value, on
  trivial prompts.
- **Run `--all` on a prompt that requires real interpretation** (a long
  ambiguous user request, a poorly-worded technical question) and watch
  the answers diverge. Lesson: the seam matters when the input *needs*
  understanding, not just executing.
- **Run with `--parser deep --composer fast`** on a creative writing prompt
  and watch the prose quality drop even though the parser "understood
  perfectly." Lesson: composition is its own faculty, distinct from
  understanding.
- **Try a question with intentional ambiguity** and watch what the parser
  surfaces in the AMBIGUITIES section. The composer's handling of those
  flagged ambiguities is a window into how role-typed context propagates.

## Limitations of this module (deliberate)

- **Anthropic only.** Cross-provider bilateral (parser ∈ Anthropic|OpenAI|Google)
  is Module 1c. Limiting to one lab here keeps the bilateral effect from being
  confounded with provider differences.
- **No modality split.** Text in, text out. Modality routing is what makes
  the bilateral split *forced* rather than optional, and that lesson belongs
  in Module 1c or beyond.
- **Free-text IR.** The intermediate representation between parser and
  composer is loosely-structured plain text. JSON IR with a typed schema is
  one of the open questions in `docs/limbic-design.md` — left open
  deliberately, not yet decided.
- **No memory.** Each run is a fresh pair of stateless calls, like Module 1.
  Multi-turn bilateral is Module 2-ish territory.

These limits are not bugs. They isolate the variable being tested (the
bilateral split itself) so that any cost/quality crossover you observe is
attributable to that variable and not to confounds.

## What this enables (Module 1c and beyond)

Once the bilateral seam feels real, the natural extensions are:

- **1c — Cross-provider bilateral.** Parser and composer can be from
  different labs. Modality forces this: video → Gemini parser → Claude
  composer becomes a one-line routing decision.
- **1d — Asymmetric IR.** What happens if the parser's IR is JSON instead of
  free text? Does composer quality go up or down?
- **2 — Memory across bilateral turns.** Whose context grows: the parser's
  or the composer's? Probably the composer's, but design that deliberately.
- **Module 4 — Faculty-aware evals.** Score each configuration on a fixed
  eval set tagged with faculty + modality. *This is where LIMBIC starts to
  have data.*

The progression is cumulative. Each module adds one variable. By the time
LIMBIC v0 is built, every routing decision will have an empirical defense.
