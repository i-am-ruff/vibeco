"""WorkflowMasterCog: Bridges #workflow-master channel to persistent Claude dev conversation.

Mirrors StrategistCog structure but simpler -- no PM escalation, no decision
logger, no pending escalations. workflow-master is a hands-on developer agent
with full dev tools (Bash, Read, Write, Edit, Glob, Grep).

Pure I/O adapter: routes Discord messages to daemon via RuntimeAPI.
Conversation management lives in the daemon layer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.daemon.runtime_api import RuntimeAPI

logger = logging.getLogger(__name__)

# Persistent directory for files sent to workflow-master via Discord
_WM_FILES_DIR = Path.home() / "vco-workflow-master-files"

# Discord message character limit
_DISCORD_MAX_CHARS = 2000


def _get_runtime_api(bot: VcoBot) -> RuntimeAPI | None:
    """Get RuntimeAPI from daemon if available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is None:
        return None
    return getattr(daemon, "runtime_api", None)


class WorkflowMasterCog(commands.Cog):
    """Bridges #workflow-master channel to persistent Claude dev conversation.

    Owner messages are forwarded via RuntimeAPI. Responses are posted back
    with Thinking... placeholder and split on 2000 chars.

    Pure Discord I/O adapter -- conversation management lives in daemon.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._wm_channel: discord.TextChannel | None = None
        self._owner_role_name = "vco-owner"
        self._initialized: bool = False

    async def initialize(
        self, persona_path: Path | None, worktree_path: Path
    ) -> None:
        """Initialize the workflow-master channel and signal daemon.

        Conversation creation now happens in the daemon layer via RuntimeAPI.
        This method just resolves the Discord channel.

        Args:
            persona_path: Unused (persona handled in daemon). Kept for API symmetry.
            worktree_path: Path to the git worktree (passed to daemon for conversation init).
        """
        await self._resolve_channel()

        # Signal daemon to initialize the workflow-master conversation
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            await runtime_api.initialize_workflow_master(worktree_path)

        self._initialized = True
        logger.info("WorkflowMasterCog initialized with worktree: %s", worktree_path)

    async def _resolve_channel(self) -> None:
        """Find #workflow-master channel in the guild."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.name == "workflow-master":
                    self._wm_channel = channel
                    break

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Resolve channel on ready."""
        await self._resolve_channel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Process messages in #workflow-master from the owner.

        Filters:
        - Skip webhook messages
        - Skip bot's own messages
        - Skip messages from non-workflow-master channels
        - Skip messages from users without vco-owner role
        """
        # Filter: skip webhooks
        if message.webhook_id is not None:
            return

        # Filter: skip bot's own messages UNLESS it's a Strategist task dispatch
        if message.author.id == self.bot.user.id:
            if not message.content.startswith("[strategist]"):
                return

        # Filter: skip non-workflow-master channels
        if (
            self._wm_channel is None
            or message.channel.id != self._wm_channel.id
        ):
            if not (
                self._wm_channel is not None
                and message.channel is self._wm_channel
            ):
                return

        # Allow: owner (vco-owner role) or the Strategist (bot itself posting a task)
        is_owner = self._has_owner_role(message.author)
        is_strategist_task = (
            message.author.id == self.bot.user.id
            and message.content.startswith("[strategist]")
        )
        if not is_owner and not is_strategist_task:
            return

        # Route through RuntimeAPI
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            await message.reply(
                "Workflow-master not initialized yet. Please wait for bot startup to complete."
            )
            return

        # Build message content with attachments
        content = await self._build_message_with_attachments(message)

        # Forward to daemon and post response
        await self._send_to_channel(message.channel, content, runtime_api)

    @staticmethod
    def _has_owner_role(member: discord.Member) -> bool:
        """Check if member has the vco-owner role."""
        return any(role.name == "vco-owner" for role in getattr(member, "roles", []))

    async def _build_message_with_attachments(self, message: discord.Message) -> str:
        """Download attachments and build a message referencing their file paths.

        Files are saved to ~/vco-workflow-master-files/{timestamp}_{filename}.

        Args:
            message: Discord message potentially containing attachments.

        Returns:
            Message content with file paths appended.
        """
        content = message.content or ""

        if not message.attachments:
            return content

        _WM_FILES_DIR.mkdir(exist_ok=True)

        file_refs = []
        for att in message.attachments:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = att.filename.replace(" ", "_")
            dest = _WM_FILES_DIR / f"{ts}_{safe_name}"

            try:
                data = await att.read()
                dest.write_bytes(data)
                file_refs.append(f"[attached file: {dest}]")
                logger.info("Saved attachment: %s (%d bytes)", dest, len(data))
            except Exception:
                logger.exception("Failed to download attachment %s", att.filename)
                file_refs.append(f"[failed to download: {att.filename}]")

        if file_refs:
            content = content + "\n" + "\n".join(file_refs) if content else "\n".join(file_refs)

        return content

    async def _send_to_channel(
        self, channel: discord.TextChannel, content: str, runtime_api: RuntimeAPI
    ) -> str:
        """Send message to workflow-master via RuntimeAPI and post response.

        Args:
            channel: Discord channel to send response to.
            content: User message content to send.
            runtime_api: RuntimeAPI instance for daemon delegation.

        Returns:
            Full response text.
        """
        status_msg = await channel.send("[workflow-master] working on it...")

        response = await runtime_api.relay_workflow_master_message(content)

        # Delete the "working on it" status
        try:
            await status_msg.delete()
        except Exception:
            pass

        # Post final response as new message(s)
        if not response:
            await channel.send("[workflow-master] done (no text output)")
            return ""

        remaining = response
        while remaining:
            chunk = remaining[:_DISCORD_MAX_CHARS]
            prefix = "[workflow-master] " if remaining == response else ""
            await channel.send(f"{prefix}{chunk}")
            remaining = remaining[len(chunk):]

        return response


async def setup(bot: commands.Bot) -> None:
    """Load WorkflowMasterCog into the bot."""
    await bot.add_cog(WorkflowMasterCog(bot))
