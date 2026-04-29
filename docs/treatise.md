# Harness Engineering — A Conceptual Treatise

**Subject:** A conceptual map of the harness layer in agentic systems — what it is, how it works, and the vocabulary needed to think about it precisely. Written for someone with no prior exposure to LangChain, LangGraph, or the broader agent framework ecosystem, at the depth an AI lab engineer would expect.

**Approach:** Neural engineering metaphor used throughout — the model as the brain, the harness as the nervous system that connects cognition to motor function (tools, state, memory, surfaces). Not for learning sense, but for understanding how energy, discretion, state, continuity, observance flow between the model and the world it acts on.

**Structure:** Eight parts. The first seven establish the conceptual territory progressively. The eighth clarifies the Lang\* ecosystem so the names stop being confusing.

**Companion docs:**

- [`curriculum.md`](curriculum.md) — the 15-module path that exercises each of the eight territories in code.
- [`measurement-seam.md`](measurement-seam.md) — the philosophical lens (frozen-weight inference as a single measurement act). The treatise is the *what*; the seam doc is the *why this framing*.
- [`seam-parameters.md`](seam-parameters.md) — locked architectural decision on how seam parameters (temperature, seed, voice, streaming, caching) live in the dispatcher rather than as new curriculum modules.
- [`limbic-design.md`](limbic-design.md), [`limbic-image-video-generative.md`](limbic-image-video-generative.md) — forward design for the multi-axis router (Module L3.1) and the modality-matrix work that anchors our extended Module 1.

---

## Topical Map

```
                    ┌─────────────────────────────────────────┐
                    │  PART I  —  WHAT CHANGED ARCHITECTURALLY │
                    │  (Pre-GPT vs Post-GPT engineering)       │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART II  —  THE METABOLIC ANATOMY      │
                    │  (How a single agent thinks and acts)   │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART III  —  STATE AS NERVOUS SYSTEM    │
                    │  (How memory, context, history flow)    │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART IV  —  TOOLS AS MOTOR ORGANS       │
                    │  (How discretion meets the world)       │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART V  —  MULTI-AGENT NEURAL TOPOLOGIES│
                    │  (Supervisor, swarm, debate patterns)   │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART VI  —  CONTINUITY AND HICCUP      │
                    │  (Persistence, interrupts, recovery)    │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART VII —  OBSERVANCE                 │
                    │  (What we see, what we miss)            │
                    └─────────────────────────────────────────┘
                                      ↓
                    ┌─────────────────────────────────────────┐
                    │  PART VIII — THE LANG* FAMILY MAP        │
                    │  (Chain, Graph, Smith, SDK clarified)    │
                    └─────────────────────────────────────────┘
```

| Part | Curriculum exercise | Status |
|---|---|---|
| I — What changed architecturally | Conceptual; threaded through every module | n/a |
| II — Metabolic anatomy (Read-Think-Act) | Module 3 (RTA loop by hand), Module 5 (naive agent class) | pending |
| III — State as nervous system (4 layers) | Module 2 (conversation loop), Module 7 (memory layers) | pending |
| IV — Tools as motor organs | Module 4 (native tool calling), Deeper Territory 4 (tool design discipline) | pending |
| V — Multi-agent topologies | Module 8 (supervisor), Module 9 (pipeline / swarm / debate) | pending |
| VI — Continuity and hiccup | Module 10 (persistence), Module 14 (designed pauses) | pending |
| VII — Observance | Module 11 (custom traces), Module 15 (LangSmith / Langfuse) | pending |
| VIII — Lang\* family | Module 12 (LangGraph first encounter), Module 13 (LangGraph multi-agent + persistence) | pending |

The single piece exercised so far is the seam itself — the boundary between what the model decides and what the harness builds around that decision. That is Module 1's territory and the foundation every later module rests on. See [`measurement-seam.md`](measurement-seam.md) for the framing and [`curriculum.md`](curriculum.md) for the path forward.

