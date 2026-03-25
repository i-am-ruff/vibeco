"""Knowledge Transfer document generation for Strategist context handoff.

When the Strategist conversation approaches the token limit (~800K),
a KT document is generated capturing the essential state of the conversation.
A fresh session starts with this document as its foundation.
"""

from datetime import datetime, timezone


def generate_knowledge_transfer(
    messages: list[dict],
    system_prompt: str,
    token_count: int,
) -> str:
    """Build a Knowledge Transfer markdown document from conversation state.

    The KT document captures:
    - Token count at transfer time
    - Conversation summary (last 20 messages)
    - Key decisions extracted from assistant messages
    - Personality calibration from first assistant message
    - Open threads from recent user messages
    - Original system prompt

    Args:
        messages: The full conversation messages list (role/content dicts).
        system_prompt: The system prompt used for the conversation.
        token_count: Token count at the time of transfer.

    Returns:
        Assembled markdown string for the KT document.
    """
    sections: list[str] = []

    # Header
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections.append(f"# Knowledge Transfer\n\nGenerated: {timestamp}\n")

    # Token count
    sections.append(f"## Token Count at Transfer\n\n{token_count}\n")

    # Conversation summary -- last 20 messages
    sections.append("## Conversation Summary\n")
    recent = messages[-20:]
    for msg in recent:
        role = msg["role"]
        content = msg["content"]
        preview = content[:200]
        if len(content) > 200:
            preview += "..."
        sections.append(f"- **{role}**: {preview}")
    sections.append("")

    # Key decisions -- lines containing decision keywords from assistant messages
    sections.append("## Key Decisions Made\n")
    decision_keywords = {"decision", "decided", "approved", "rejected"}
    decision_lines: list[str] = []
    for msg in messages:
        if msg["role"] != "assistant":
            continue
        for line in msg["content"].splitlines():
            line_lower = line.lower()
            if any(kw in line_lower for kw in decision_keywords):
                decision_lines.append(f"- {line.strip()}")
    if decision_lines:
        sections.append("\n".join(decision_lines))
    else:
        sections.append("No explicit decisions detected.")
    sections.append("")

    # Personality and tone -- first assistant message as calibration reference
    sections.append("## Personality and Tone\n")
    first_assistant = None
    for msg in messages:
        if msg["role"] == "assistant":
            first_assistant = msg["content"]
            break
    if first_assistant:
        sections.append(f"First assistant response (personality reference):\n\n{first_assistant}\n")
    else:
        sections.append("No assistant messages found for personality calibration.\n")

    # Open threads -- last 5 user messages
    sections.append("## Open Threads\n")
    user_messages = [m for m in messages if m["role"] == "user"]
    recent_user = user_messages[-5:]
    for msg in recent_user:
        preview = msg["content"][:200]
        if len(msg["content"]) > 200:
            preview += "..."
        sections.append(f"- {preview}")
    sections.append("")

    # Original system prompt
    sections.append(f"## Original System Prompt\n\n{system_prompt}\n")

    return "\n".join(sections)
