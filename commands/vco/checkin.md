---
allowed-tools:
  - Read
  - Bash
---

<objective>
Post a checkin to your agent's Discord channel after shipping a phase.
</objective>

<instructions>
1. Read .planning/ROADMAP.md for current phase status
2. Read the most recent .planning/phases/*/SUMMARY.md
3. Run `git log --oneline -5` for recent commits
4. Read PROJECT-STATUS.md for dependency context

Post to Discord via webhook using Bash(curl):

Format:
```
**{AGENT_ID}** shipped Phase {N}: {phase name}
**Commits:** {N} commits
**Summary:** {2-3 sentence description of what was built}
**Gaps/Notes:** {any deferred items or verification gaps}
**Next:** Phase {N+1} -- {phase name}
**Dependencies:** {any blockers from other agents, or "clear"}
```

Use the DISCORD_AGENT_WEBHOOK_URL environment variable for the webhook.
Do not wait for responses. This is fire-and-forget.
</instructions>
