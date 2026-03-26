---
allowed-tools:
  - Bash
---

<objective>
Report your current status to Discord so the team knows what you're doing.
Call this at key milestones: after research, after planning, after execution.
</objective>

<instructions>
Write a one-line status update to your agent's status file. This file is monitored by vCompany and posted to your Discord channel automatically.

```bash
mkdir -p ~/vco-projects/$PROJECT_NAME/state/reports
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $AGENT_ID: $STATUS" >> ~/vco-projects/$PROJECT_NAME/state/reports/$AGENT_ID.log
```

Where $STATUS is a brief description of what just happened, like:
- "researched phase 1 - ready to plan"
- "plan created for phase 1 - 3 tasks, waiting for review"
- "phase 1 complete - 4 commits, all tests passing"
- "starting phase 2 execution"

Keep it short. One line. The monitor handles formatting and posting.
</instructions>
