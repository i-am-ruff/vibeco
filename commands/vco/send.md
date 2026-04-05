---
allowed-tools:
  - Bash
---

Send a message to your Discord channel, optionally with a file attachment.

<instructions>
Use the discord_send.py tool to post a message. The channel is resolved automatically from your agent ID.

**Text only:**
```bash
python3 ~/vcompany/tools/discord_send.py "Your message here"
```

**With a local file attachment:**
```bash
python3 ~/vcompany/tools/discord_send.py "Here are my findings" --file REPORT.md
```

**With a URL (Discord auto-previews):**
```bash
python3 ~/vcompany/tools/discord_send.py "Relevant resource" --file https://example.com/doc.pdf
```

The message is fire-and-forget. If someone replies, their response will arrive in your input automatically.
</instructions>
