# Zero to Hero — A Self-Directed Curriculum in Harness Engineering

**Subject:** A practical, code-grounded curriculum for learning harness engineering from first principles to advanced patterns. Designed to build engineering muscle through deliberate practice, not theoretical understanding.

**Audience:** Self. Someone with software engineering background but no prior exposure to LangChain, LangGraph, or any agent framework. Learning as an academic / weekend project, not toward a deployable system.

**Outcome:** By the end, you will have written every pattern that defines modern agentic systems with your own hands. You will have done it on toy use cases that exercise the architectural primitives without requiring real infrastructure. You will be able to read someone else's agent code and understand what they did, why, and where it might break — not because you memorized framework patterns but because you built each pattern yourself from the kernel.

**Framing:** This is muscle-building, not credential-building. The path is naive on purpose — the goal is to develop intuitions that survive when the framework changes. Every pattern is exercised through a use case small enough to fit in a few hundred lines of code, large enough to demonstrate the pattern's actual properties.

**Tooling assumed:** Python and a capable LLM API key are the only hard requirements. A text editor and SQLite cover most modules' state needs. Beyond that, **tooling is appropriate-not-prescribed**: pick the labs and surfaces that fit the lesson at hand. Some modules (notably the Module 1 extension in this project) reach for multiple labs (Anthropic + OpenAI + Google), object storage (S3), async-job APIs (Sora, Veo), or a small web surface (FastAPI + Gradio + nginx) when those are what the lesson actually exercises. The principle: tooling earns its place when the *lesson* needs it, not when convention suggests it. No managed agent frameworks (LangChain, LangGraph) until Movement Three.

**Companion docs:**

- [`treatise.md`](treatise.md) — the conceptual map (Parts I–VIII) that this curriculum exercises in code.
- [`measurement-seam.md`](measurement-seam.md) — frozen-weight inference as a single measurement act; the lens behind Module 1's deep dive.
- [`seam-parameters.md`](seam-parameters.md) — locked architectural decision: temperature, seed, voice, streaming, caching live in the dispatcher rather than as new curriculum modules.
- [`limbic-design.md`](limbic-design.md), [`limbic-image-video-generative.md`](limbic-image-video-generative.md) — forward design for the multi-axis router (L3.1) and the modality work that anchors our extended Module 1.

---

## Code organization — three layers

The codebase is organized in three layers that map cleanly to the curriculum's progression from primitives to systems:

```
.
├── level_1_modules/    Layer 1 — the 15 modules + 8 deeper territories.
│                       Each module is a self-contained CLI. One lesson at
│                       the seam per module. No frameworks until M12.
│
├── level_2_strings/    Layer 2 — stringings of modules. Compositions that
│                       glue multiple level-1 modules into a single user-
│                       facing surface. The dispatcher in
│                       string_01_dispatch/ is the first example.
│
└── level_3_agents/     Layer 3 — full agentic solutions for specific use
                        cases. Built using either the own micro-framework
                        that emerges from Movement Two, or production
                        frameworks (LangGraph, etc.) once Movement Three
                        is done.
```

**Why three layers and not one:** primitives, compositions, and applications have different design languages and failure modes. Conflating them makes everything harder to reason about. The same kernel powers all three; the abstractions stack.

**The Layer 2 / Layer 3 distinction in practice:**
- A *string* (Layer 2) is a thin orchestration of existing level-1 modules with a single dispatch concern. The dispatcher routes (input, output) cells to the right module CLI. No new agent loop.
- An *agent* (Layer 3) is a full Read-Think-Act loop with tools, memory, and recovery. It uses level-1 modules and level-2 strings as building blocks, but its top-level shape is the agent loop.

---

## How to Use This Curriculum

The curriculum is structured as 15 modules, organized into three movements:

**Movement One — The Kernel (Modules 1-5).** Build the agent loop from scratch. No frameworks. Bare API calls, hand-managed state, explicit tool dispatch. This is where the deepest understanding comes from. Skip this and the rest is shallow.

**Movement Two — Patterns (Modules 6-11).** Add the patterns that make single agents capable: tool ecosystems, retrieval, memory, multi-agent topologies, persistence, observability. Still without frameworks. By the end of this movement, you have written your own micro-framework.

**Movement Three — Frameworks and Production Concerns (Modules 12-15).** Now learn LangGraph and the Lang\* ecosystem. Compare what you built to what they built. See what they got right, what they got wrong, what you would build differently. By this point, you can read their source code with comprehension.

Each module has:

- **Learning goal** — the specific muscle being built
- **Use case** — the toy problem that exercises the pattern
- **What to write** — the code you'll produce (no code in this document; just specifications)
- **What it should teach you** — the intuition that survives after you forget the syntax
- **Pitfalls to encounter** — failures you should produce before solving, because the failures are the lesson
- **Stretch exercise** — optional deeper exploration

Time budget is intentionally not specified. Some modules will take an evening; some will take a weekend; some will take two weekends if you go deep. The point is the muscle, not the schedule.

---