---

## Part I — What Changed Architecturally

The pre-GPT era and the post-GPT era differ in one specific architectural fact, and almost everything else flows from it.

**Pre-GPT software:** the *control flow* was authored entirely by humans. Programs executed deterministic logic — `if`, `for`, `while`, function calls — written in code by engineers. Data flowed through these structures. Every branch, every loop iteration, every function invocation was determined by code humans had specified. There was no part of the program where the program itself decided what to do next based on its own reasoning. State machines were designed; transitions were enumerated.

**Post-GPT software:** part of the control flow is *delegated to the model*. The program reaches a decision point and asks the model "given everything you know, what should we do next?" The model responds with a directive — "call this tool with these parameters," "produce this final answer," "ask the user this clarifying question." The program then routes accordingly. This delegation is the architectural mutation that changed everything.

This is what makes harness engineering genuinely different from backend engineering. In backend, you author the logic. In harness, you author the *space within which the model authors the logic*. You design the range of choices the model can make, the consequences of each choice, the state the model has access to, and the recovery if the model's choices fail. You are building a substrate for non-deterministic decision-making, not a deterministic execution path.

This also clarifies why "model is commodity, agent is engineering" is correct. The model is the cognitive resource; the harness is the architecture that channels its cognition into useful work. Two harnesses around the same model produce dramatically different systems because the *space within which the model decides* is different.

Concretely, the new architectural primitives that didn't exist before:

- **Reasoning as a step** — a program operation whose output is unstructured text or structured-but-flexible JSON, not deterministic data. The output is meaningful only because a model produced it.
- **Tool selection as inference** — the program does not call function X because the code says so; the model selected function X because it judged that appropriate.
- **Context window as substrate** — a finite, position-sensitive working memory that bounds what the model knows in this moment.
- **Sampling and stopping as hyperparameters** — temperature, top-p, max tokens; these are knobs that affect program behavior without being conventional configuration.
- **Failure modes that are silent** — the model produces fluent output that is wrong; conventional error handling does not catch this.

Every concept in the rest of this document is a consequence of these primitives.

> **In our codebase:** Module 1's curriculum-extension (1b–1l) is the working-out of *one* of these primitives — the seam itself, the moment where input meets a frozen-weight model and a resolved output crosses back. Sampling/stopping (the fourth bullet) is an axis we have explicitly parked as dispatcher growth in [`seam-parameters.md`](seam-parameters.md) — temperature, seed, voice, streaming, caching are not new lessons but knobs at every existing measurement act.

---

## Part II — The Metabolic Anatomy of a Single Agent

Forget any specific framework for a moment. Here is what an agent *is*, conceptually.

### The agent loop, distilled

An agent is a loop with three phases:

```
   ┌──────────┐
   │   read   │  ← gather inputs: user query, retrieved context, prior state
   └────┬─────┘
        ↓
   ┌──────────┐
   │  think   │  ← model reasons: produces structured output (text + tool calls)
   └────┬─────┘
        ↓
   ┌──────────┐
   │   act    │  ← either: invoke a tool, return final answer, or continue
   └────┬─────┘
        ↓
   (if tool was invoked, results feed back into next iteration)
```

This is the metabolic cycle. It executes once per "turn" of the agent's reasoning. A single user query may result in 1–50+ cycles before the agent returns a final answer.

### The cycle in more detail

**Read.** The harness assembles a *prompt* — everything the model will see in this iteration. This includes:

- System instructions (who the agent is, how it should behave)
- Conversation history (prior user messages, prior agent responses, prior tool calls and results)
- Retrieved context (documents, data, memory pulled in for this turn)
- The current user query or trigger
- Tool definitions (what tools are available, their schemas)

This assembly is *prompt construction*, and it is the most under-discussed engineering art in agentic systems. Most agent quality lives here. The same model with a good prompt and the same model with a bad prompt produces dramatically different agents.

**Think.** The harness sends the assembled prompt to the model and receives a response. The response can take three forms:

