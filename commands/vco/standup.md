---
allowed-tools:
  - Read
  - Bash
  - Write
  - Edit
---

<objective>
Participate in an interactive group standup. Report your status,
then respond to any owner feedback.
</objective>

<instructions>
## Phase 1: Report

1. Read .planning/ROADMAP.md for phase status
2. Read .planning/STATE.md for decisions and blockers
3. Run `git log --oneline --since="24 hours ago"` for recent work
4. Read any recent .planning/phases/*/VERIFICATION.md for gaps
5. Read any recent .planning/phases/*/SUMMARY.md for outcomes
6. Read PROJECT-STATUS.md for cross-agent context

Post to #standup via webhook:

```
**{AGENT_ID}** Standup
**Status:** Phase {X}/{Y} -- {state}
**Since last standup:** {N} commits
**Work done:** {semantic description of what was actually built}
**Blockers:** {list or "None"}
**Completed phases:** {list with descriptions}
**Current:** {active work}
**Next:** {upcoming phase}
**Dependencies:** {cross-agent dependency status}
**Risks:** {scope creep, gaps, delays -- or "None"}
```

## Phase 2: Listen for feedback

After posting, poll the Discord thread under your standup post
for owner replies (check every 5s, timeout after 5 min).

If the owner replies:
- Acknowledge their feedback
- If they request reprioritization: update .planning/ROADMAP.md
  and confirm the change
- If they request scope change: note it in .planning/STATE.md
  and confirm
- If they ask a question: answer from your project knowledge
- Post your response in the same thread

If no reply after 5 minutes: post "No feedback received. Continuing."
and exit.
</instructions>
