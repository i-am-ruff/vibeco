"""Release button view for standup threads.

No timeout per D-11 -- owner decides when to release each agent.
"""

from __future__ import annotations

from typing import Callable

import discord


class ReleaseView(discord.ui.View):
    """Release button for standup threads. No timeout per D-11."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(timeout=None)  # No timeout per D-11
        self.agent_id = agent_id
        self.released = False
        self._release_callback: Callable[[str], None] | None = None

    def set_release_callback(self, callback: Callable[[str], None]) -> None:
        """Set the callback invoked when Release is clicked."""
        self._release_callback = callback

    @discord.ui.button(label="Release", style=discord.ButtonStyle.success)
    async def release(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Handle Release button press -- unblock the agent."""
        self.released = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"Agent **{self.agent_id}** released.", ephemeral=True
        )
        if self._release_callback:
            self._release_callback(self.agent_id)
        self.stop()
