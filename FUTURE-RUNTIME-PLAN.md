# Future Runtime Plan

This document captures the current working direction for vCompany's multi-model,
multi-runtime architecture.

It is a future-development reference, not a final implementation spec.

## Goals

- Keep the vCompany UX simple:
  - owner sends one high-level request
  - Strategist turns it into an executable project
  - escalations to the owner are rare
- Support multiple providers:
  - Anthropic for premium strategy and premium coding
  - DeepSeek for default worker and reviewer lanes
  - Google Gemini for research and context compression
- Preserve the strengths of GSD:
  - staged workflow
  - planning artifacts
  - resumability
  - anti-context-rot behavior
- Keep vCompany as the orchestrator and source of truth.

## Final Stack Direction

### Models

- `claude-opus-4.6`
  - strategist
  - project kickoff
  - milestone planning
  - architecture resets
  - last model stop before human escalation
- `claude-sonnet-4.6`
  - premium coder
  - high-risk coding
  - cross-cutting refactors
  - hard debugging after cheap lanes fail
  - premium final review
- `deepseek-chat`
  - default PM/router lane
  - routine worker lane
  - routine coding
  - cheap bulk refactors and boilerplate
- `deepseek-reasoner`
  - reviewer/debugger lane
  - bug triage
  - flaky test diagnosis
  - review-first debugging
  - hidden-regression hunting
- `gemini-3.1-flash-lite-preview`
  - cheap research
  - backlog cleanup
  - long log summarization
  - context compression
- `gemini-3.1-pro-preview`
  - premium research
  - cross-document synthesis
  - ambiguity reduction
  - turning messy research into execution-ready briefs

### Default Ladders

- Research:
  - `gemini-3.1-flash-lite-preview -> gemini-3.1-pro-preview -> claude-opus-4.6 -> human`
- Coding:
  - `deepseek-chat -> deepseek-reasoner -> claude-sonnet-4.6 -> claude-opus-4.6 -> human`
- Review:
  - `deepseek-reasoner -> claude-sonnet-4.6 -> claude-opus-4.6 -> human`

## Why Not Use ClawCode As The Base

Even for personal use, where redistribution risk matters less, ClawCode is still
the wrong foundation for vCompany.

### 1. Wrong abstraction level

vCompany is not trying to become "a Claude Code clone". It needs:

- multi-provider routing
- role-based model selection
- cost governance
- provider-specific fallbacks
- a durable project-memory layer
- runtime-independent workflow control

ClawCode is oriented around reproducing a Claude-Code-like runtime, which is too
low-level and too provider-specific for the center of this architecture.

### 2. It does not remove the hard work

Even if ClawCode gives a Claude-like shell/runtime experience, vCompany would
still need to build:

- provider router
- budget governor
- session store
- transcript compaction
- project memory model
- GSD compatibility layer
- cross-runtime tool bus
- escalation engine

That means ClawCode would not actually eliminate the main architectural work.

### 3. Maintenance economics are bad

If vCompany forks or internalizes a Claude-Code-like rewrite, it becomes
responsible for keeping that runtime current while also building the actual
multi-agent system on top of it.

That creates two products to maintain:

- a local agent runtime
- vCompany itself

That is not a good trade when official Claude tooling already exists.

### 4. Official Claude tooling is now available

Anthropic now exposes Claude Code programmatically through the official Agent
SDK. That gives access to the real Claude-side agent loop, sessions, hooks,
plugins, MCP, and file-checkpointing without needing to build or depend on a
reimplementation.

So for Claude lanes, the better path is:

- use the official Anthropic Agent SDK
- let vCompany wrap it behind a runtime adapter

### 5. ClawCode is still the wrong center even if parts are useful

It is still reasonable to inspect ClawCode for ideas or isolated techniques, but
not to make it the architectural core. At most:

- borrow patterns
- compare UX
- inspect how it models tool calls or context

Do not make it the backbone of the multi-provider harness.

### 6. Provenance noise is unnecessary even if personal

For a private project, license exposure is less important. But provenance and
clean-room questions still make ClawCode a noisy dependency. Since there is a
better official Anthropic integration path, vCompany does not need that risk.

## What To Use Instead

### Claude lanes

Use the official Anthropic Agent SDK as the Claude runtime.

This is the right fit for:

- `claude-opus-4.6`
- `claude-sonnet-4.6`
- premium strategy
- premium coding
- premium review

### DeepSeek and Gemini lanes

Use a generic multi-provider runtime behind an adapter. The best candidate
discussed so far is OpenCode.

This is the right fit for:

- `deepseek-chat`
- `deepseek-reasoner`
- `gemini-3.1-flash-lite-preview`
- `gemini-3.1-pro-preview`

### Everything-Claude-Code