## Status snapshot

| Module | Title | Status | Path |
|---|---|---|---|
| 1 | The Bare Model Call | ✅ done | `level_1_modules/module_01/module_01_bare_call/` |
| 1 (extension) | Modality matrix + asset-conditioning | ✅ done | `level_1_modules/module_01/module_01b_*` … `module_01l_*` |
| L2 (extension) | Dispatcher (cover app over Module 1) | ✅ done | `level_2_strings/string_01_dispatch/` |
| 2 | The Conversation Loop | ✅ done | `level_1_modules/module_02_conversation/` |
| 3 | The Three-Phase Loop, By Hand | ✅ done | `level_1_modules/module_03_three_phase/` |
| 4 | Native Tool Calling | ✅ done | `level_1_modules/module_04_native_tools/` |
| 5 | The Naive Agent Class | ✅ done | `level_1_modules/module_05_agent/` |
| L2 (extension) | Witness — Mind & Machine log over M2–M5 | ✅ done | `level_2_strings/string_02_witness/` |
| 6 | RAG From Scratch | ⏳ pending | — |
| 7 | Memory: Working / Episodic / Session / Long-Term | ⏳ pending | — |
| 8 | Multi-Agent: Supervisor Pattern | ⏳ pending | — |
| 9 | Multi-Agent: Pipeline / Swarm / Debate | ⏳ pending | — |
| 10 | Persistence and Resumption | ✅ done (built early, as **M5 ⊕ M10** — the durable Mind) | `level_1_modules/module_10_persistence/` |
| 11 | Observability: Traces and Telemetry | ⏳ pending | — |
| 12 | LangGraph: First Encounter | ⏳ pending | — |
| 13 | LangGraph: Multi-Agent and Persistence | ⏳ pending | — |
| 14 | Designed Pauses: Interrupt and Resume | ⏳ pending | — |
| 15 | Observability with LangSmith / Langfuse | ⏳ pending | — |

**A note on the Module 1 extension:** the curriculum's stated Module 1 is a single `bare_call.py`. We have gone substantially deeper before moving on — covering the bilateral split (1b), three-lab cross-coverage (1c), modality input across image / audio / video (1d–1f), audio output (1g), the modality matrix (1h), image and video output (1i / 1j), and asset-conditioned image and video output (1k / 1l). The dispatcher in `level_2_strings/string_01_dispatch/` strings these into a single user-facing surface.

This expansion is project-specific elaboration of Module 1's territory — *the seam*, the boundary between the world inside the model and the world outside. Per [`measurement-seam.md`](measurement-seam.md), this is the only inference gate; everything from Module 2 onward is scaffolding upstream or downstream of it. Closing the seam thoroughly across modalities and labs before moving to scaffolding is consistent with the curriculum's "build from first principles" ethos and is the foundation later modules will rest on.

**A note on Movement One (M2–M5) and the early Module 10.** M2–M5 are built as self-contained CLI kernels (the diff between each is the lesson) and are *animated* by the Witness — a Layer-2 string (`string_02_witness/`) that spans them, serializing a per-thread **Mind & Machine log** to `traces/`. Module 10 was built ahead of order, **fused with Module 5's declarative agent**, because the user wanted the canonical agent born *durable* — a `(config, state)` Mind that outlasts its process — rather than retrofitting persistence later. Its data contract is frozen in [`module_10_persistence/SCHEMA.md`](../level_1_modules/module_10_persistence/SCHEMA.md). M5 is the *naive in-process* agent; M10 is the *mature durable* Mind — the contrast is itself a lesson. Modules 6–9 and 11–15 remain pending.

---

## Movement One — The Kernel

### Module 1 — The Bare Model Call

**Status:** ✅ done; extended with the modality matrix and asset-conditioning (1b–1l) plus a Layer-2 dispatcher.

**Learning goal:** Internalize what a single model invocation actually is. No abstraction, no framework, just the API.

**Use case:** Build a command-line tool that takes a question, sends it to the model, prints the answer. That is the entire program.

**What to write:**

- A Python script with a function that takes a string, calls the API, returns the response
- A CLI wrapper that accepts a query and prints the result
- Configuration for the model (provider, model name, max tokens, temperature)

**What it should teach you:**

- The model is stateless. Every call is independent. Memory is something you bring; the model has none across calls.
- Latency is real. A frontier model takes seconds. This shapes everything downstream.
- Cost is real. Print the token counts. Multiply by the price. See where money goes.
- The response is just text. Whatever structure you want, you must impose.

**Pitfalls to encounter:**

- Forgetting to set a max_tokens limit and burning unexpected cost
- Assuming the model "remembers" your previous question (it doesn't; you'd have to send it again)
- Prompting badly and getting wandering responses; learn to write a tight system message

**Stretch exercise:** Implement the same call against three providers (Anthropic, OpenAI, a local model via Ollama). Notice what differs. The provider abstractions are not free.

