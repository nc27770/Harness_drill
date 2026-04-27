"""Module 1 — The Bare Model Call.

The smallest meaningful program that talks to a language model. One function,
one API call, one print. Nothing else.

Why this exists: every agentic system you will ever build is a recursive
elaboration of this. A scaffolded research agent is — at its core — many of
these calls in a clever pattern. If this single call doesn't feel obvious in
your bones, no amount of LangGraph or MCP scaffolding will make the higher
levels feel obvious either.

Read top to bottom. Every comment ties code to a concept from the curriculum.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Load ANTHROPIC_API_KEY (and ANTHROPIC_MODEL, if set) from a .env file at the
# repo root. The Anthropic SDK reads ANTHROPIC_API_KEY from the environment
# automatically — we never pass it explicitly to the client. Keys live in
# environment variables so they don't end up in source control.
load_dotenv()

# Pricing snapshot for Sonnet 4.6 as of 2026-04. ALWAYS verify against
# console.anthropic.com before using these for anything that matters — pricing
# drifts. The point of printing cost on every call is the visceral feedback
# ("every token is paid for at every Think"), not exact accounting.
PRICE_PER_MTOK_INPUT = 3.00    # USD per 1,000,000 input tokens
PRICE_PER_MTOK_OUTPUT = 15.00  # USD per 1,000,000 output tokens

# Default model. Override per-environment via the ANTHROPIC_MODEL env var
# (see .env.example at the repo root).
DEFAULT_MODEL = "claude-sonnet-4-6"


# ─────────────────────────────────────────────────────────────────────────────
# The data we care about, after a call
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Response:
    """The shape we care about for a single model call.

    The SDK returns a richer object (stop reasons, message IDs, content-block
    polymorphism, ...). We discard everything except what's pedagogically
    useful here. When you need more — e.g. handling stop_reason == "tool_use"
    in a later module — you'll add fields back deliberately.
    """

    text: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    cost_usd: float


# ─────────────────────────────────────────────────────────────────────────────
# The call
# ─────────────────────────────────────────────────────────────────────────────


def call_model(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    model: str = DEFAULT_MODEL,
) -> Response:
    """One question in, one answer out. No memory. No tools. No retries.

    This is the Read → Think → Act loop collapsed to its smallest form: the
    model "reads" your prompt, "thinks" once, "acts" by emitting text. There
    is no second turn, no tool call, no branching. Higher modules will
    elaborate this into all of those.
    """
    # The client picks up ANTHROPIC_API_KEY from the environment. No global
    # mutable state, no singleton — just instantiate when you need it.
    client = anthropic.Anthropic()

    # Time the round trip. The Think phase dominates wall-clock time on most
    # prompts ("energy concentration"). Watching this number teaches you which
    # design choices are cheap and which are expensive.
    started_at = time.perf_counter()

    # Build the request kwargs. We omit `system` entirely when not provided
    # rather than passing None, because the API treats absence and None
    # differently for some parameters and we want the cleanest possible
    # request when the user doesn't set a system prompt.
    request: dict = {
        "model": model,
        # max_tokens is REQUIRED. It is the hard cap on the model's reply
        # length. Without it the SDK has no fallback; with it, you have a
        # spending ceiling on this call. "Sampling and stopping as
        # hyperparameters" — stopping rules are not afterthoughts, they are
        # part of the program's contract.
        "max_tokens": max_tokens,
        # temperature shifts sampling. 0.0 = greedy (most likely token at
        # each step), giving roughly reproducible outputs and making lessons
        # diffable. 1.0 = full sampling distribution — try the same prompt
        # three times and feel the variance. Anything in between trades
        # between the two.
        "temperature": temperature,
        # The actual question. The API is STATELESS: this list is the entire
        # universe of context the model has for this call. There is no hidden
        # conversation history. If you want continuity across calls, you
        # bring it (Module 2 onward).
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    if system is not None:
        # The system prompt sets role / persona / constraints. It is the
        # most powerful single lever in the API and the cheapest to abuse.
        # If you don't pass one, the model has no instructions beyond its
        # post-training defaults. Context is role-typed, and the role you
        # put a token under changes how it lands.
        request["system"] = system

    response = client.messages.create(**request)

    elapsed = time.perf_counter() - started_at

    # response.content is a list of typed blocks (text, tool_use, thinking,
    # ...). We only sent text and got text back, so we collect the text
    # blocks. ALWAYS check block.type — directly indexing content[0].text
    # would crash the moment the model emits anything else (e.g. a thinking
    # block, which becomes relevant in later modules).
    text = "".join(b.text for b in response.content if b.type == "text")

    # Token counts come from the response, not from client-side estimation.
    # Trust the server's accounting; client-side tokenizers drift across
    # model versions and are a frequent source of off-by-some bugs.
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    cost = (
        input_tokens * PRICE_PER_MTOK_INPUT / 1_000_000
        + output_tokens * PRICE_PER_MTOK_OUTPUT / 1_000_000
    )

    return Response(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_seconds=elapsed,
        cost_usd=cost,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _read_question() -> str:
    """Question from argv, or stdin if argv is empty and stdin is piped."""
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    print(
        "usage: bare_call.py 'your question'\n"
        "       echo 'your question' | bare_call.py",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    question = _read_question()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    result = call_model(question, model=model)

    # Answer to stdout — pipe-friendly. You can do:
    #     python bare_call.py 'list 3 fruits' | grep -i apple
    # and the telemetry on stderr won't pollute the pipe.
    print(result.text)

    # Telemetry to stderr — visible in your terminal, NOT captured when you
    # redirect stdout. Splitting the two streams is a deliberate interface
    # choice that makes Module 1's program well-behaved in Unix terms.
    print(
        f"\n[model={model} "
        f"in={result.input_tokens} out={result.output_tokens} "
        f"cost=${result.cost_usd:.6f} "
        f"latency={result.latency_seconds:.2f}s]",
        file=sys.stderr,
    )