- *Final answer* — text intended for the user; the agent loop terminates this turn
- *Tool call* — structured directive to invoke a specific tool with specific arguments
- *Reasoning step* — text expressing intermediate thinking, often with a tool call following

Modern models support *parallel tool calls* (multiple tools invoked in one inference) and *thinking blocks* (reasoning text the model produces before its actionable output). Both are harness-level concerns to handle.

**Act.** The harness inspects the model's response and dispatches:

- If final answer → return to caller, end the loop
- If tool call → execute the tool, capture the result, append to context, loop back to Read
- If error → handle (retry, escalate, fail) per harness policy

The cycle continues until a final answer is produced, a maximum iteration count is reached, an error condition halts execution, or an external signal interrupts.

### Where energy and discretion concentrate

Where does *neural energy* flow, where does *discretion* live?

**Energy concentration:** the Think phase is by far the most expensive in compute, latency, and cost. A single frontier-model call might take 1–30 seconds and cost cents to dollars. Read and Act are cheap (milliseconds, microcents). Most engineering optimization lives in reducing the number and size of Think operations.

**Discretion concentration:** discretion (the model's freedom to choose) is highest in the Think phase, but the *boundaries of that discretion* are set in the Read phase. What tools are available, what state is visible, what instructions are given — these constrain what the model can decide. A well-engineered agent gives the model *exactly the right amount of discretion* — enough to handle variance in inputs intelligently, not so much that it makes choices the harness can't recover from.

**Where humans most often get it wrong:** they over-constrain the Think phase (too many rigid rules, too detailed instructions) or under-constrain it (too vague, too few tools, no clear stopping condition). Either failure produces brittle agents.

### The single agent's anatomy as code (conceptually)

```
def run_agent(user_input):
    state = initial_state(user_input)
    for iteration in range(max_iterations):
        prompt = build_prompt(state)              # READ
        response = model.complete(prompt)         # THINK
        if response.is_final_answer:              # ACT
            return response.text
        elif response.has_tool_call:
            tool_result = execute_tool(response.tool, response.args)
            state = update_state(state, response, tool_result)
        else:
            handle_unexpected(response)
    return iteration_limit_reached()
```

This is the entire agent in 12 lines. Every framework — LangGraph, Strands, AutoGen, custom SDK harnesses — is an elaboration of this kernel. The complexity comes from how each phase is structured, how state is managed, how multiple agents compose, and how the loop's invariants are preserved.

> **In our codebase:** Module 1's bare-call sub-modules exercise *one Think* per invocation, no loop. The bilateral pattern (1b–1l) splits the Think into two stages (parser → composer) but is still one cycle of the metabolic loop, not the loop itself. The full Read-Think-Act loop is Module 3 — pending. Module 5 wraps it into a reusable `Agent` class.

---

## Part III — State as Nervous System

If the cycle is the agent's metabolism, *state* is its nervous system. State is what makes the agent more than a stateless function. It's how the agent knows what happened earlier in this conversation, in this session, across sessions.

### The four temporal layers of state

State exists across four distinct time horizons, and conflating them is one of the most common architectural failures:

**Working memory (within one model call).** The context window — what the model literally sees in this single inference. Capped by model context length. Ephemeral; gone after the inference completes. The harness reconstructs it for every Think phase.

**Episodic memory (within one agent task).** The accumulated conversation through this loop's iterations — user query, the back-and-forth with tools, the agent's intermediate reasoning. Lives in harness-managed structures during the task. Often, but not always, persisted to a session store at task end.

**Session memory (within one user conversation).** The full conversation history with this user across multiple agent tasks. The user starts a session, has multiple exchanges, the session ends. Conversation memory persists through this. Stored in a database, key-value store, or session store — managed by the harness.

**Long-term memory (across sessions, across users).** What the agent "knows" persistently — facts about the user (preferences, prior interactions), facts about the world (enterprise data via retrieval), patterns the agent has learned (in production systems with feedback loops). Stored in vector databases, knowledge graphs, structured stores. Accessed via retrieval at the start of relevant tasks.

The harness orchestrates flow between these four layers. Working memory is reconstructed each Think from session memory + retrieved long-term memory. At task end, episodic memory may be summarized into session memory. Periodically, session memory may be distilled into long-term memory.

### The context window as a scarce, position-sensitive substrate

Working memory deserves special attention because it is the single most operationally consequential state primitive in agentic systems.

The context window is:

**Finite.** Models have a maximum token count they can attend to. Once you exceed it, you must drop or summarize content. For long agentic tasks (50+ tool calls, large retrieved documents), context management becomes a significant engineering problem.

**Position-sensitive.** Models attend differently to content at the beginning, middle, and end of the context. The well-known "lost in the middle" phenomenon: information placed in the middle of long contexts is more often missed than information at the start or end. Prompt construction must consider position.

**Implicitly typed by structure.** Models behave differently when content is in system messages vs user messages vs assistant messages vs tool results. The roles carry semantic weight. Information placed in the wrong role can be ignored or misinterpreted.

**Costly.** Every token in context is paid for at every Think. Long contexts cost meaningfully on every inference. Context length and inference frequency are major cost drivers.

The harness's job in working memory is *prompt construction* — choosing what goes in, where, and how it's structured. This is where most quality optimization happens. Frameworks differ in how much help they provide here.

### State as the harness's primary engineering concern

If you remember one thing from this section: **state management is the harness's primary engineering concern**, more than tool calls, more than model selection, more than orchestration. Every other concern derives from how state is managed.

Bad state management produces:

- Agents that lose track of what they're doing mid-task
- Agents that "forget" earlier conversation parts
- Agents that hallucinate facts that contradict their own earlier outputs
- Agents that cannot resume after interruption
- Multi-agent systems that diverge because each agent has different views of state

Good state management produces:

- Agents that maintain coherence across long tasks
- Resumable, persistent sessions
- Multi-agent coordination that converges
- Auditable reasoning traces
- Context-window efficiency at scale

> **In our codebase:** Module 1's modules are stateless by construction — every CLI invocation is its own world. Working memory is exercised implicitly (the prompt assembled per call), but episodic / session / long-term layers don't yet exist. Module 2 (conversation loop) introduces episodic memory; Module 7 (memory layers) makes all four layers explicit.

---

## Part IV — Tools as Motor Organs

Tools are how an agent acts on the world. The model's discretion ends at the tool call; the tool's execution happens in deterministic software. The seam between "model decides" and "code executes" is the most consequential boundary in agentic engineering.

### Anatomy of a tool

A tool is a function exposed to the model with:

**A name** — typically descriptive: `query_database`, `send_email`, `read_calendar`.

**A description** — natural language explanation of what the tool does, when to use it, what it returns. The model reads this when deciding whether to invoke. Description quality is critical; a poorly described tool will be misused or ignored.

**A schema** — structured definition of inputs (typically JSON Schema). Defines parameter types, required vs optional, enums, constraints. The model produces a JSON object matching this schema when it calls the tool.

**An implementation** — the actual code that runs when the tool is invoked. Receives the model's arguments (parsed and validated against the schema), executes the action, returns a result.

**A return contract** — what the tool returns to the model after execution. Usually structured text: success/failure, the result data, any errors. The return value gets appended to the agent's context for the next Think phase.

### Tool calls as discretion handoff

Look closely at what happens at a tool call:

```
Model: "I need to call get_calendar_events with start=today, end=today"
       → produces structured tool_call object
       → control returns to harness

Harness: validates the tool_call against schema
       → invokes the tool's implementation
       → captures the result
       → appends to context

Model: receives the tool result in next Think
       → reasons about it
       → decides next step
```

This is *discretion handoff and return*. The model decides what tool to call (discretion). The harness validates and dispatches (deterministic). The tool executes (deterministic). The result returns. The model now decides what to do with it (discretion again).

The harness's job at this seam is critical:

- **Schema validation** — ensure the model's tool call is structurally valid before execution
- **Authorization check** — verify the agent has the authority to invoke this tool with these arguments
- **Execution dispatch** — invoke the actual tool implementation with proper context
- **Result formatting** — format the tool's output in a way the model can parse usefully
- **Error handling** — if the tool fails, decide whether to retry, surface to user, or feed the error back for the model to handle

### Tool call patterns and their engineering

**Sequential tool calls.** Most basic: model calls tool A, gets result, calls tool B. Each Think between tool calls. High latency (multiple round trips), but simple.

**Parallel tool calls.** Modern models can output multiple tool calls in a single Think. Harness dispatches them concurrently, gathers results, returns to model. Reduces latency for independent operations. Requires the harness to handle concurrent execution, partial failures, ordering of results.

**Conditional tool calls.** Model emits a tool call only if a condition holds. The model is doing the conditional logic in the Think; the harness just executes whatever comes out. This is where model discretion is most visible — the model is choosing which tools to call based on its reasoning.

**Recursive tool calls.** A tool's result triggers more tool calls, which trigger more, etc. The agent is doing real research/work. This is where context management matters most — recursive paths can produce extensive history that strains context windows.

### Tool design as harness engineering

Tool design is its own discipline. Good tools have:

**Single, clear purpose.** A tool that does one thing well is easier for the model to use correctly than a tool with many modes.

**Descriptive names and descriptions.** The model decides whether to use a tool largely from its description. Poor descriptions = misuse.

**Useful error messages.** When a tool fails, the error message should help the model understand what went wrong and what to do about it. Generic "tool failed" errors leave the model unable to recover.

**Output that supports next steps.** A tool that returns "success" is useless; a tool that returns the data the model needs to act next is invaluable.

**Idempotency where possible.** Tools that can be safely retried without side effects make recovery from transient failures clean.

### MCP — the standardization of tool exposure

MCP (Model Context Protocol) is the emerging standard for how tools are exposed to models. Before MCP, every framework had its own tool definition format, every model provider had its own, integration was N×M.

MCP defines a server-side protocol where any system can expose its tools (resources, prompts, tools proper) over a standard interface. Any harness can consume MCP servers. The result is that a system, exposed once as an MCP server, is callable from any harness that speaks MCP.

> **In our codebase:** No tools yet. Module 4 introduces native tool calling; Deeper Territory 4 makes tool design a study in itself. The dispatcher's `/api/dispatch` endpoint at [`level_2_strings/string_01_dispatch/server.py`](../level_2_strings/string_01_dispatch/server.py) is *consumable as a tool* by a future agent — but the system itself does not yet *call* tools.

---

## Part V — Multi-Agent Neural Topologies

Up until now, the discussion has been about a single agent. Multi-agent systems compose multiple agents, and the composition patterns matter.

### Why multiple agents at all?

Single agents work well up to a point. They strain when:

- The task requires expertise across multiple specialized domains (one agent can't be excellent at everything)
- The task is too long to fit in a single context window even with retrieval (decompose into sub-tasks)
- Parallel work is possible (run multiple agents simultaneously rather than serially)
- Different parts need different models (frontier for hard reasoning, fast for classification)
- Different parts need different identities or authority

### The four canonical topologies

**Supervisor pattern (hierarchical).** One agent is the supervisor; it delegates sub-tasks to specialist sub-agents. Sub-agents return results; supervisor synthesizes.

```
        [Main Agent]
        /     |     \
[Sub-A]  [Sub-B]  [Sub-C]
```

Properties: simple to reason about, single point of orchestration, single conversational coherence. Bottleneck: supervisor must understand all sub-agent capabilities to delegate well.

**Swarm pattern (peer-to-peer).** Multiple agents collaborate without explicit hierarchy. Each agent decides when to invoke others. State shared across the swarm. Used for emergent collaboration, often in research/exploration tasks.

```
[Agent-A] ←→ [Agent-B]
     ↕            ↕
[Agent-C] ←→ [Agent-D]
```

Properties: flexible, organic, scales to many agents. Risks: divergence (agents disagree without resolution), runaway loops (A calls B calls A), incoherent global behavior.

**Pipeline pattern (sequential).** Agents arranged in a fixed pipeline. Output of agent N is input to agent N+1. Used for staged processing where each stage adds something.

```
[Agent-A] → [Agent-B] → [Agent-C] → output
```

Properties: deterministic flow, clear stages, easy to optimize each stage independently. Limitations: rigid; no recovery if a middle stage struggles.

**Debate pattern (adversarial).** Two or more agents argue different positions; a judge agent (or human) selects the best. Used for tasks where verifying correctness is easier than producing correctness.

```
[Proposer] vs [Critic]
     ↘       ↙
     [Judge]
```

Properties: surfaces weaknesses in reasoning, useful for quality-critical decisions. Cost: 3x the inference cost of single-agent.

### The communication problem

Multi-agent systems have a communication problem that single agents don't: how do agents share state?

Three patterns:

**Shared state.** All agents read from and write to a common state store. Coherent global view; risk of state corruption from concurrent modification.

**Message passing.** Agents send structured messages to each other. Each agent has its own state; communication is explicit. Decoupled; risks losing global coherence.

**Hierarchical state.** Sub-agents have their own state; parent has aggregating state. Sub-agent state is encapsulated; parent state is the integration point.

> **In our codebase:** No multi-agent topologies yet. Modules 8 and 9 build them. The bilateral pattern in Module 1 (parser → composer) prefigures the *pipeline* topology at the smallest scale — two stages, each a single Think — but is structurally still one agent's two-stage measurement act, not two agents communicating.

---

## Part VI — Continuity and Hiccup

Real agents fail. Models time out. Tools error. Networks partition. Users walk away mid-task. The harness must handle all of this gracefully.

### Three classes of interruption

**Synchronous failures.** A tool returns an error, the model produces malformed output, a request times out. The harness catches and decides: retry, escalate, fail.

**Asynchronous interruptions.** The user closes their browser. The session times out. A scheduled job is killed mid-execution. The harness must persist enough state to resume (or know it can't).

**Designed pauses.** A human-in-the-loop gate triggers; the agent suspends pending review. A long-running task awaits an external trigger. Different from failures: the agent is *intentionally paused*, not broken.

### Persistence — the answer to "where is the state when the agent isn't running?"

If the agent is running in a stateless container and a task takes hours or days, the state cannot live in process memory. It must be persisted to durable storage.

This is **checkpoint-and-resume**:

- Periodically (or at every step boundary), the harness serializes the agent's state to durable storage
- A checkpoint identifier is associated with the session/task
- If the process crashes, restarts, scales down — the state is preserved
- When the task resumes (next user message, scheduled trigger, review completion), the harness loads the state and continues

### The three hiccup-handling questions

For any agentic system, ask:

1. **What happens if the model call fails?** Retry policy, fallback model, escalation, user notification — all decisions the harness must make.
2. **What happens if a tool call fails?** Error feedback to model (let the model handle), automatic retry, escalation, abort — different per tool and per failure type.
3. **What happens if the user disappears mid-task?** Save and resume vs abandon, timeout policies, notification on resumption — affects state design.

These questions are not framework questions; they are harness engineering decisions.

### Designed pause as a special primitive

A designed pause (such as a human review gate) is its own pattern:

- Agent reaches a gate; conditions met
- Harness suspends the agent's execution
- State checkpointed
- Review request published to a queue
- Agent waits (potentially for hours)
- Reviewer responds; decision delivered to harness
- Agent resumes from the gate node with the reviewer's decision in state

The agent cannot proceed past the gate by some loophole; the only path forward is through the resume call after a decision is delivered.

> **In our codebase:** The async-job state machine in [`module_01j_video_out/bilateral_j.py`](../level_1_modules/module_01j_video_out/bilateral_j.py) (and reused in 1l) is the *first* place we encode terminal states — `completed`, `failed`, `rejected` — distinct from exceptions. That's a continuity primitive at single-call scale; it is *not yet* checkpoint-and-resume across process death (that is Module 10) nor designed-pause / human-in-loop (that is Module 14). The dispatcher's `MemoryMax=2G` systemd cap is a hiccup boundary at the OS level — a runaway gets killed cgroup-wide and `Restart=on-failure` brings the service back. State is thrown away on that kill; durable resume is exactly what Module 10 will introduce.

---

## Part VII — Observance

In any system where part of the control flow is delegated to non-deterministic reasoning, you cannot operate it without observing it carefully. This is the role of telemetry and tracing in agentic systems.

### What you need to see

**Per-Think visibility:**

- The full prompt sent to the model (system, history, retrieved context, user message)
- The full model response (text, tool calls, thinking blocks)
- Token counts (input, output, total)
- Latency (request time)
- Cost (computed from tokens × model pricing)

**Per-loop visibility:**

- The sequence of Think operations in this task
- Tool calls made, with arguments and results
- State transitions
- Decisions and branches taken

**Per-session visibility:**

- All loops executed in this session
- All sub-agents invoked
- Aggregate cost, latency, and outcomes

**Cross-session visibility:**

- Patterns across sessions for a user
- Aggregate quality metrics
- Drift detection

### LLM observability vs traditional observability

Traditional observability tools capture latency, errors, and metrics — they answer "is the system up, fast, and healthy?" They are necessary but not sufficient for agents.

LLM observability tools additionally capture prompts, completions, tool calls, intermediate reasoning. They answer "what is the agent actually doing?" — which traditional tools cannot.

A serious agent system uses both, linked via correlation IDs so you can navigate from "system call X took 30 seconds" to "Think phase Y produced this output."

### What you cannot see

Important to acknowledge:

- **You cannot see why the model decided what it decided** in any deep sense. You see the input and output. The internal computation that produced the output is opaque.
- **You cannot prove the agent will behave consistently.** Test inputs may produce different outputs across runs (temperature effects, model updates, cumulative state differences).
- **You cannot detect semantic drift through pure observability.** The agent might be producing fluent, well-formed outputs that are wrong in ways the telemetry can't see.

This is why evaluation is a separate concern from observability. Observability shows you *what happened*; evaluation tells you *whether what happened was good*. Both are necessary.

> **In our codebase:** Each Module 1 sub-module emits a structured stderr trace (`=== / --- PARSER --- / --- COMPOSER --- / --- TOTAL ---`) that the dispatcher's regex extractor harvests into `parsed.total_cost_usd`, `parsed.stage_latencies_s`, `parsed.job_id`. This is per-Think visibility for a single bilateral call. Per-loop / per-session / cross-session visibility is Module 11; LangSmith / Langfuse is Module 15.

---

## Part VIII — The Lang* Family Map

Now let me clarify the Lang\* universe so the names stop being confusing.

### The four entities

**LangChain.** The original framework. Created in late 2022 to help developers compose LLMs with prompts, chains of operations, retrieval, and tools. It introduced the abstraction of "chains" — sequential pipelines of operations. LangChain is *broad and shallow*: many integrations, many primitives, but its abstractions struggle with complex multi-step agentic flows. It's still widely used, especially for retrieval-augmented patterns, but for agents most teams have moved on.

**LangGraph.** Created in 2023 by the LangChain team, specifically for stateful agentic flows. Where LangChain is a chain, LangGraph is a *graph* — nodes are steps, edges are transitions, and state flows through the graph. LangGraph's distinguishing feature is its state model: every node receives the current state, can modify it, and the modifications propagate. This makes complex agent flows tractable in a way LangChain wasn't. LangGraph is what most teams use today for serious multi-agent systems.

**LangSmith.** Created in 2023 as the observability and evaluation companion to LangChain/LangGraph. It's a managed service (with self-host options) that captures traces, runs evaluations, and provides debugging and monitoring for agentic systems. Functionally similar to other LLM observability tools.

**LangChain SDK.** The actual Python (and TypeScript) library. The SDK contains the abstractions you use in code: `Runnable`, `Graph`, `StateGraph`, `MessagesPlaceholder`, etc.

### How they relate

```
            [LangChain Ecosystem]
                    │
        ┌───────────┼───────────┐
        ↓           ↓           ↓
   [LangChain]  [LangGraph]  [LangSmith]
   (chains,     (stateful    (observability,
   pipelines,   agents,      evaluation,
   retrieval)   graphs)      debugging)
        │           │           │
        └─────┬─────┘           │
              ↓                 │
        [LangChain SDK]    [LangSmith UI]
        (Python / TS)      (web service)
```

LangChain and LangGraph are libraries you import. LangSmith is a service you connect to. The SDK is the code-level interface to all of them.

### LangGraph specifically — the abstraction stack

For someone working in LangGraph day-to-day, this is what they'll encounter:

**StateGraph** — the core primitive. Define the state (typically a TypedDict or Pydantic model), define nodes (functions that receive state and return state updates), define edges (transitions between nodes, which can be conditional). The graph compiles into a runnable object.

**Nodes** — Python functions, typically calling models or executing tools. Each node has access to the full state, can modify it, and can route to next nodes.

**Edges** — connections between nodes. Static edges (always go from A to B). Conditional edges (go from A to B or C based on a function evaluating state). The conditional edges are where model-driven control flow happens — the model's output is in state, and the conditional edge function reads it to route.

**Checkpointer** — the persistence abstraction. Configure a checkpointer (Postgres, Redis, in-memory) and the graph automatically persists state at each node boundary. Resumption is built-in.

**Interrupt and resume** — primitives for designed pauses. A node can interrupt; the graph suspends with state checkpointed; a separate API call resumes with new input.

**Subgraphs** — graphs nested inside other graphs. The supervisor pattern is naturally expressed as a parent graph whose nodes are themselves graphs (the sub-agents).

### Where LangGraph helps and where it doesn't

**LangGraph helps with:**

- State management (the killer feature)
- Persistence and resumption
- Multi-agent supervisor patterns
- Conditional flow based on model outputs
- Visualization of agent flows (the graphs are inspectable)
- Standard primitives that match common patterns

**LangGraph doesn't help with:**

- Prompt construction (you write your own prompts; LangGraph just hands them to the model)
- Model selection logic (you implement routing yourself)
- Tool design (you write your own tools)
- Semantic correctness (LangGraph is a software-engineering framework; semantic verification is your problem)

LangGraph is a software-engineering framework that helps with agentic state management. It is the scaffolding; the interesting engineering happens above and around it.

> **In our codebase:** Movement Three (Modules 12–15) is the encounter with LangGraph and LangSmith. Until then, every pattern is hand-rolled. The point of the curriculum is to know what LangGraph is abstracting *before* using it; the dispatcher in `level_2_strings/string_01_dispatch/` is hand-rolled scaffolding above the seam, exactly the kind of thing LangGraph would later replace.

---

## Closing

The harness layer is where conventional software engineering meets the new world of model-delegated control flow. Eight conceptual territories define it: what changed architecturally; the metabolic anatomy of the agent loop; state as nervous system; tools as motor organs; multi-agent topologies; continuity through interruption; observance and its limits; the Lang\* family that implements many of these patterns.

These territories do not become familiar through reading. They become familiar through practice — through writing the agent loop, managing its state, designing its tools, composing it with other agents, persisting it through interruption, observing what it does, and discovering what observation cannot show. The map exists to make the practice navigable.

What follows the map is the work. See [`curriculum.md`](curriculum.md) for the path.