**Project elaboration (1b–1l):** the stretch exercise above became its own arc — three providers (1c), then asset-input modalities (image/audio/video — 1d/1e/1f), audio output (1g), the consolidated modality matrix (1h), image and video output (1i / 1j), and asset-conditioned image and video (1k / 1l). All 16 cells of the (input × output) modality matrix are now covered. See `level_1_modules/*/README.md` per module and [`limbic-image-video-generative.md`](limbic-image-video-generative.md) §4.1 for the design grounding.

**Project elaboration (Layer 2):** the per-module CLIs are composed by a Gradio + FastAPI dispatcher at `level_2_strings/string_01_dispatch/`. This is the first Layer-2 string and predates the curriculum's introduction of strings — it is here because closing the seam across all 16 cells made a single user-facing surface useful. The dispatcher is a routing concern only, not an agent loop; that distinction matters for Layer 3 later.

---

### Module 2 — The Conversation Loop

**Status:** ⏳ next.

**Learning goal:** Understand why context window management is the central engineering problem.

**Use case:** Build a CLI chatbot. The user types messages; the bot responds; the conversation continues until the user types `exit`.

**What to write:**

- A loop that reads user input
- A list (your conversation history) that grows with each turn
- For each turn: append user message, send full history to model, append model response, print response

**What it should teach you:**

- Conversation memory is *you* maintaining the list. The model sees only what you send.
- The list grows unboundedly. After 50 turns, you're sending a lot of tokens. Cost balloons.
- The model sometimes forgets what was said earlier even though it's in context. Position matters.
- The model treats the system message specially. Its placement and content shape every response.

**Pitfalls to encounter:**

- Forgetting to include system message and getting personality drift
- Letting context grow until you hit the model's context limit and the API errors
- Including too much (entire response history) when only the most recent matters

**Stretch exercise:** Implement a "summarize and compress" function that, when conversation history exceeds N tokens, asks the model to summarize earlier turns and replaces them with the summary. Notice how summary quality affects subsequent conversation coherence.

---

### Module 3 — The Three-Phase Loop, By Hand

**Status:** ⏳ pending.

**Learning goal:** Implement Read-Think-Act explicitly. This is the kernel of every agent.

**Use case:** A homework helper. The user asks a math question. The agent should sometimes answer directly (when easy), sometimes ask the user a clarifying question, sometimes "compute" by calling a fake calculator function. The agent decides which.

**What to write:**

- A function `read()` that assembles the full prompt: system instructions explaining the role, conversation history, available "actions" the agent can take (answer, ask, calculate)
- A function `think()` that calls the model and returns its response
- A function `act()` that parses the model's response — looking for a structured marker like `ACTION: answer` or `ACTION: ask` or `ACTION: calculate(expression)` — and dispatches accordingly
- A loop that runs the three phases until the agent answers or asks the user

**What it should teach you:**

- The model needs to be told what actions are available, in the system prompt, with examples
- Parsing the model's structured output is brittle. Sometimes it produces the wrong format. You need to handle that.
- The agent loop has natural stopping conditions. Decide them explicitly.
- "Tools" are just functions you call when the model requests them. The magic is in the agent loop choosing.

**Pitfalls to encounter:**

- The model produces `ACTION: answer` plus extra commentary you don't expect
- The model invents an action you didn't define (`ACTION: search_web` when you only supported three actions)
- The loop runs forever because the model keeps calling actions without ever answering

**Stretch exercise:** Add a `give_up` action so the agent can decide when it cannot answer. Notice how having a graceful exit changes the model's behavior — it tries other things less often.

---

### Module 4 — Native Tool Calling

**Status:** ⏳ pending.

**Learning goal:** Replace your hand-parsed action format with the model provider's native tool calling. Understand what it gives you and what it doesn't.

**Use case:** Same homework helper, but use Anthropic's or OpenAI's tool calling API to define `calculate` and `ask_user` as proper tools.

**What to write:**

- Tool definitions with JSON Schema (name, description, input schema)
- The agent loop now sends `tools` in the API request
- When the model calls a tool, the response has a structured `tool_use` block
- Dispatch based on tool name, get result, send back as `tool_result`
- Loop until model responds without a tool call

**What it should teach you:**

- Native tool calling is structured parsing for free. The provider validates the schema; you just dispatch.
- The conversation history now includes tool calls and tool results, in distinct roles.
- The model is much more reliable at producing tool calls than at producing your homemade action format.
- The same loop pattern applies whether you have one tool or ten.

**Pitfalls to encounter:**

- Forgetting to include `tool_choice` policy and getting the model to ignore your tools
- Returning tool results in the wrong format and confusing the model
- Tool descriptions that are too vague; the model misuses the tool

**Stretch exercise:** Add a tool that intentionally fails 30% of the time. Watch the model's behavior — does it retry? Does it give up? Does it explain the failure to the user? Tweak the tool's error message and see how the model adapts.

---

### Module 5 — The Naive Agent Class

**Status:** ⏳ pending.

**Learning goal:** Wrap everything you've built into a small reusable agent class. This is the moment you've built your own micro-framework.