Treat this as an ideas/plugin/content source, not the runtime foundation.

More specifically, `everything-claude-code` is best understood as a harness
optimization and prompt-pack system:

- skills
- rules
- agents
- memory helpers
- security patterns
- research-first workflows

It is useful across multiple tools because it is largely content and workflow
structure, not the execution engine itself.

Use it for:

- reusable skills
- rules and conventions
- research/verification patterns
- prompt scaffolding
- cross-tool `AGENTS.md` style guidance

Do not use it as:

- the runtime core
- the session engine
- the tool execution layer
- the provider router

## Recommended Runtime Architecture

vCompany should sit above multiple runtimes.

### Core rule

vCompany owns:

- routing
- project memory
- workflow state
- budgets
- escalation
- cross-agent coordination

Runtimes only own:

- agent loop execution
- tool invocation
- provider-specific sessions
- local interaction semantics

### Main interfaces

Introduce a `RuntimePort` abstraction with two concrete implementations:

- `ClaudeRuntime`
  - Anthropic Agent SDK underneath
- `GenericRuntime`
  - OpenCode underneath for DeepSeek and Gemini lanes

Each runtime should support:

- `start_session()`
- `send_message()`
- `run_task()`
- `resume_session()`
- `compact_context()`
- `list_tools()`
- `register_mcp_servers()`
- `checkpoint()`

### Supporting subsystems

- `LLMRouter`
  - selects provider/model/runtime based on situation and escalation ladder
- `BudgetGovernor`
  - tracks spend by provider, role, and project
  - applies downgrade rules
- `SessionStore`
  - persists transcript metadata, summaries, checkpoints, and restart state
- `ProjectMemory`
  - canonical memory layer backed by markdown artifacts and SQLite
- `ToolBus`
  - shared registration of local tools and MCP servers
- `GSDCompatibilityLayer`
  - re-expresses GSD workflow stages so they work across runtimes

## How This Fits The Current vCompany Architecture

vCompany already has the right seams for this migration.

### Existing useful seams

- clone/artifact deployment
- context sync
- PM context building
- strategist/worker bootstrapping
- worker memory store
- per-agent routing and supervision

### Current code that will eventually need replacement or adaptation

- direct `claude -p` usage in PM and conversation paths
- hardcoded Claude session semantics in worker conversation handling
- Claude-specific assumptions in resume/relaunch paths

### Migration direction

1. Keep current orchestration and supervision model.
2. Replace direct provider-specific session calls with runtime adapters.
3. Move model/provider choice into a central router.
4. Move long-term memory into vCompany-owned state.
5. Let runtimes be replaceable execution engines.

## How GSD Still Fits

GSD should remain part of vCompany.

The important insight is:

- GSD is valuable as a workflow and anti-context-rot system
- GSD is not valuable only because it runs inside Claude Code

### What vCompany should preserve from GSD

- `discuss-phase`
- `plan-phase`
- `execute-phase`
- `verify-work`
- `ship`
- checkpointing and resumability
- planning artifact generation in `.planning/`
- explicit separation between planning and execution

### What changes

Instead of making every agent depend on a Claude-only runtime, vCompany should
define a runtime-agnostic compatibility layer:

- `discuss-phase`
  - produces assumptions/questions
  - routes clarification through Strategist/PM
- `plan-phase`
  - writes plan artifacts
- `execute-phase`
  - bounded tool-driven implementation loop
- `verify-work`
  - review/test/diagnostic pass
- `resume-work`
  - reconstructs session state from transcript summary + project memory

This keeps the workflow but removes the provider lock-in.

## MCP, Tools, Context, and Memory

### MCP

MCP is the external tool bus, not the memory system.

Use MCP for:

- GitHub
- browser automation
- docs/search
- databases
- repo intelligence
- custom `vco-control` server

The custom `vco-control` MCP server should expose vCompany-native operations like:

- read project status
- read/update decisions
- request interface update
- fetch current milestone scope
- query agent ownership
- publish checkin/report

### Built-in local tools

Every runtime still needs direct local tools:

- Bash
- Read
- Write/Edit/Patch
- Glob/Grep/Search
- test execution
- git inspection

## Generic Runtime Versus Claude-Native Runtime

### Why not use one generic runtime for everything

Using one generic runtime for Claude, DeepSeek, and Gemini is possible, but it
flattens Claude into a lowest-common-denominator integration.

That loses some Claude-specific advantages:

- first-party session semantics
- first-party checkpointing/compaction behavior
- first-party hooks and plugin support
- closer parity with Claude Code behavior
- less translation between Claude-native agent behavior and vCompany

So the preferred shape is:

- uniform public interface in vCompany
- multiple runtime implementations underneath

