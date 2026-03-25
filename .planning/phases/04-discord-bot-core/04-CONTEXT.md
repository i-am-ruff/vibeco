# Phase 4: Discord Bot Core - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the Discord bot framework: discord.py Cog architecture, channel auto-setup (category per project), all operator commands (!new-project, !dispatch, !status, !standup, !kill, !relaunch, !integrate), role-based access (Owner + Viewer tiers), async threading discipline, and auto-reconnect. The bot imports the vcompany library directly (same process) and injects real callbacks into MonitorLoop for alert routing.

</domain>

<decisions>
## Implementation Decisions

### Command UX
- **D-01:** `!new-project` is a **conversation starter**, not a file uploader. It creates a thread in a dedicated channel where the owner describes the product, drops references (images, docs, links). Phase 6's PM/Strategist will drive the conversation intelligence — Phase 4 scaffolds the thread and channel infrastructure.
- **D-02:** `!new-project [optional-name]` creates: (1) a project thread for discussion, (2) the Discord category + channels for the project. If no name given, bot asks for one.
- **D-03:** All destructive commands (!kill, !integrate) require confirmation via reaction buttons before executing. Bot posts "Are you sure? React ✅ to confirm, ❌ to cancel" and waits.
- **D-04:** `!status` returns a rich embed showing all agents' current phase, state, and blockers — assembled from PROJECT-STATUS.md.
- **D-05:** `!dispatch [agent-id | all]`, `!kill agent-id`, `!relaunch agent-id` — thin wrappers calling AgentManager methods.
- **D-06:** `!standup` triggers interactive group standup (creates per-agent threads in #standup). Full implementation in Phase 7, Phase 4 scaffolds the command and channel.
- **D-07:** `!integrate` triggers integration pipeline. Full implementation in Phase 7, Phase 4 scaffolds the command.

### Role Mapping
- **D-08:** Two permission tiers:
  - **Owner** (Discord role: `vco-owner`): All commands — !new-project, !dispatch, !kill, !relaunch, !integrate, !standup, !status
  - **Viewer** (default / no role): Read-only — can view all channels, see !status output, but cannot execute any commands
- **D-09:** Role check is a decorator on each command. Unauthorized users get a polite "You need the vco-owner role to use this command" message.
- **D-10:** Bot creates the `vco-owner` role on startup if it doesn't exist.

### Bot Architecture
- **D-11:** Bot imports vcompany library directly — same Python process. No subprocess calls. AgentManager, MonitorLoop, sync_context_files, CrashTracker all used via direct import.
- **D-12:** discord.py Cog architecture with 4 Cogs: CommandsCog (operator commands), AlertsCog (receives monitor callbacks, posts to #alerts), PlanReviewCog (placeholder for Phase 5 plan gate), StrategistCog (placeholder for Phase 6 PM).
- **D-13:** Bot startup: load project config, initialize AgentManager + MonitorLoop + CrashTracker, inject Discord callbacks (on_circuit_open, on_agent_dead, on_agent_stuck, on_plan_detected), start monitor loop as asyncio background task.
- **D-14:** All blocking operations (file I/O, git calls) use `asyncio.to_thread()` to never block the Discord gateway event loop.
- **D-15:** Bot auto-reconnects on network interruption using discord.py's built-in reconnect handling. Monitor loop continues independently during disconnects — alerts are buffered and sent when reconnected.

### Channel Setup
- **D-16:** Discord category per project: category name = `vco-{project-name}`.
- **D-17:** Channels within category: #strategist, #plan-review, #standup, #alerts, #decisions, plus #agent-{id} per agent from agents.yaml.
- **D-18:** Channel creation happens when `!new-project` is confirmed (after discussion thread). Bot creates category + all channels in one operation.
- **D-19:** Viewer role gets read-only permissions on all channels. Owner role gets send permissions.

### Bot Entry Point
- **D-20:** Bot runs as `vco bot` CLI command (not a separate script). Click command that starts the discord.py event loop.
- **D-21:** Bot token loaded from environment variable `DISCORD_BOT_TOKEN`. Guild ID from `DISCORD_GUILD_ID`.
- **D-22:** Single guild bot (not multi-server). Simplifies permissions and channel management.

### Claude's Discretion
- Embed formatting for !status (colors, fields, layout)
- Error message wording
- Whether to add !help command listing available commands
- Alert message formatting in #alerts
- Buffer implementation for alerts during disconnect

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `VCO-ARCHITECTURE.md` — Discord channel structure (lines 686-697), bot commands, message formats (lines 746-784), Cog architecture recommendation

### Phase 1-3 Code (reuse these)
- `src/vcompany/orchestrator/agent_manager.py` — AgentManager (dispatch, kill, relaunch)
- `src/vcompany/orchestrator/crash_tracker.py` — CrashTracker with on_circuit_open callback
- `src/vcompany/monitor/loop.py` — MonitorLoop with callback injection (on_agent_dead, on_agent_stuck, on_plan_detected)
- `src/vcompany/monitor/status_generator.py` — generate_project_status (for !status embed)
- `src/vcompany/coordination/sync_context.py` — sync_context_files
- `src/vcompany/models/config.py` — ProjectConfig, AgentConfig, load_config
- `src/vcompany/cli/main.py` — Click CLI group, add `bot` command

### Research
- `.planning/research/STACK.md` — discord.py 2.7.x recommendation
- `.planning/research/PITFALLS.md` — Discord gateway disconnects, asyncio blocking

### Requirements
- `.planning/REQUIREMENTS.md` — DISC-01..12

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AgentManager` — dispatch(), dispatch_all(), kill(), relaunch() for all lifecycle commands
- `MonitorLoop` — accepts callback dict on init, inject Discord alert senders
- `CrashTracker` — on_circuit_open callback for circuit breaker alerts
- `generate_project_status()` — returns formatted string for !status embed content
- `load_config()` — parse agents.yaml to get agent roster for channel creation

### Established Patterns
- Callback injection (MonitorLoop, CrashTracker) — bot injects real Discord message senders
- Click CLI for all commands — add `vco bot` alongside existing commands
- Pydantic models for config — bot config could extend or compose existing models

### Integration Points
- MonitorLoop callbacks → AlertsCog methods (on_agent_dead → post to #alerts)
- CrashTracker.on_circuit_open → AlertsCog.alert_circuit_open
- AgentManager methods → CommandsCog command handlers
- generate_project_status → !status embed builder

</code_context>

<specifics>
## Specific Ideas

- !new-project creates a conversation thread, not a form — owner describes the product naturally
- Phase 6 PM/Strategist will add intelligence to the !new-project conversation
- Bot + monitor run in the same asyncio event loop (discord.py and MonitorLoop are both asyncio)
- Confirmation buttons use discord.py's View/Button components (not raw reactions)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-discord-bot-core*
*Context gathered: 2026-03-25*
