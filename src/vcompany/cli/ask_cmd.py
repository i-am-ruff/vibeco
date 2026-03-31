"""vco ask -- route AskUserQuestion through daemon socket.

Called by Claude Code's PreToolUse hook for AskUserQuestion. Reads hook JSON
from stdin, posts the question to the agent's Discord channel via daemon
CommunicationPort, polls for reply, returns the answer as a hook deny reason.

Uses only the daemon socket — no network, no bot token, works in Docker containers.
"""

from __future__ import annotations

import json
import os
import sys

import click

from vcompany.daemon.client import DaemonClient
from vcompany.shared.paths import VCO_SOCKET_PATH


def _output_deny(reason: str) -> None:
    """Write deny JSON to stdout and exit. Carries answer back to Claude."""
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.flush()
    sys.exit(0)


def _output_allow() -> None:
    """Write allow JSON to stdout and exit."""
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)
    sys.stdout.flush()
    sys.exit(0)


@click.command()
def ask() -> None:
    """Route AskUserQuestion hook through daemon socket.

    Reads hook JSON from stdin. Called automatically by Claude Code hooks.
    """
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw)

        if input_data.get("tool_name") != "AskUserQuestion":
            _output_allow()

        tool_input = input_data.get("tool_input", {})
        questions = tool_input.get("questions", [])

        if not questions:
            _output_allow()

        agent_id = os.environ.get("VCO_AGENT_ID", os.environ.get("AGENT_ID", "unknown-agent"))
        timeout_mode = os.environ.get("VCO_TIMEOUT_MODE", "continue")

        client = DaemonClient(VCO_SOCKET_PATH, timeout=660.0)
        client.connect()
        result = client.call("ask", {
            "agent_id": agent_id,
            "questions": questions,
            "timeout_mode": timeout_mode,
        })
        client.close()

        answer = result.get("answer", "")
        status = result.get("status", "error")

        if status == "ok":
            _output_deny(f"Answered via Discord: {answer}")
        elif status == "timeout":
            _output_deny(answer)
        else:
            _output_deny(f"Hook error: {answer}")
    except SystemExit:
        raise
    except Exception as exc:
        _output_deny(
            f"Hook error (auto-fallback): {exc}. "
            "Proceeding with first available option."
        )
