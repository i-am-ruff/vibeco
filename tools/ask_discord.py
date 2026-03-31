#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion -- routes questions through daemon socket.

Uses the daemon's CommunicationPort abstraction instead of hitting Discord API
directly. Works for both local and Docker agents — only needs the daemon socket
(no network access, no bot token required in the agent).

Protocol:
  - Receives JSON on stdin with session_id, hook_event_name, tool_name, tool_input
  - Sends question to daemon via Unix socket RPC
  - Daemon posts to Discord (or any platform) and polls for reply
  - Returns deny + permissionDecisionReason carrying the answer back to Claude
  - NEVER hangs: top-level try/except guarantees JSON output on any error
"""

from __future__ import annotations

import json
import os
import socket
import sys


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "1.0"
SOCKET_PATH = os.environ.get("VCO_SOCKET_PATH", "/tmp/vco-daemon.sock")


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
# Daemon socket client (stdlib only — no project imports in hook scripts)
# ---------------------------------------------------------------------------

def daemon_call(method: str, params: dict, timeout: float = 660.0) -> dict:
    """Send an RPC call to the daemon via Unix socket. Returns result dict."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(SOCKET_PATH)

    # Hello handshake
    hello = json.dumps({"id": "hello", "method": "hello", "params": {"version": PROTOCOL_VERSION}})
    sock.sendall((hello + "\n").encode())
    _recv_line(sock)  # consume hello response

    # RPC call
    req = json.dumps({"id": "req-1", "method": method, "params": params})
    sock.sendall((req + "\n").encode())
    resp_line = _recv_line(sock)
    sock.close()

    parsed = json.loads(resp_line)
    if "error" in parsed:
        raise RuntimeError(parsed["error"].get("message", "RPC error"))
    return parsed.get("result", {})


def _recv_line(sock: socket.socket) -> bytes:
    """Read one newline-terminated line from socket."""
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Daemon closed connection")
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Main hook logic: parse stdin, route question through daemon, return answer."""
    raw = sys.stdin.read()
    input_data = json.loads(raw)

    if input_data.get("tool_name") != "AskUserQuestion":
        output_allow()

    tool_input = input_data.get("tool_input", {})
    questions = tool_input.get("questions", [])

    if not questions:
        output_allow()

    agent_id = os.environ.get("VCO_AGENT_ID", os.environ.get("AGENT_ID", "unknown-agent"))
    timeout_mode = os.environ.get("VCO_TIMEOUT_MODE", "continue")

    result = daemon_call("ask", {
        "agent_id": agent_id,
        "questions": questions,
        "timeout_mode": timeout_mode,
    })

    answer = result.get("answer", "")
    status = result.get("status", "error")

    if status == "ok":
        output_deny(f"Answered via Discord: {answer}")
    elif status == "timeout":
        output_deny(answer)
    else:
        output_deny(f"Hook error: {answer}")


# ---------------------------------------------------------------------------
# Entry point -- guaranteed fallback
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        output_deny(
            f"Hook error (auto-fallback): {exc}. "
            "Proceeding with first available option."
        )
