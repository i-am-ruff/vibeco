---
phase: 04-discord-bot-core
plan: 01
subsystem: discord
tags: [discord.py, pydantic-settings, discord-bot, cogs, permissions, embeds]

# Dependency graph
requires:
  - phase: 02-agent-lifecycle
    provides: "AgentManager, CrashTracker with callback injection"
  - phase: 03-monitor-coordination
    provides: "MonitorLoop with on_agent_dead/stuck/plan_detected callbacks, generate_project_status"
provides:
  - "VcoBot(commands.Bot) with setup_hook loading 4 Cog extensions"
  - "BotConfig pydantic-settings model for DISCORD_BOT_TOKEN and DISCORD_GUILD_ID"
  - "setup_project_channels for category + standard + per-agent channels with permissions"
  - "ConfirmView with confirm/cancel buttons and user restriction"
  - "is_owner() role check decorator for vco-owner role"
  - "build_status_embed and build_alert_embed helpers"
affects: [04-02-commands-cog, 04-03-alerts-cog, 04-04-bot-entry-point]

# Tech tracking
tech-stack:
  added: [discord.py 2.7.1, aiohttp, aiohappyeyeballs, aiosignal, attrs, frozenlist, multidict, propcache, yarl, idna]
  patterns: [discord.py Cog architecture, pydantic-settings for bot config, Pitfall 7 on_ready guard, Pitfall 6 ready flag]

key-files:
  created:
    - src/vcompany/bot/__init__.py
    - src/vcompany/bot/config.py
    - src/vcompany/bot/client.py
    - src/vcompany/bot/channel_setup.py
    - src/vcompany/bot/permissions.py
    - src/vcompany/bot/embeds.py
    - src/vcompany/bot/views/__init__.py
    - src/vcompany/bot/views/confirm.py
    - src/vcompany/bot/cogs/__init__.py
    - tests/test_bot_config.py
    - tests/test_confirm_view.py
    - tests/test_bot_client.py
    - tests/test_channel_setup.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "discord.py button callbacks are bound methods; tests invoke via callback(interaction) not callback(self, interaction)"

patterns-established:
  - "Pitfall 7 guard: _initialized flag prevents duplicate on_ready work during reconnects"
  - "Pitfall 6 guard: is_bot_ready property lets cogs check bot readiness before operations"
  - "Permission overwrites pattern: default_role view-only, owner_role send+manage on category"
  - "ConfirmView pattern: interaction_user_id restricts button presses to command invoker"

requirements-completed: [DISC-01, DISC-02, DISC-10, DISC-12]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 4 Plan 1: Bot Foundation Summary

**Discord bot foundation with VcoBot client, BotConfig, channel setup, ConfirmView, role-check decorator, and embed builders using discord.py 2.7 Cog architecture**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T14:53:34Z
- **Completed:** 2026-03-25T14:56:34Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Installed discord.py 2.7.1 with all transitive dependencies
- Created VcoBot(commands.Bot) that loads 4 Cog extensions via setup_hook and creates vco-owner role on first on_ready
- Created channel setup that builds vco-{project} category with 5 standard channels + per-agent channels and role-based permission overwrites
- Created reusable ConfirmView, is_owner decorator, and embed builders as building blocks for Plan 02-04

## Task Commits

Each task was committed atomically:

1. **Task 1: Add discord.py dependency and create bot package foundation** - `75a1b72` (feat)
2. **Task 2: VcoBot client class and channel setup** - `b76646f` (feat)

## Files Created/Modified
- `pyproject.toml` - Added discord.py>=2.7,<3 dependency
- `src/vcompany/bot/__init__.py` - Package marker
- `src/vcompany/bot/config.py` - BotConfig pydantic-settings model for token and guild ID
- `src/vcompany/bot/client.py` - VcoBot with setup_hook, on_ready, Pitfall 6/7 guards
- `src/vcompany/bot/channel_setup.py` - setup_project_channels with category, standard, and agent channels
- `src/vcompany/bot/permissions.py` - is_owner() decorator checking vco-owner role
- `src/vcompany/bot/embeds.py` - build_status_embed and build_alert_embed helpers
- `src/vcompany/bot/views/__init__.py` - Package marker
- `src/vcompany/bot/views/confirm.py` - ConfirmView with confirm/cancel buttons and user restriction
- `src/vcompany/bot/cogs/__init__.py` - Package marker for future Cog modules
- `tests/test_bot_config.py` - 5 tests for BotConfig env loading and defaults
- `tests/test_confirm_view.py` - 9 tests for ConfirmView buttons, callbacks, user restriction
- `tests/test_bot_client.py` - 10 tests for VcoBot init, setup_hook, on_ready, Pitfall 7
- `tests/test_channel_setup.py` - 6 tests for channel creation, permissions, agent channels

## Decisions Made
- discord.py button decorator callbacks are already bound to the view instance; test invocations use `view.confirm.callback(interaction)` not `view.confirm.callback(view, interaction)`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed discord.py button callback invocation in tests**
- **Found during:** Task 1 (test_confirm_view.py)
- **Issue:** discord.py decorated button callbacks use `_ItemCallback.__call__` which takes `(self, interaction)` not `(view, self, interaction)`
- **Fix:** Changed `view.confirm.callback(view, interaction)` to `view.confirm.callback(interaction)` in tests
- **Files modified:** tests/test_confirm_view.py
- **Verification:** All 14 tests pass
- **Committed in:** 75a1b72 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test fix for discord.py API behavior. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Bot foundation complete: VcoBot, BotConfig, channel_setup, ConfirmView, is_owner, embeds all ready
- Plan 02 (CommandsCog) can import VcoBot, is_owner, ConfirmView, build_status_embed
- Plan 03 (AlertsCog) can import VcoBot, build_alert_embed
- Plan 04 (Bot entry point) can import VcoBot, BotConfig
- All 204 tests pass with no regressions

## Self-Check: PASSED

All 13 created files verified on disk. Both task commits (75a1b72, b76646f) found in git log.

---
*Phase: 04-discord-bot-core*
*Completed: 2026-03-25*