**Use case:** Refactor your homework helper into a class `Agent` that takes a system prompt, a list of tools, and a model configuration. Instantiate it. Use it.

**What to write:**

- An `Agent` class with `__init__` taking system prompt, tools, model config
- A method `run(user_input)` that runs the full loop and returns the final answer
- A method `chat()` for multi-turn interaction (the conversation loop from Module 2 + the tool calling from Module 4)
- Internal state: conversation history, iteration counter, max iteration limit

**What it should teach you:**

- The agent's API is simple from the outside; the complexity is internal
- Configuration matters: max iterations, temperature, tool choice policy, etc.
- Reusability comes from clean separation of concerns: tools are independent of the agent class

**Pitfalls to encounter:**

- Hardcoding the model provider; later you'll want to swap
- Forgetting to handle the iteration limit gracefully
- Bundling state in the class instance such that you can't run two agents in parallel

**Stretch exercise:** Make the agent class support multiple model providers behind a single interface (this is a tiny LiteLLM, conceptually). The agent code should not change when switching providers.

---

## Movement Two — Patterns

### Module 6 — Retrieval-Augmented Generation, From Scratch

**Status:** ⏳ pending.

**Learning goal:** Understand why retrieval is its own engineering territory and how it integrates with the agent loop.

**Use case:** Build a personal Q&A bot over your own notes. Take a folder of markdown files (your blog drafts, journal, technical notes — anything personal). The agent answers questions using these notes as ground truth.

**What to write:**

- A document chunker that breaks markdown files into chunks of ~500 tokens each, with overlap
- An embedding pipeline using a hosted embedding API (Cohere, OpenAI, Voyage) or a local model
- A simple vector store (in-memory list of (chunk, embedding) tuples is fine for hundreds of chunks; SQLite with FAISS for thousands)
- A retrieval function that takes a query, embeds it, finds top-K chunks by cosine similarity
- A modified agent that, before each Think, retrieves relevant chunks and includes them in context

**What it should teach you:**

- Chunking strategy matters more than people admit. Bad chunks produce bad retrieval.
- Embeddings are not magic; they're a similarity heuristic that breaks for specific kinds of queries
- The model can answer wrong even with right retrieval; it can answer right even with bad retrieval (using its own knowledge); both failures look similar from outside
- Retrieval is a tool, but a special tool that runs before every Think rather than on demand

**Pitfalls to encounter:**

- Retrieval returns plausible-but-wrong chunks; the model confidently cites them
- The model ignores retrieved context and answers from training data; you can't tell from the output
- Chunking that breaks paragraphs in awkward places; the chunks lose meaning

**Stretch exercise:** Implement hybrid retrieval — keyword search (BM25) plus vector search, fused via reciprocal rank fusion. Notice which queries each method handles better.

---

### Module 7 — Memory: Working, Episodic, Session, Long-Term

**Status:** ⏳ pending.

**Learning goal:** Understand the four temporal layers of state by implementing each, distinctly.

**Use case:** A personal assistant that remembers your preferences over time. Across sessions, it should remember that you like long replies, prefer Python over Rust, are working on a project called X. Within a session, it should track what you've discussed. Within a single response, it should hold relevant context.

**What to write:**

- **Working memory:** the prompt construction logic that selects what goes in this Think
- **Episodic memory:** an in-memory list per agent invocation, tracking the back-and-forth
- **Session memory:** a SQLite table per user with conversation history and learned facts (preferences, ongoing topics)
- **Long-term memory:** another SQLite table with extracted facts that persist across users (or, for personal use, persist across all your sessions)

**What it should teach you:**

- Each layer has different write semantics and different read semantics
- Long-term memory needs an *extraction* step — the agent decides what to remember
- Session memory grows; you need a strategy for what to keep and what to summarize
- Working memory is reconstructed every Think; the upstream layers are sources

**Pitfalls to encounter:**

- Stuffing all of session memory into working memory, blowing out context
- Long-term memory accumulates contradictions ("user likes X" and "user no longer likes X" both stored)
- Memory extraction extracts trivia ("user said hello") instead of meaningful facts

**Stretch exercise:** Implement a memory consolidation step that runs periodically (e.g., end of session). It looks at session memory, extracts new long-term facts, and removes redundant or stale entries from long-term memory. This is closer to how real memory systems behave.

---

### Module 8 — Multi-Agent: Supervisor Pattern

**Status:** ⏳ pending.

**Learning goal:** Build the supervisor pattern from scratch. Understand why one agent isn't always enough.

**Use case:** A research assistant. The supervisor receives a research question. It delegates to specialist agents:

- A *web research* agent (uses a fake web search tool that returns canned results)
- A *summarization* agent (synthesizes findings)
- A *citation checker* agent (verifies that claims have sources)

The supervisor coordinates them, gathers results, presents the final answer.

**What to write:**

- Three sub-agent classes (each a simpler `Agent` with focused tools and prompts)
- A supervisor class that has a tool to invoke each sub-agent
- The supervisor's tools are essentially "ask the research agent X" or "have summarization agent process Y"
- Each sub-agent runs its own loop independently, returns to the supervisor
- The supervisor synthesizes the final answer

