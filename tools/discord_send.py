#!/usr/bin/env python3
"""Fire-and-forget Discord message sender with optional file attachment.

Self-contained script using ONLY Python stdlib. Called by agents via
/vco:send to post messages (with optional file attachments) to their
Discord channel.

Usage:
    python3 discord_send.py "message text"
    python3 discord_send.py "message text" --file /path/to/REPORT.md
    python3 discord_send.py "check this" --file https://example.com/doc.pdf

Environment variables (required):
    DISCORD_BOT_TOKEN  — Bot token for API auth
    DISCORD_GUILD_ID   — Guild to find the channel in
    VCO_AGENT_ID       — Agent ID (channel is #task-{agent_id} or #agent-{agent_id})
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"


def _resolve_channel(bot_token: str, guild_id: str, agent_id: str) -> str | None:
    """Find the agent's Discord channel (#task-{id} or #agent-{id})."""
    url = f"{DISCORD_API}/guilds/{guild_id}/channels"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "DiscordBot (https://vcompany.dev, 1.0)",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            channels = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching channels: {e}", file=sys.stderr)
        return None

    # Prefer task-{id}, fall back to agent-{id}
    for prefix in ("task-", "agent-"):
        target = f"{prefix}{agent_id}"
        for ch in channels:
            if ch.get("name") == target:
                return ch["id"]
    return None


def _send_text_only(bot_token: str, channel_id: str, content: str) -> bool:
    """Send a text-only message via JSON POST."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://vcompany.dev, 1.0)",
    }
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        return False


def _build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    """Build multipart/form-data body with a file attachment.

    Args:
        fields: Form fields (key: value pairs, sent as text parts).
        file_path: Local file to attach.

    Returns:
        (body_bytes, content_type_header)
    """
    boundary = "----VcoDiscordSendBoundary"
    lines: list[bytes] = []

    # Text fields
    for key, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"Content-Type: application/json")
        lines.append(b"")
        lines.append(value.encode() if isinstance(value, str) else value)

    # File attachment
    filename = file_path.name
    file_data = file_path.read_bytes()
    lines.append(f"--{boundary}".encode())
    lines.append(
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"'.encode()
    )
    lines.append(b"Content-Type: application/octet-stream")
    lines.append(b"")
    lines.append(file_data)

    # Closing boundary
    lines.append(f"--{boundary}--".encode())

    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _send_with_file(
    bot_token: str, channel_id: str, content: str, file_path: Path
) -> bool:
    """Send a message with a local file attachment via multipart/form-data."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages"

    payload_json = json.dumps({"content": content})
    body, content_type = _build_multipart({"payload_json": payload_json}, file_path)

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": content_type,
        "User-Agent": "DiscordBot (https://vcompany.dev, 1.0)",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Error sending message with file: {e}", file=sys.stderr)
        return False


def _send_with_url(bot_token: str, channel_id: str, content: str, url_str: str) -> bool:
    """Send a message with a URL embedded (Discord auto-previews)."""
    full_content = f"{content}\n{url_str}"
    return _send_text_only(bot_token, channel_id, full_content)


def main() -> None:
    """Parse args and send message."""
    args = sys.argv[1:]
    if not args:
        print("Usage: discord_send.py \"message\" [--file /path/or/url]", file=sys.stderr)
        sys.exit(1)

    # Parse arguments
    message = args[0]
    file_arg: str | None = None
    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_arg = args[idx + 1]

    # Environment
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    agent_id = os.environ.get("VCO_AGENT_ID", os.environ.get("AGENT_ID", ""))

    if not bot_token or not guild_id or not agent_id:
        print("Error: DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, VCO_AGENT_ID required", file=sys.stderr)
        sys.exit(1)

    channel_id = _resolve_channel(bot_token, guild_id, agent_id)
    if not channel_id:
        print(f"Error: Could not find channel for agent {agent_id}", file=sys.stderr)
        sys.exit(1)

    # Send
    if file_arg is None:
        ok = _send_text_only(bot_token, channel_id, message)
    elif file_arg.startswith("http://") or file_arg.startswith("https://"):
        ok = _send_with_url(bot_token, channel_id, message, file_arg)
    else:
        path = Path(file_arg).expanduser().resolve()
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        ok = _send_with_file(bot_token, channel_id, message, path)

    if ok:
        print(f"Message sent to #{agent_id}")
    else:
        print("Failed to send message", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
