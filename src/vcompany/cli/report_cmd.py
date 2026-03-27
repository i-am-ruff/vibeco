"""vco report command -- agents report status directly to Discord via bot HTTP API."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import click

# Module-level cache: agent_id -> channel_id
_channel_cache: dict[str, str] = {}


def _find_agent_channel(
    bot_token: str, guild_id: str, agent_id: str, project_name: str | None = None
) -> str | None:
    """Look up the #agent-{agent_id} channel in the guild via Discord HTTP API.

    When project_name is provided, only matches channels under the
    vco-{project_name} category to avoid routing to stale project channels.

    Uses module-level cache to avoid repeated API calls.
    Returns channel_id or None if not found.
    """
    cache_key = f"{project_name}:{agent_id}" if project_name else agent_id
    if cache_key in _channel_cache:
        return _channel_cache[cache_key]

    import httpx

    channel_name = f"agent-{agent_id}"
    url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "DiscordBot (https://vcompany.dev, 1.0)",
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=5.0)
        resp.raise_for_status()
        channels = resp.json()

        # Build category_id -> category_name map for filtering
        category_map: dict[str, str] = {}
        if project_name:
            target_category = f"vco-{project_name}"
            for ch in channels:
                if ch.get("type") == 4:  # GUILD_CATEGORY
                    category_map[ch["id"]] = ch["name"]

        for ch in channels:
            if ch.get("name") == channel_name:
                # If we have a project name, only match channels in the right category
                if project_name:
                    parent_id = ch.get("parent_id")
                    parent_name = category_map.get(parent_id, "")
                    if parent_name != target_category:
                        continue
                channel_id = ch["id"]
                _channel_cache[cache_key] = channel_id
                return channel_id
    except Exception:
        pass

    return None


def _post_to_channel(bot_token: str, channel_id: str, content: str) -> bool:
    """Post a message to a Discord channel via HTTP API.

    Returns True on success, False on failure.
    """
    import httpx

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, headers=headers, json={"content": content}, timeout=5.0)
        resp.raise_for_status()
        return True
    except Exception:
        return False


@click.command()
@click.argument("status", nargs=-1, required=True)
def report(status: tuple[str, ...]) -> None:
    """Report agent status directly to Discord.

    Usage: vco report starting plan-phase 1
           vco report phase 1 complete - all tests passing

    Reads DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, and AGENT_ID from environment
    variables (set by dispatch).
    """
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    agent_id = os.environ.get("AGENT_ID", "")
    project_name = os.environ.get("PROJECT_NAME", "")

    if not bot_token or not guild_id or not agent_id:
        click.echo(
            "Error: DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, and AGENT_ID env vars must be set",
            err=True,
        )
        raise SystemExit(1)

    status_text = " ".join(status)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = f"{ts} {agent_id}: {status_text}"

    # Find the agent's Discord channel (scoped to current project category)
    channel_id = _find_agent_channel(
        bot_token, guild_id, agent_id, project_name or None
    )
    if channel_id is None:
        click.echo(f"Warning: Could not find #agent-{agent_id} channel", err=True)
        click.echo(f"Reported (local only): {agent_id}: {status_text}")
        return

    # Post to Discord
    success = _post_to_channel(bot_token, channel_id, message)
    if success:
        click.echo(f"Reported: {agent_id}: {status_text}")
    else:
        click.echo(f"Warning: Failed to post to Discord", err=True)
        click.echo(f"Reported (local only): {agent_id}: {status_text}")
