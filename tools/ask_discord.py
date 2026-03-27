#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion -- routes questions through Discord REST API.

This is a self-contained script that uses ONLY Python stdlib.
It is invoked by Claude Code when an agent calls AskUserQuestion.

Protocol:
  - Receives JSON on stdin with session_id, hook_event_name, tool_name, tool_input
  - Posts question to #agent-{id} channel via Discord REST API
  - Polls for reply messages to the question message
  - Returns deny + permissionDecisionReason carrying the answer back to Claude
  - NEVER hangs: top-level try/except guarantees JSON output on any error
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCORD_API = "https://discord.com/api/v10"
POLL_INTERVAL = 5  # seconds between polls
MAX_POLLS_PM = 120  # 10 minutes (120 * 5s) for PM auto-answer timeout (D-17)
MAX_POLLS_ESCALATION = 0  # 0 = infinite, for owner escalation (D-18)
ESCALATION_MARKER = "escalated"  # substring in reply indicating escalation in progress


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def output_deny(reason: str) -> None:
    """Write deny JSON to stdout and exit. Carries answer back to Claude."""
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    json.dump(response, sys.stdout)
    sys.stdout.flush()
    sys.exit(0)


def output_allow() -> None:
    """Write allow JSON to stdout and exit. Lets the tool call proceed."""
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }
    json.dump(response, sys.stdout)
    sys.stdout.flush()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Stdin parsing
# ---------------------------------------------------------------------------

def parse_stdin() -> dict:
    """Read ALL of stdin and parse as JSON.

    Uses sys.stdin.read() (not readline) to get the full JSON payload.
    Raises on malformed input.
    """
    raw = sys.stdin.read()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _make_request(
    url: str,
    bot_token: str,
    method: str = "GET",
    data: dict | None = None,
    timeout: int = 10,
) -> dict | None:
    """Common HTTP helper using urllib.request.

    Returns parsed JSON or None on error.
    Sets Authorization header to Bot {bot_token}.
    """
    headers = {"Authorization": f"Bot {bot_token}"}
    body = None

    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------

def resolve_channel(
    bot_token: str,
    guild_id: str,
    agent_id: str,
    project_name: str | None = None,
) -> str | None:
    """Find #agent-{agent_id} channel in the guild via Discord REST API.

    When project_name is provided, only match channels under the
    vco-{project_name} category (type==4). Returns channel_id or None.
    """
    url = f"{DISCORD_API}/guilds/{guild_id}/channels"
    channels = _make_request(url, bot_token)
    if not channels:
        return None

    channel_name = f"agent-{agent_id}"

    # Build category map for project scoping
    category_map: dict[str, str] = {}
    if project_name:
        target_category = f"vco-{project_name}"
        for ch in channels:
            if ch.get("type") == 4:  # GUILD_CATEGORY
                category_map[ch["id"]] = ch["name"]

    for ch in channels:
        if ch.get("name") == channel_name:
            if project_name:
                parent_id = ch.get("parent_id")
                parent_name = category_map.get(parent_id, "")
                if parent_name != target_category:
                    continue
            return ch["id"]

    return None


# ---------------------------------------------------------------------------
# Post question
# ---------------------------------------------------------------------------

def post_question(
    bot_token: str,
    channel_id: str,
    agent_id: str,
    request_id: str,
    questions: list,
) -> str | None:
    """POST question as embed to #agent-{id} channel. Returns message_id or None."""
    question_data = questions[0]
    embed = {
        "title": f"Question from {agent_id}",
        "description": question_data["question"],
        "fields": [
            {"name": opt["label"], "value": opt["description"], "inline": True}
            for opt in question_data.get("options", [])
        ],
        "footer": {"text": f"Request: {request_id}"},
        "color": 0x3498DB,
    }
    payload = {
        "content": f"[{agent_id}] has a question:",
        "embeds": [embed],
    }

    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    result = _make_request(url, bot_token, method="POST", data=payload)
    if result and "id" in result:
        return result["id"]
    return None


# ---------------------------------------------------------------------------
# Poll for reply
# ---------------------------------------------------------------------------

