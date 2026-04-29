# Module 1 — The Bare Model Call

> **Curriculum:** Movement One, Module 1 — *The Bare Model Call*. The canonical bare-call module — one round trip, no abstraction, no state. See [`docs/curriculum.md`](../../docs/curriculum.md#module-1--the-bare-model-call) and [`docs/treatise.md`](../../docs/treatise.md) Part I.

**Goal:** internalize what a single model invocation actually is. No
abstraction. No state. No tools. Just one round trip with prompt → text.

If you can read every line of `bare_call.py` and explain *why* it's there,
you've completed this module. That's the bar — not "ran without crashing,"
but "no line feels like cargo-cult boilerplate."

## Setup

From the repo root:

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit .env and put your real API key in
```

## Run

Three deliberate exercises. Run each, watch the telemetry on stderr, feel
the lesson.

### 1. The basic call

```sh
python level_1_modules/module_01_bare_call/bare_call.py "What is 2+2?"
```

You'll see the answer on stdout, and on stderr a line like:

```
[model=claude-sonnet-4-6 in=12 out=7 cost=$0.000141 latency=0.94s]
```

That number — `cost=$0.000141` — is the visceral piece. Every call has a
price tag. Most agentic systems fail in production because nobody watched
the price tag in development.

### 2. Statelessness

Run this twice, in two separate invocations:

```sh
python level_1_modules/module_01_bare_call/bare_call.py "My name is Alice."
python level_1_modules/module_01_bare_call/bare_call.py "What is my name?"
```

The second call has no idea. The model is stateless across calls. *Memory
is not free; it is something you bring.* Module 2 builds the smallest
possible memory.

### 3. Sampling

Edit the call to set `temperature=1.0` (in `__main__` or wherever you
choose to thread it through), and run the same prompt three times:

```sh
python level_1_modules/module_01_bare_call/bare_call.py "Tell me a one-line joke about a fox."
python level_1_modules/module_01_bare_call/bare_call.py "Tell me a one-line joke about a fox."
python level_1_modules/module_01_bare_call/bare_call.py "Tell me a one-line joke about a fox."
```

Three different jokes. Now set `temperature=0.0` and rerun three times —
you'll see the same joke (or very nearly). Sampling is a knob, not a
detail. Lessons that depend on reproducibility set it to 0; lessons that
exercise creativity crank it up.

## Pitfalls deliberately within reach

These are doors you should open at least once:

- **Forget `max_tokens`.** Try removing it — the SDK requires it. The fact
  that this is required is itself a design lesson: stopping rules are not
  afterthoughts, they're part of the contract.
- **Pass no system prompt vs. a tight system prompt.** Compare the answer
  to "Explain recursion" with no system, then with
  `system="Answer in one sentence, suitable for a 10-year-old."` Same
  question, different role-typed context, different answer.
- **Watch the cost on a long question.** Try a prompt like "Write a 500
  word essay on..." and watch `out=` climb. Output tokens cost 5× input
  tokens on Sonnet 4.6.

## What you should be able to explain

Hold yourself to this. If any answer is hand-wavy, re-read the relevant
comment in `bare_call.py`:

1. Why does `max_tokens` exist? What happens if you omit it?
2. Why do we read `block.type` before reading `block.text`?
3. Where is the conversation history stored between calls?
4. What's the difference between `temperature=0` and `temperature=1`?
5. Why is the answer printed to stdout but the telemetry to stderr?
6. What does the system prompt do that the user message can't?

When you can answer all six without looking, you're ready for Module 2.
