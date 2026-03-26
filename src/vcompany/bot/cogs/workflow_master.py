"""WorkflowMasterCog: Bridges #workflow-master channel to persistent Claude dev conversation.

Mirrors StrategistCog structure but simpler -- no PM escalation, no decision
logger, no pending escalations. workflow-master is a hands-on developer agent
with full dev tools (Bash, Read, Write, Edit, Glob, Grep).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.strategist.conversation import StrategistConversation

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger(__name__)

# Persistent directory for files sent to workflow-master via Discord
_WM_FILES_DIR = Path.home() / "vco-workflow-master-files"

# Discord message character limit
_DISCORD_MAX_CHARS = 2000


class WorkflowMasterCog(commands.Cog):
    """Bridges #workflow-master channel to persistent Claude dev conversation.

    Owner messages are forwarded to a Claude conversation with full dev tools.
    Responses are posted back with Thinking... placeholder and split on 2000 chars.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._conversation: StrategistConversation | None = None
        self._wm_channel: discord.TextChannel | None = None
        self._owner_role_name = "vco-owner"

    async def initialize(
        self, persona_path: Path | None, worktree_path: Path
    ) -> None:
        """Initialize the workflow-master conversation with worktree-aware persona.

        Writes the built persona to a known file path so StrategistConversation
        can load it via persona_path. Uses workflow-master's own session UUID
        and expanded tool set.

        Args:
            persona_path: Unused (persona is built from template). Kept for API symmetry.
            worktree_path: Path to the git worktree for workflow-master.
        """
        from vcompany.strategist.workflow_master_persona import (
            WORKFLOW_MASTER_SESSION_UUID,
            build_workflow_master_persona,
        )

        persona_text = build_workflow_master_persona(worktree_path)
        runtime_persona_path = Path.home() / "vco-workflow-master-persona.md"
        runtime_persona_path.write_text(persona_text)

        self._conversation = StrategistConversation(
            persona_path=runtime_persona_path,
            session_id=WORKFLOW_MASTER_SESSION_UUID,
            allowed_tools="Bash Read Write Edit Glob Grep",
        )
        await self._resolve_channel()
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

        # Check if conversation is initialized
        if self._conversation is None:
            await message.reply(
                "Workflow-master not initialized yet. Please wait for bot startup to complete."
            )
            return

        # Build message content with attachments
        content = await self._build_message_with_attachments(message)

        # Forward to conversation and post response
        await self._send_to_channel(message.channel, content)

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
        self, channel: discord.TextChannel, content: str
    ) -> str:
        """Send message to workflow-master with streaming progress.

        Posts new messages for each tool action so the Strategist and owner
        can see what's happening in real-time. Final response is a separate message.

        Args:
            channel: Discord channel to send response to.
            content: User message content to send to conversation.

        Returns:
            Full response text.
        """
        status_msg = await channel.send("[workflow-master] working on it...")
        last_tool_desc = ""

        async def on_tool_use(description: str):
            nonlocal last_tool_desc
            if description != last_tool_desc:
                last_tool_desc = description
                try:
                    await channel.send(f"[workflow-master] {description}")
                except Exception:
                    pass  # don't break the stream if Discord rate-limits

        response = await self._conversation.send_streaming(content, on_tool_use=on_tool_use)

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
