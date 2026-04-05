# Model Selection

Current default mapping for vCompany.

| Problem | Model |
| --- | --- |
| Large design docs, long logs, issue threads, backlog cleanup, context compression | `gemini-3.1-flash-lite-preview` |
| Cross-document synthesis, premium research, ambiguous requirements, turning messy research into an execution-ready brief | `gemini-3.1-pro-preview` |
| New project kickoff from owner prompt + design doc | `claude-opus-4.6` |
| Milestone design, architecture planning, contract decisions, strategy resets | `claude-opus-4.6` |
| Routine PM decomposition, backlog routing, normal ticket shaping | `deepseek-chat` |
| Routine coding in owned files with small blast radius | `deepseek-chat` |
| Cheap bulk refactors, boilerplate, repetitive implementation work | `deepseek-chat` |
| Log-heavy bug triage, flaky test diagnosis, hidden-regression hunting, review-first debugging | `deepseek-reasoner` |
| Final review of medium-risk changes | `deepseek-reasoner` |
| High-risk coding: auth, billing, payments, migrations, contracts, infra, shared runtime changes | `claude-sonnet-4.6` |
| Cross-cutting refactors, multi-file redesigns, hard debugging after cheap lanes fail | `claude-sonnet-4.6` |
| Final review of high-risk changes | `claude-sonnet-4.6` |
| Situation still blocked after premium coding/review | `claude-opus-4.6` |
| No encoded policy exists and multiple valid product/architecture choices remain | human escalation |

## Default Ladders

| Problem type | Model order |
| --- | --- |
| Research | `gemini-3.1-flash-lite-preview -> gemini-3.1-pro-preview -> claude-opus-4.6 -> human` |
| Coding | `deepseek-chat -> deepseek-reasoner -> claude-sonnet-4.6 -> claude-opus-4.6 -> human` |
| Review | `deepseek-reasoner -> claude-sonnet-4.6 -> claude-opus-4.6 -> human` |

## Notes

- `deepseek-chat` remains the default worker model until `DeepSeek V4` is publicly available in the API and passes local acceptance checks.
- `gemini-3.1-pro-preview` is the premium research lane, not the default coding lane.
- `claude-opus-4.6` is for strategy and irreducible ambiguity, not routine throughput.
