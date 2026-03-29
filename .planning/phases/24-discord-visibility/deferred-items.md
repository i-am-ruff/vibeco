# Phase 24 Deferred Items

## External callers of removed RuntimeAPI methods

These bot cog files call RuntimeAPI methods that were removed in Plan 04. They were
outside Plan 04's `files_modified` scope. The calls are now dead code paths that will
raise AttributeError if reached at runtime.

1. **src/vcompany/bot/cogs/strategist.py:173** -- calls `runtime_api.relay_strategist_message()`
   - Now routed through MentionRouterCog (@Strategist mentions)
   - The StrategistCog.on_message handler should be removed or updated to use MentionRouterCog

2. **src/vcompany/bot/cogs/strategist.py:245** -- calls `runtime_api.handle_pm_escalation()`
   - PM escalations now go through Discord (@Strategist messages)
   - The handle_pm_escalation method in StrategistCog should be updated

3. **src/vcompany/bot/cogs/workflow_orchestrator_cog.py:425** -- calls `runtime_api.route_completion_to_pm()`
   - Completion events now posted as Discord messages by GSD agents directly
   - This code path in WorkflowOrchestratorCog should be removed

4. **src/vcompany/bot/cogs/question_handler.py:143** -- calls `strategist_cog.handle_pm_escalation()`
   - Indirect caller (goes through StrategistCog, not RuntimeAPI directly)
   - Will break when StrategistCog.handle_pm_escalation is fixed

### Recommended fix
Remove or update these callers in a follow-up cleanup plan. All inter-agent communication
now flows through Discord via MentionRouterCog -- these old relay paths are superseded.