def poll_for_reply(
    bot_token: str,
    channel_id: str,
    question_msg_id: str,
    poll_interval: int = POLL_INTERVAL,
    max_polls: int = MAX_POLLS_PM,
) -> str | None:
    """Poll for reply messages to the question.

    Checks message_reference.message_id for exact match.
    If escalation marker detected in any message, switches to infinite polling.
    On HTTP 429, respects Retry-After header.
    Returns answer string or None on timeout.
    """
    url = f"{DISCORD_API}/channels/{channel_id}/messages?after={question_msg_id}&limit=10"
    polls_done = 0
    effective_max = max_polls

    while effective_max == 0 or polls_done < effective_max:
        headers = {"Authorization": f"Bot {bot_token}"}
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                messages = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = float(e.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                continue
            messages = []
        except Exception:
            messages = []

        for msg in messages:
            # Check for direct reply to our question
            ref = msg.get("message_reference")
            if ref and ref.get("message_id") == question_msg_id:
                return msg.get("content", "")

            # Check for escalation marker in non-reply messages
            content = msg.get("content", "").lower()
            if ESCALATION_MARKER in content and effective_max != 0:
                effective_max = 0  # Switch to infinite polling

        polls_done += 1
        if poll_interval > 0:
            time.sleep(poll_interval)

    return None


# ---------------------------------------------------------------------------
# Timeout alert
# ---------------------------------------------------------------------------

def alert_timeout(
    bot_token: str,
    channel_id: str,
    agent_id: str,
    request_id: str,
    fallback: str,
) -> None:
    """POST a timeout warning message to the channel.

    Failure here must not block the hook.
    """
    try:
        content = (
            f"[system] Timeout: Auto-fallback for {agent_id} "
            f"(Request: {request_id}): {fallback}"
        )
        url = f"{DISCORD_API}/channels/{channel_id}/messages"
        _make_request(url, bot_token, method="POST", data={"content": content})
    except Exception:
        pass  # Never block the hook on alert failure


# ---------------------------------------------------------------------------
# Fallback handling
# ---------------------------------------------------------------------------

def get_fallback_answer(questions: list, timeout_mode: str) -> str:
    """Get fallback answer when polling times out.

    Args:
        questions: List of question dicts from tool_input.
        timeout_mode: "continue" (auto-select first option) or "block" (pause agent).

    Returns:
        Fallback answer string.
    """
    if timeout_mode == "block":
        return (
            "BLOCKED: No answer received within timeout. "
            "Agent should wait for human input before proceeding."
        )

    # Continue mode: try to pick the first option
    try:
        first_option = questions[0]["options"][0]
        label = first_option.get("label", "Unknown")
        description = first_option.get("description", "")
        return (
            f"Auto-selected (timeout): {label} - {description}. "
            "NOTE: This was an automatic fallback. "
            "Human did not respond within 10 minutes."
        )
    except (IndexError, KeyError):
        return (
            "No answer received and no options to fall back to. "
            "Proceeding with best judgment."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Main hook logic: parse stdin, post question, poll for answer, return."""
    input_data = parse_stdin()

    if input_data.get("tool_name") != "AskUserQuestion":
        output_allow()  # not our tool, let it through

    tool_input = input_data.get("tool_input", {})
    questions = tool_input.get("questions", [])

    if not questions:
        output_allow()  # no questions, let it through

    agent_id = os.environ.get("VCO_AGENT_ID", os.environ.get("AGENT_ID", "unknown-agent"))
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    project_name = os.environ.get("PROJECT_NAME", "")
    timeout_mode = os.environ.get("VCO_TIMEOUT_MODE", "continue")
    request_id = str(uuid.uuid4())

    if not bot_token or not guild_id:
        output_deny("Hook error: DISCORD_BOT_TOKEN and DISCORD_GUILD_ID not set. Auto-fallback.")
        return  # output_deny calls sys.exit

    channel_id = resolve_channel(bot_token, guild_id, agent_id, project_name or None)
    if not channel_id:
        output_deny(f"Hook error: Could not find #agent-{agent_id} channel. Auto-fallback.")
        return

    msg_id = post_question(bot_token, channel_id, agent_id, request_id, questions)
    if not msg_id:
        output_deny("Hook error: Failed to post question to Discord. Auto-fallback.")
        return

    answer = poll_for_reply(bot_token, channel_id, msg_id)

    if answer is None:
        fallback = get_fallback_answer(questions, timeout_mode)
        if timeout_mode == "continue":
            alert_timeout(bot_token, channel_id, agent_id, request_id, fallback)
        output_deny(fallback)
    else:
        output_deny(f"Answered via Discord: {answer}")


# ---------------------------------------------------------------------------
# Entry point -- HOOK-07: guaranteed fallback
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # let sys.exit() through
    except Exception as exc:
        # NEVER hang -- always produce valid JSON
        output_deny(
            f"Hook error (auto-fallback): {exc}. "
            "Proceeding with first available option."
        )
