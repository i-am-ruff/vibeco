---
allowed-tools:
  - Bash
---

Signal that your task is complete and exit the session cleanly.

<instructions>
1. Write a completion marker so the system knows this was a clean exit (not a crash):

```bash
echo "completed $(date -u +%Y-%m-%dT%H:%M:%SZ)" > .finished
```

2. Then exit the session:

```
/exit
```

Only run this when the Strategist has confirmed your work is done. If they ask for more work, continue instead.
</instructions>