**What it should teach you:**

- Sub-agents are agents in their own right; they have their own loops, their own state
- Communication between agents happens through structured messages (tool calls and tool results)
- The supervisor needs good understanding of when to invoke which sub-agent — bad delegation = bad results
- Cost multiplies; what was one agent's loop is now four agents' loops

**Pitfalls to encounter:**

- Supervisor calls the wrong sub-agent for a task and gets a useless result
- Sub-agents run forever (infinite loop) and the supervisor has no way to stop them
- State leaks between sub-agents in unintended ways

**Stretch exercise:** Add a *fact checker* sub-agent that the supervisor calls *after* the summarization agent. Make it disagree sometimes. Now the supervisor must reconcile contradictions. Notice how this is harder than it sounds.

---

### Module 9 — Multi-Agent: The Other Three Topologies

**Status:** ⏳ pending.

**Learning goal:** Build pipeline, swarm, and debate patterns. See where each is appropriate.

**Use cases:**

**Pipeline pattern:** A blog-post writer. Stage 1 generates an outline. Stage 2 expands each outline section into prose. Stage 3 edits for tone and clarity. Stage 4 fact-checks. The output of each stage feeds the next. No backtracking.

**Swarm pattern:** A simulation of three agents collaboratively writing fiction. Each is a different "character" with their own voice. They take turns continuing the story. They can prompt each other ("Hey, Character B, what would you say next?"). State is the shared story so far.

**Debate pattern:** A decision-making assistant. The user describes a decision they're facing. A "Pro" agent argues for one option. A "Con" agent argues against. A "Judge" agent reads both arguments and recommends a decision with reasoning.

**What to write:**

- Three separate small projects, each implementing one topology
- Common building blocks (the `Agent` class from Module 5) reused
- Different orchestration patterns (linear pipeline, peer-to-peer turn-taking, adversarial-then-judge)

**What it should teach you:**

- Each topology has distinct properties around determinism, coherence, cost, and recovery
- Pipeline is most predictable but least flexible
- Swarm is most flexible but hardest to constrain
- Debate produces higher quality on contested questions but at 3x cost
- Real systems often combine topologies (pipeline of swarms, supervisor of debates, etc.)

**Pitfalls to encounter:**

- Pipeline where one stage produces output the next stage can't parse
- Swarm that goes off-rails because no agent has authority to stop it
- Debate where Pro and Con converge to the same answer (because the model is the same model on both sides)

**Stretch exercise:** Combine two topologies. For instance, a pipeline whose first stage is a debate (debate to decide what topic to write about), then the writing pipeline proceeds. Notice the orchestration complexity multiplies.

---

### Module 10 — Persistence and Resumption

**Status:** ⏳ pending.

**Learning goal:** Build checkpoint-and-resume from scratch. Understand why this is non-trivial.

**Use case:** A long-running research project agent. It runs for hours, doing many iterations. At any point, the user can close their laptop. Days later, they resume; the agent picks up where it left off.

**What to write:**

- A checkpointer interface: `save_state(session_id, state)` and `load_state(session_id)`
- Implement against SQLite (state serialized as JSON or pickle)
- Modify your `Agent` class to checkpoint after every iteration
- A resume API: given a session_id, load state, continue the loop
- Test by killing the Python process mid-execution and restarting from the saved state

**What it should teach you:**

- Serialization is harder than it looks: tool results may contain non-JSON-serializable objects
- The checkpoint must include enough state to fully resume — model context, tool call history, iteration count, anything pending
- The first time you resume after a crash, you find out what you forgot to checkpoint
- There's a trade-off between checkpoint frequency (safer) and write overhead (slower)

**Pitfalls to encounter:**

- Forgetting to checkpoint a state field; on resume the agent is in an inconsistent state
- Tool calls in flight at crash time; on resume, do you re-execute or assume completed?
- Conversation history grows large; checkpoints become huge

**Stretch exercise:** Implement a "branch from a previous checkpoint" feature. The user can say "go back to where we were 5 iterations ago and try a different approach." This is essentially Git for agent state.

---

### Module 11 — Observability: Traces and Telemetry

**Status:** ⏳ pending.

**Learning goal:** Build observability from scratch. See what you can and can't see.

**Use case:** Add observability to your research project agent (Module 10). After every run, you should be able to investigate what the agent did: every Think, every tool call, every state transition.

**What to write:**

- A `Trace` data structure that captures: per-Think (prompt, response, tokens, latency, cost), per-tool-call (name, args, result, duration), per-iteration (what happened in this iteration)
- Logging hooks throughout your agent loop that emit trace events
- A trace store (SQLite or just JSONL files) that persists traces
- A simple CLI `view_trace --session-id X` that pretty-prints the trace for inspection

**What it should teach you:**

