"""QuestionHandlerCog: Bridges webhook-posted agent questions to interactive answer UIs.

Listens for webhook messages in #strategist (posted by ask_discord.py hook),
extracts the request_id from the embed footer, and creates a follow-up message
with option buttons. When user clicks a button, writes the answer file
atomically to /tmp/vco-answers/{request_id}.json for the hook to poll.

Implements the bot-side of the hook<->bot IPC per D-02 and Research Open Question 2.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("vcompany.bot.cogs.question_handler")

ANSWER_DIR = Path("/tmp/vco-answers")

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot


class AnswerView(discord.ui.View):
    """Dynamic button view for answering agent questions.

    Creates one button per option from the webhook embed fields,
    plus an "Other" button for free text.
    """

    def __init__(
        self,
        request_id: str,
        agent_id: str,
        options: list[dict[str, str]],
        *,
        timeout: float = 600.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.request_id = request_id
        self.agent_id = agent_id
        self.answered = False

        # Dynamically add option buttons (max 5 per row, max 25 total)
        for i, opt in enumerate(options[:20]):
            button = discord.ui.Button(
                label=opt.get("name", f"Option {i+1}")[:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"answer_{request_id}_{i}",
            )
            button.callback = self._make_option_callback(
                opt.get("name", ""), opt.get("value", "")
            )
            self.add_item(button)

        # Add "Other" button for free text
        other_btn = discord.ui.Button(
            label="Other (type answer)",
            style=discord.ButtonStyle.secondary,
            custom_id=f"answer_{request_id}_other",
        )
        other_btn.callback = self._other_callback
        self.add_item(other_btn)

    def _make_option_callback(self, label: str, description: str):
        async def callback(interaction: discord.Interaction) -> None:
            answer_text = f"{label} - {description}" if description else label
            await self._write_answer(answer_text, interaction)

        return callback

    async def _other_callback(self, interaction: discord.Interaction) -> None:
        """Show a modal for free text answer."""
        modal = OtherAnswerModal(request_id=self.request_id, agent_id=self.agent_id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.answer_text:
            await self._write_answer_file(
                modal.answer_text,
                str(interaction.user),
            )
            self.answered = True
            for child in self.children:
                child.disabled = True  # type: ignore[union-attr]
            if interaction.message:
                await interaction.message.edit(view=self)
            self.stop()

    async def _write_answer(self, answer_text: str, interaction: discord.Interaction) -> None:
        """Write answer file and update UI."""
        await self._write_answer_file(answer_text, str(interaction.user))
        self.answered = True
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"Answer recorded for `{self.agent_id}`: {answer_text}",
            ephemeral=True,
        )
        self.stop()

    async def _write_answer_file(self, answer_text: str, answered_by: str) -> None:
        """Write answer file atomically per Pitfall 3."""
        import asyncio

        await asyncio.to_thread(
            _write_answer_file_sync,
            self.request_id,
            self.agent_id,
            answer_text,
            answered_by,
        )


class OtherAnswerModal(discord.ui.Modal, title="Type Your Answer"):
    """Modal for free-text answers when predefined options don't fit."""

    answer_input = discord.ui.TextInput(
        label="Your answer",
        style=discord.TextStyle.paragraph,
        placeholder="Type your answer here...",
        required=True,
        max_length=2000,
    )

    def __init__(self, request_id: str, agent_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.request_id = request_id
        self.agent_id = agent_id
        self.answer_text: str = ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.answer_text = self.answer_input.value
        await interaction.response.send_message(
            f"Answer recorded for `{self.agent_id}`: {self.answer_text}",
            ephemeral=True,
        )


def _write_answer_file_sync(
    request_id: str, agent_id: str, answer: str, answered_by: str
) -> None:
    """Write answer JSON atomically (tmp+rename) per Pitfall 3 / D-02."""
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    answer_path = ANSWER_DIR / f"{request_id}.json"
    data = {
        "request_id": request_id,
        "agent_id": agent_id,
        "answer": answer,
        "answered_by": answered_by,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
    content = json.dumps(data)
    fd, tmp_path = tempfile.mkstemp(dir=str(ANSWER_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, str(answer_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class QuestionHandlerCog(commands.Cog):
    """Listens for webhook-posted questions in #strategist and provides answer UI."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._strategist_channel: discord.TextChannel | None = None

    async def _resolve_channel(self) -> None:
        """Find #strategist channel in the guild."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.name == "strategist":
                    self._strategist_channel = channel
                    break

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._resolve_channel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Detect webhook questions in #strategist and create answer buttons."""
        # Only process webhook messages in #strategist
        if not message.webhook_id:
            return
        if not self._strategist_channel:
            await self._resolve_channel()
        if not self._strategist_channel or message.channel.id != self._strategist_channel.id:
            return

        # Extract request_id from embed footer
        if not message.embeds:
            return
        embed = message.embeds[0]
        if not embed.footer or not embed.footer.text:
            return

        match = re.search(r"Request:\s*(\S+)", embed.footer.text)
        if not match:
            return
        request_id = match.group(1)

        # Extract agent_id from embed title
        agent_id = "unknown"
        if embed.title:
            title_match = re.search(r"Question from (\S+)", embed.title)
            if title_match:
                agent_id = title_match.group(1)

        # Extract options from embed fields
        options = [
            {"name": field.name, "value": field.value or ""}
            for field in embed.fields
        ]

        # Create answer view and post follow-up
        view = AnswerView(
            request_id=request_id,
            agent_id=agent_id,
            options=options,
        )

        await message.reply(
            f"Select an answer for **{agent_id}** (Request: `{request_id}`):",
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    """Load QuestionHandlerCog into the bot."""
    await bot.add_cog(QuestionHandlerCog(bot))
