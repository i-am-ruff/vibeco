#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion -- routes questions through Discord.

This is a self-contained script that uses ONLY Python stdlib.
It is invoked by Claude Code when an agent calls AskUserQuestion.

Protocol:
  - Receives JSON on stdin with session_id, hook_event_name, tool_name, tool_input
  - Posts question to Discord via webhook
  - Polls /tmp/vco-answers/{request_id}.json for an answer
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
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANSWER_DIR = Path("/tmp/vco-answers")
POLL_INTERVAL = 5  # seconds between polls
MAX_POLLS = 120  # 10 minutes total (120 * 5s)


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
# Discord webhook
# ---------------------------------------------------------------------------

def post_question(
    webhook_url: str,
    agent_id: str,
    request_id: str,
    questions: list,
) -> None:
    """POST formatted question embed to Discord webhook.

    Args:
        webhook_url: Discord webhook URL for #strategist channel.
        agent_id: Identifier for the agent asking the question.
        request_id: UUID for tracking the answer.
        questions: List of question dicts from AskUserQuestion tool_input.
    """
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
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


# ---------------------------------------------------------------------------
# Answer polling
# ---------------------------------------------------------------------------

def poll_answer(
    request_id: str,
    poll_interval: int = POLL_INTERVAL,
    max_polls: int = MAX_POLLS,
) -> str | None:
    """Poll for answer file at ANSWER_DIR/{request_id}.json.

    Returns the answer text if found, None on timeout.
    Deletes the answer file after reading (cleanup on read).
    On JSON parse error, deletes corrupt file and continues polling.
    """
    answer_path = ANSWER_DIR / f"{request_id}.json"

    for _ in range(max_polls):
        if answer_path.exists():
            try:
                data = json.loads(answer_path.read_text())
                answer = data.get("answer", "")
                # Cleanup on read
                try:
                    answer_path.unlink()
                except OSError:
                    pass
                return answer
            except (json.JSONDecodeError, KeyError):
                # Corrupt file -- delete and retry next cycle
                try:
                    answer_path.unlink()
                except OSError:
                    pass
        if poll_interval > 0:
            time.sleep(poll_interval)

    return None


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


def alert_timeout(
    webhook_url: str,
    agent_id: str,
    request_id: str,
    fallback: str,
) -> None:
    """POST a timeout warning embed to Discord webhook.

    Failure here must not block the hook.
    """
    try:
        embed = {
            "title": f"Timeout: Auto-fallback for {agent_id}",
            "description": (
                f"Question {request_id} timed out. Fallback: {fallback}"
            ),
            "color": 0xE67E22,
        }
        payload = json.dumps({"embeds": [embed]}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Never block the hook on alert failure


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

    agent_id = os.environ.get("VCO_AGENT_ID", "unknown-agent")
    webhook_url = os.environ.get("DISCORD_AGENT_WEBHOOK_URL", "")
    timeout_mode = os.environ.get("VCO_TIMEOUT_MODE", "continue")
    request_id = str(uuid.uuid4())

    ANSWER_DIR.mkdir(parents=True, exist_ok=True)

    if webhook_url:
        post_question(webhook_url, agent_id, request_id, questions)

    answer = poll_answer(request_id, POLL_INTERVAL, MAX_POLLS)

    if answer is None:
        fallback = get_fallback_answer(questions, timeout_mode)
        if webhook_url and timeout_mode == "continue":
            alert_timeout(webhook_url, agent_id, request_id, fallback)
        output_deny(fallback)
    else:
        output_deny(f"Human answered via Discord: {answer}")


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
