# Phase 23: Strategist Autonomy - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The Strategist agent manages workforce through vco CLI commands via its Bash tool, with no special action tag parsing in the bot. Covers STRAT-01 (vco hire/give-task/dismiss from Bash tool), STRAT-02 (remove [CMD:...] parsing from StrategistCog), STRAT-03 (update persona to reference vco CLI).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — final cleanup phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/bot/cogs/strategist.py` — StrategistCog (already rewired to RuntimeAPI in Phase 22)
- `STRATEGIST-PERSONA.md` — Strategist system prompt
- `src/vcompany/cli/hire_cmd.py`, `give_task_cmd.py`, `dismiss_cmd.py` — CLI commands from Phase 21

### Integration Points
- StrategistCog action tag parsing ([CMD:...]) needs removal
- Persona needs vco CLI references instead of action tags
- Strategist Claude session needs Bash tool access to run vco commands

</code_context>

<specifics>
## Specific Ideas

No specific requirements.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