This preserves architectural uniformity without forcing every provider through
the same generic execution path.

### When a generic runtime is good enough

A generic runtime is a good fit for DeepSeek and Gemini if it provides:

- tool calling
- session persistence
- context compaction
- MCP support
- plugin/hooks support
- filesystem tools
- shell execution
- diagnostics/LSP or equivalent
- programmatic server/SDK access

That is why OpenCode-like runtimes are attractive for the non-Claude lanes.

## Are Generic Models Less Strong Than Claude Code

This comparison needs to be stated carefully:

- Claude Code is not just a model
- Claude Code is a runtime + tool stack + context management system layered on
  top of Claude models

So a generic DeepSeek or Gemini setup is not weaker just because it is not using
"Claude Code". The real comparison is:

- model quality
- runtime quality
- tool quality
- context management quality
- workflow discipline

### What Claude Code gives "for free"

Claude-native tooling gives:

- strong built-in coding loop behavior
- session persistence
- compaction/checkpoint behavior
- hooks
- plugins
- MCP integration
- polished file/tool interaction

### What generic models need in order to compete

To make DeepSeek and Gemini perform closer to a Claude-Code-quality workflow,
vCompany or its generic runtime needs to supply:

- strong system prompts per role
- strict tool schemas
- explicit plan/execute/verify workflow
- repo mapping and scoped retrieval
- transcript summaries and compaction
- LSP/diagnostics
- patch-oriented editing
- build/test loops
- review lane
- escalation lane
- memory/checkpoint persistence
- cost-aware routing

In other words, generic models are not automatically weaker. They are usually
more dependent on runtime engineering quality.

## Practical Take On Generic Models

### Gemini

Gemini is stronger than "generic CLI only" if used through Google's SDKs and not
through a bare OpenAI-compat wrapper, because Google exposes:

- function calling
- automatic function execution in SDKs
- built-in MCP support in Python and JavaScript SDKs
- long-context and document-processing capabilities

That makes Gemini especially strong for:

- research
- document synthesis
- context compression
- planning support

It is not automatically the best default code execution lane.

### DeepSeek

DeepSeek is viable in a generic runtime because the official API exposes:

- OpenAI-compatible chat completions
- function calling
- JSON output
- caching information
- multi-turn conversation
- beta prefix/FIM style coding helpers

This makes it a strong default worker/reviewer lane when wrapped in a good local
runtime.

It is strongest when:

- task shape is constrained
- context is well prepared
- tools are strongly typed
- escalation is available for risky work

### Claude

Claude benefits most from the first-party runtime path. That is why Claude
should not be forced into generic mode unless the operational simplicity win is
worth the capability loss.

### Session memory

Runtime session memory is disposable and local to the runtime.

It should include:

- active transcript
- rolling summary
- tool history
- checkpoints
- restart metadata

### Canonical project memory

Canonical memory must live in vCompany, not inside one runtime.

That includes:

- `PROJECT-BLUEPRINT.md`
- `INTERFACES.md`
- `MILESTONE-SCOPE.md`
- `PROJECT-STATUS.md`
- `PM-CONTEXT.md`
- decisions log
- backlog state
- SQLite memory/state stores

### Key design rule

If a runtime session dies, vCompany must still be able to continue from project
memory plus a compact transcript summary.

That is the main anti-context-rot property that needs to survive the move to a
multi-provider architecture.

## Practical Decision Record

### Decisions currently favored

- vCompany remains the orchestrator and source of truth.
- Use multiple runtimes, not one universal provider-specific engine.
- Claude lanes should use the official Anthropic Agent SDK.
- DeepSeek and Gemini lanes should run through a generic multi-provider runtime,
  likely OpenCode.
- Keep GSD as a workflow discipline and compatibility layer.
- Keep canonical memory in vCompany-owned files and databases.
- Use model escalation ladders instead of one model for everything.

### Decisions explicitly not favored

- Do not make ClawCode the base of the system.
- Do not rebuild all of Claude Code internally unless there is no official path.
- Do not make runtime-local session memory the source of truth.
- Do not couple GSD permanently to a single provider runtime.

## Immediate Next Implementation Steps

1. Introduce `RuntimePort`.
2. Build `ClaudeRuntime` on Anthropic Agent SDK.
3. Build `GenericRuntime` on OpenCode for DeepSeek/Gemini.
4. Add `LLMRouter` and `BudgetGovernor`.
5. Move conversation state into `SessionStore`.
6. Implement `vco-control` MCP server.
7. Add `GSDCompatibilityLayer`.
8. Migrate PM/Strategist/worker runtime entry points off direct `claude -p`.

## Related Local Files

- `MODEL-SELECTION.md`
- `MODEL-ROUTING.md`
- `model-routing.yaml`