- The trace is the only thing that lets you investigate what an agent actually did
- Without trace, debugging is essentially impossible — you have outputs but no path to them
- The trace must include enough context to reconstruct the decision; logging "tool called" without the args is useless
- Token counts and costs are necessary for any production reasoning about agent expense

**Pitfalls to encounter:**

- Logging too little; investigation reveals you don't have the data you need
- Logging too much; the trace is overwhelming and hard to navigate
- Logging in a format that can't be queried; you have data but can't analyze it

**Stretch exercise:** Build a trace visualization. A simple HTML page that, given a trace, renders it as a tree (iterations as nodes, tool calls as children, model calls as content). Notice how much easier debugging becomes when you can see the structure.

---

## Movement Three — Frameworks and Production Concerns

### Module 12 — LangGraph: First Encounter

**Status:** ⏳ pending.

**Learning goal:** Reimplement Module 5 (the naive agent class) in LangGraph. Compare what you wrote to what they wrote.

**Use case:** Same homework helper from Module 4, but now built with LangGraph.

**What to write:**

- A LangGraph `StateGraph` definition
- Define your state (a TypedDict or Pydantic model with messages, current task, etc.)
- Define nodes for each phase (a `think` node that calls the model, a `tool_dispatch` node that runs tool calls)
- Define edges (after `think`, conditionally route to `tool_dispatch` or to END)
- Compile and run the graph

**What it should teach you:**

- LangGraph is essentially a state machine you describe declaratively
- The state object flows through nodes; each node can modify it
- Conditional edges are where control flow lives — they read the state to decide where to go
- Most of what you wrote by hand in Module 5 is now framework-provided

**Pitfalls to encounter:**

- Misunderstanding what state is; treating it as a global variable instead of a per-invocation context
- Forgetting that nodes return state *updates*, not the full state
- Conditional edges that don't handle all cases; the graph gets stuck

**Stretch exercise:** Compare your hand-written `Agent` class side-by-side with the LangGraph version. Make a list of: what's better in LangGraph, what's worse, what's just different. This is your framework intuition.

---

### Module 13 — LangGraph: Multi-Agent and Persistence

**Status:** ⏳ pending.

**Learning goal:** Reimplement Modules 8 and 10 in LangGraph using its native primitives.

**Use cases:**

**Multi-agent in LangGraph:** Reimplement the supervisor pattern from Module 8 using LangGraph subgraphs. Each sub-agent is its own compiled graph; the supervisor is a parent graph whose nodes invoke the subgraphs.

**Persistence in LangGraph:** Reimplement Module 10 using LangGraph's checkpointer. Configure a SQLite checkpointer; observe automatic state persistence at every node boundary.

**What to write:**

- A LangGraph supervisor with three subgraph sub-agents
- A persistent version that resumes after process restart
- Compare implementation complexity to your hand-rolled versions

**What it should teach you:**

- Subgraphs are LangGraph's natural unit of agent composition
- The checkpointer abstraction handles persistence with very little code
- Multi-agent topologies in LangGraph are fundamentally state-machine compositions
- The framework removes ~60% of the boilerplate but you still need to design the state correctly

**Pitfalls to encounter:**

- Subgraph state and parent state get conflated
- Checkpointer overhead is real; persisting at every node may be more granular than you need
- The framework's abstractions sometimes hide what you need to debug

**Stretch exercise:** Try to implement the swarm pattern (Module 9) in LangGraph. Notice that LangGraph is much better suited to supervisor than to swarm. The framework has opinions; some patterns fit, some don't.

---

### Module 14 — Designed Pauses: Interrupt and Resume

**Status:** ⏳ pending.

**Learning goal:** Implement human-in-the-loop gates as designed pauses, both by hand and in LangGraph.

**Use case:** A "publish a tweet" agent. The user says "draft a tweet about my latest project." The agent drafts. Before publishing (mocked — just printing), the agent pauses and asks the human "approve, edit, or discard?" The human responds. The agent acts accordingly.

**What to write:**

- **Hand-rolled version:** modify your `Agent` class so that certain "tools" cause the loop to suspend. The state is checkpointed. A separate API call resumes with the human's decision.
- **LangGraph version:** use LangGraph's `interrupt` primitive at the publish node. The graph naturally suspends. A `resume` call continues with new input.

**What it should teach you:**

- Designed pauses are different from failures; the agent intends to wait
- The pause is a state, not an event — checkpointing must capture it
- The human's response is just another input to the agent loop, not a special signal
- Without the pause primitive, you'd be polling or hacking — the framework support matters here

**Pitfalls to encounter:**

- Forgetting that resume needs to re-establish full context (the model needs to "remember" what was waiting on)
- Pause without timeout; the agent waits forever
- The human modifies the action in a way the agent didn't expect

**Stretch exercise:** Add multiple pause types: approval (human says yes/no), modification (human edits the proposed action), escalation (human reassigns to a different agent). Each is a different shape of human-in-loop, and the resume contract differs.

---

### Module 15 — Observability with LangSmith / Langfuse

**Status:** ⏳ pending.

