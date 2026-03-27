# Phase 1: Foundation and Configuration - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the foundational tooling layer: Pydantic config models for agents.yaml, git and tmux wrapper abstractions, atomic file write utilities, and the `vco init` + `vco clone` commands that create project structures and deploy per-agent artifacts (hooks, GSD config, CLAUDE.md, vco commands). After this phase, a valid agents.yaml produces a fully scaffolded project with isolated agent clones ready for dispatch.

</domain>

<decisions>
## Implementation Decisions

### CLI Structure
- **D-01:** Flat subcommand structure using click groups: `vco init`, `vco clone`, `vco dispatch`, etc. No nested subcommand groups.
- **D-02:** Follow click conventions: `--flag` for options, positional args for required inputs (e.g., `vco init myproject`).
- **D-03:** Entry point defined in pyproject.toml `[project.scripts]` section.

### Config Validation
- **D-04:** Strict validation — invalid agents.yaml rejected with clear Pydantic validation errors before any filesystem changes.
- **D-05:** Pydantic models for: AgentConfig (id, role, owns, consumes, gsd_mode, system_prompt), ProjectConfig (project, repo, agents, shared_readonly).
- **D-06:** Directory ownership validation: non-overlapping owned directories enforced at parse time.

### Clone Artifacts
- **D-07:** Per-clone deployment includes: .claude/settings.json (AskUserQuestion hook), .planning/config.json (GSD config), CLAUDE.md (cross-agent awareness), .claude/commands/vco/checkin.md, .claude/commands/vco/standup.md.
- **D-08:** Agent system prompt generated from template with: agent ID, role, owned directories, rules, milestone scope. Stored in context/agents/{id}.md.
- **D-09:** Template-based generation — Jinja2 or string.Template for all templated files.

### Project Layout
- **D-10:** Follow VCO-ARCHITECTURE.md directory structure exactly:
  ```
  ~/vcompany/projects/{project-name}/
  ├── clones/{agent-id}/    # One full repo clone per agent
  ├── context/
  │   ├── PROJECT-BLUEPRINT.md
  │   ├── INTERFACES.md
  │   ├── MILESTONE-SCOPE.md
  │   ├── PROJECT-STATUS.md
  │   ├── STRATEGIST-PROMPT.md
  │   └── agents/{id}.md
  └── agents.yaml
  ```
- **D-11:** Context docs (blueprint, interfaces, milestone scope) are provided by the user as input files. `vco init` copies them into the context/ directory.

### Wrappers and Utilities
- **D-12:** Git wrapper: thin module using subprocess.run() for clone, checkout, branch, merge, log, push, status. Standardized error handling and logging.
- **D-13:** tmux wrapper: abstraction over libtmux with create_session(), create_pane(), send_command(), is_alive(), get_output(), kill_pane(). If libtmux breaks, only this module changes.
- **D-14:** Atomic file write utility: write_atomic(path, content) — writes to {path}.tmp then os.rename(). Used for all coordination files.

### Claude's Discretion
- Internal module organization (how to split vco into packages/modules)
- Specific Pydantic model field types and validators beyond what's specified
- Error message formatting and verbosity levels
- Test structure and fixtures

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `VCO-ARCHITECTURE.md` — Authoritative system design. Defines directory structure, agent isolation model, GSD config, system prompt template, all component interactions.

### Project Context
- `.planning/PROJECT.md` — Project goals, constraints, key decisions
- `.planning/REQUIREMENTS.md` — FOUND-01..07, COORD-04..07 requirements for this phase
- `.planning/research/STACK.md` — Recommended libraries with versions (click, libtmux, pydantic, uv)
- `.planning/research/ARCHITECTURE.md` — Component boundaries and build order
- `.planning/research/PITFALLS.md` — tmux zombie detection, atomic write patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code.

### Established Patterns
- None yet — this phase establishes the foundational patterns.

### Integration Points
- This phase creates the foundation that Phase 2 (Agent Lifecycle) builds on: tmux wrapper for dispatch, git wrapper for clone operations, config models for agent definitions.

</code_context>

<specifics>
## Specific Ideas

- uv for package management (from research STACK.md)
- Pin libtmux tightly and wrap in abstraction layer (research recommendation)
- Use subprocess for git operations, not GitPython (research recommendation)
- Pydantic-settings for environment variable loading (.env support)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-configuration*
*Context gathered: 2026-03-25*
