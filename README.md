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

Subsequent modules are built on demand, in order.

## Design notes

| Doc | Purpose |
|---|---|
| [`docs/limbic-design.md`](docs/limbic-design.md) | Future-project sketch — multi-axis dynamic router (direction × faculty × modality × cost). Module 1b is the prototype of its bilateral axis. |