**Learning goal:** See what professional observability looks like, compared to what you built in Module 11.

**Use case:** Connect your most complex agent (the multi-agent research system from Module 8 or the LangGraph version from Module 13) to LangSmith (managed) or Langfuse (self-hosted).

**What to write:**

- LangSmith integration: set environment variables, run the agent, observe traces appearing in the LangSmith UI
- Langfuse integration alternative: run a local Langfuse instance via Docker, instrument your agent, observe traces
- Compare to your hand-rolled trace from Module 11

**What it should teach you:**

- Professional observability gives you a UI for trace navigation that you would not have built yourself
- Trace correlation across sessions, across users, across agents is harder than your single-trace tool
- The cost and latency aggregation is built-in; you don't have to compute it
- You can still hand-roll observability for special cases the framework doesn't capture

**Pitfalls to encounter:**

- Sensitive data in traces (the trace captures everything, including user inputs that might be private)
- Performance overhead of trace emission
- Lock-in to the observability vendor's data format

**Stretch exercise:** Build a custom evaluator that runs against your traces. Define a quality metric (e.g., "did the agent eventually answer the question correctly"). Score recent traces. This is the seed of an evaluation pipeline.

---

## The Eight Deeper Territories

After completing the 15 modules, you've built the muscle. Now go deep into specific territories that the modules touched but did not fully exercise. Each is a multi-weekend project on its own.

### Deeper Territory 1 — Prompt Construction as Architectural Work

**Status:** ⏳ pending.

The most under-documented art in agentic systems. Build a personal "prompt lab" where you maintain a library of system prompts, few-shot examples, and chain-of-thought patterns. For each, document the use case, the failure modes, the alternatives you tried.

Sample uses cases to explore:

- A summarization prompt that varies summary length based on input length without being told to
- A classification prompt that produces calibrated confidence scores
- A reasoning prompt that exposes its chain of thought in a structured way

What you're building: intuition for the difference between a brittle prompt and a robust one.

### Deeper Territory 2 — State Design for Multi-Agent Systems

**Status:** ⏳ pending.

Take a multi-agent system you've built and redesign its state from first principles. What does each sub-agent need to see? What does the parent need to aggregate? What flows in only one direction; what flows both ways?

Sample explorations:

- A supervisor with 5 sub-agents where some sub-agents share state and some don't
- A pipeline where each stage's state is the union of upstream states (provenance tracking)
- A debate where Pro and Con cannot see each other's state but the Judge sees both

What you're building: intuition for state design as architectural work, distinct from code-writing.

### Deeper Territory 3 — Inter-Agent Communication Protocols

**Status:** ⏳ pending.

Design a protocol for agents to communicate that goes beyond "function call." What does an agent need to convey when it asks another agent for help? What does it need to convey when it returns a result? When does it need to escalate vs. answer vs. defer?

Sample uses cases:

- An agent that asks for help and includes "what I tried, why it didn't work" so the helper doesn't redo work
- A return value that includes confidence ("I'm fairly sure about this, but check the citations")
- An escalation that includes "here's what I see; I need a more capable agent to handle"

What you're building: intuition for the difference between API design and protocol design.

### Deeper Territory 4 — Tool Design Discipline

**Status:** ⏳ pending.

Take a tool you built and rebuild it three ways: too simple, just right, too complex. Compare how the model uses each version.

Sample explorations:

- A web-search tool with three versions: just a query string in, just URLs out (too simple); query + filters + result schema (just right); a hundred parameters (too complex)
- An email tool that succeeds without telling the model what was sent, vs. one that returns the full sent email
- A database query tool with auto-formatting vs. raw results

What you're building: intuition for what the model needs from a tool to use it well.

### Deeper Territory 5 — Model Routing Logic

**Status:** ⏳ pending. *(Forward-designed in [`limbic-design.md`](limbic-design.md) and [`limbic-image-video-generative.md`](limbic-image-video-generative.md) under the LIMBIC v0 / L3.1 framing.)*

Build a "model router" that, given a task, decides which model to use. Implement at least three routing strategies: cost-aware (cheapest model that can handle this), capability-aware (frontier model for hard tasks, fast model for easy ones), latency-aware (fastest model that meets quality bar).

Sample explorations:

- Classify task complexity using a cheap model, then route the actual task to an appropriate-tier model
- Route tasks based on context length (some models handle long context better)
- Implement a fallback chain (try fast model first; if confidence is low, escalate to frontier)

What you're building: intuition for model selection as a first-class engineering concern, not a config setting.

### Deeper Territory 6 — Evaluation Frameworks

**Status:** ⏳ pending.

Build an eval framework from scratch for one of your agents. Define test cases. Define quality metrics. Run agents under multiple model configurations. Compare. Iterate.

Sample explorations:

- A regression test suite that catches when the agent's quality degrades after a model update
- An LLM-as-judge evaluator that scores agent outputs against criteria you define
- A human-in-the-loop annotation tool for evaluating outputs that LLM judges struggle with

What you're building: intuition for evaluation as continuous engineering, not a one-time benchmark.

