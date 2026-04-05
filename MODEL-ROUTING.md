# Model Routing and Escalation Policy

This document defines the default `situation -> model` mapping for vCompany and
the deterministic escalation rules that move work from cheaper models to more
expensive ones.

The current stack is:

| Profile | Provider | Model | Primary use |
| --- | --- | --- | --- |
| `researcher` | Google | `gemini-3.1-flash-lite` | Cheap ingestion, summarization, log compaction, backlog condensation |
| `worker_default` | DeepSeek | `deepseek-chat` | Default PM and worker lane for routine coding and decomposition |
| `reviewer` | DeepSeek | `deepseek-reasoner` | Bug triage, log-heavy diagnosis, review, hidden-regression checks |
| `premium_coder` | Anthropic | `claude-sonnet-4.6` | High-risk coding, complex refactors, premium review, difficult debugging |
| `strategist` | Anthropic | `claude-opus-4.6` | Project kickoff, milestone planning, architecture resets, irreducible ambiguity |

## Principles

1. Route by observable signals, not by model self-reported confidence.
2. Use the cheapest model that is likely to succeed for the current situation.
3. Escalate on repeated failure, blast radius, or risk category.
4. Keep human escalation as the last step, not the first.
5. Treat DeepSeek V4 as a cutover candidate, not the current baseline, until the
   public API is live and passes vCompany acceptance checks.

## Situation to Model

| Situation | Primary model | Notes |
| --- | --- | --- |
| Ingest large design docs, docs, logs, issue threads, or command output | `researcher` | Summarize first; compress context before it reaches expensive models |
| New project kickoff | `strategist` | Convert owner input into roadmap, milestones, and contracts |
| Milestone planning or interface contract work | `strategist` | Strategic and cross-agent work starts here |
| Routine PM decomposition and backlog grooming | `worker_default` | Default lane unless the task is strategic or high risk |
| Routine coding in owned files | `worker_default` | Use when change is small and local |
| Log-heavy bug triage or flaky test diagnosis | `reviewer` | Reasoning lane before paying for Sonnet |
| High-risk coding or cross-cutting refactor | `premium_coder` | Use for auth, billing, migrations, contracts, infra, concurrency, or shared runtime changes |
| Final review for medium/high-risk work | `reviewer`, then `premium_coder` if needed | Cheap reasoning pass first, premium pass on risky diffs |
| Architecture reset, ambiguous requirements, failed premium lane | `strategist` | Last model stop before human escalation |

## High-Risk Conditions

Route directly to `premium_coder` if any of these are true:

- Task touches authentication, authorization, billing, payments, migrations,
  schema, deployment, secrets, or infrastructure code.
- Task changes shared contracts, routing, transport, orchestration, or
  concurrency/recovery logic.
- Expected change touches more than 5 files.
- Expected change exceeds roughly 600 changed lines.
- Task spans multiple agent ownership boundaries.
- Task changes public APIs, message schemas, or persistence formats.

Route directly to `strategist` if any of these are true:

- The task is a new project or milestone definition.
- Requirements conflict with existing architecture.
- The system needs to choose among materially different architectural options.
- The owner input is incomplete enough that execution would otherwise branch.

## Default Escalation Ladders

### Coding

`worker_default -> reviewer -> premium_coder -> strategist -> human`

Use this for normal implementation tasks.

### Research

`researcher -> strategist -> human`

Use this for document ingestion, backlog shaping, and context compression.

### Review

`reviewer -> premium_coder -> strategist -> human`

Use this for bug triage, verification, and release-readiness checks.

## Deterministic Escalation Rules

Escalation is based on runtime signals, not prompts asking the model whether it
feels uncertain.

### From `worker_default` to `reviewer`

Escalate when any of these are true:

- One implementation attempt completed but build, lint, or target tests still fail.
- The task is primarily diagnostic rather than generative.
- The agent is spending more time explaining logs than changing code.
- The task is blocked on root-cause analysis of an error, race, or flaky test.

### From `worker_default` to `premium_coder`

Escalate when any of these are true:

- Two implementation attempts fail on the same task.
- The task meets any high-risk condition listed above.
- The change grows past the default blast-radius thresholds.
- The worker needs to redesign a module boundary rather than edit inside one.

### From `reviewer` to `premium_coder`

Escalate when any of these are true:

- The reviewer finds a concrete defect but the required fix is invasive.
- The review output says the bug source crosses files or subsystems.
- The reviewer cannot reduce the issue to a localized fix plan.

### From `premium_coder` to `strategist`

Escalate when any of these are true:

- One premium attempt still leaves the task blocked.
- The premium lane identifies architectural contradiction or missing product policy.
- The task now requires contract, milestone, or ownership changes.

### From `strategist` to `human`

Escalate only when any of these are true:

- Multiple valid architectural options remain and the system lacks a policy to choose.
- Budget policy, auth policy, or external-provider policy must be set by the owner.
- The strategist cannot continue without product intent that is not encoded anywhere.

## Acceptance Rule for DeepSeek V4

When the public DeepSeek API exposes V4, do not switch immediately. Treat V4 as
the new `worker_default` only after all of the following are true:

1. Official API availability is confirmed.
2. Tool calling required by vCompany is supported.
3. vCompany acceptance tests pass against the new model.
4. Two shadow runs complete without rollback to `deepseek-chat`.

Until then, `worker_default` stays on `deepseek-chat`.