### Deeper Territory 7 — Failure Modes and Recovery

**Status:** ⏳ pending.

Take an agent and deliberately induce failures. Tool failures. Model timeouts. Malformed responses. Authentication errors. For each, design recovery.

Sample explorations:

- A retry strategy that distinguishes transient errors from permanent ones
- A degradation strategy that, when frontier model is unavailable, falls back gracefully
- A loop-detection strategy that catches the agent stuck in a tool-call cycle

What you're building: intuition for the operational reality that real agents face.

### Deeper Territory 8 — Cost Engineering

**Status:** ⏳ pending.

Take a multi-agent system and optimize its cost without degrading quality. Measure baseline. Identify cost concentrations. Apply techniques: prompt compression, response caching, model tier downshift, parallel tool calls instead of serial.

Sample explorations:

- Caching identical sub-agent invocations within a session
- Compressing conversation history above a threshold via summarization
- Using a small model for tool selection but a frontier model for synthesis

What you're building: intuition for cost as architectural concern, not finance concern.

---

## Project-specific notes

A handful of design decisions have been locked or partially-locked along the way. They modify the curriculum's defaults in specific places:

- **The seam-parameter axis.** Temperature, seed, voice, audio_format, CFG/guidance, reasoning_effort, max_tokens, streaming, batch, prompt caching, logprobs, embeddings — none of these earn new curriculum modules. They are dial settings on every existing measurement act and land in the dispatcher (Phase 2) after per-module passthrough (Phase 1). See [`seam-parameters.md`](seam-parameters.md) for the full lock.
- **Tool-call output handling.** Excluded from seam parameters; lives in Module 4 (introduction) and Deeper Territory 4 (design discipline).
- **LIMBIC v0 (L3.1).** Forward-designed in [`limbic-design.md`](limbic-design.md). It is the eventual home for Deeper Territory 5 (Model Routing Logic) and overlaps with Movement Three's framework story. When the curriculum reaches that point, LIMBIC v0 becomes the integration target.
- **Multi-asset input as Module 1m.** When a future need arises for `input_modality: set[str]` (image + audio together, etc.), it lives at `level_1_modules/module_01m_*` and changes the dispatcher's cell lookup from 4×4 to set-cover. Parked deliberately; not blocking Module 2.

---

## How to Know You've Built the Muscle

You've built the muscle when:

- You can read a paper or framework documentation about agentic systems and immediately recognize which patterns they're using and why
- When something doesn't work in an agent you've built, your first instinct is correct more often than not
- You can predict, before running, where an agent design will break — context window overflow, tool selection ambiguity, state contamination, etc.
- You can argue with a framework's choices because you've made other choices yourself and can compare
- You can teach this to someone else without referring back to documentation

The muscle is not "I memorized LangGraph." The muscle is "I understand what every framework is solving for and where each one trades off."

When you reach this level, framework boundaries dissolve. LangGraph, Strands, AutoGen, custom SDK harnesses — they're all different elaborations of the same kernel you built in Module 3. You can use any of them; you can build your own when none fit.

---

## Resources Beyond This Curriculum

Once you've built the muscle, the literature opens up:

**Papers worth reading (search current titles):**

- Original ReAct paper (the agent loop pattern)
- Tree of Thoughts and other reasoning patterns
- Reflection / self-critique patterns
- Recent multi-agent papers (debate, swarm, role-play)
- Papers on tool selection and tool use evaluation
- Papers on long-context handling and context compression

**Code repositories worth reading:**

- Anthropic's published example agents
- LangGraph's example notebooks
- Building blocks of major agent products (when source is available)

**Engineering blogs worth following:**

- Anthropic's engineering posts
- Hamel Husain's work on evals
- Eugene Yan's posts on production agentic systems
- LangChain / LangGraph blogs for framework-specific deep dives

**Communities:**

- Anthropic Discord
- LangChain Discord
- The various AI engineering Substacks and YouTube channels

By the time you can read this material critically — agreeing with parts, disagreeing with parts, identifying claims that aren't justified — you have arrived. The muscle holds.

---

## Closing

This curriculum is built on a single belief: the way to understand agentic systems is to write them, deliberately, from the kernel outward, before relying on any framework. Frameworks become useful when you understand what they're abstracting; until then, they're cargo cult.

The path from Module 1's bare API call to Module 15's professional observability covers everything that distinguishes a senior agentic engineer from someone who has copied a tutorial. The eight deeper territories take you from competent to deep. The journey is bounded; the muscle is durable.

Time invested: somewhere between 60 and 200 hours over a few months, depending on how deep you go in each module. That's a few hours a weekend, a few months. Less than learning a new programming language properly.

Outcome: you can build, debug, evaluate, and reason about agentic systems with the intuition that comes from having built each pattern yourself, in code, on toy use cases that exercised the actual properties.

The harness layer is where the new world of model-delegated control flow meets the old world of deterministic engineering. This curriculum is the path through it.

Build. Break. Rebuild. The muscle accumulates.
