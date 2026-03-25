"""Reusable confirmation view with Confirm/Cancel buttons.

Used by destructive commands (!kill, !integrate) per D-03.
"""

import discord


class ConfirmView(discord.ui.View):
    """A confirmation dialog with Confirm and Cancel buttons.

    Attributes:
        value: True if confirmed, False if cancelled, None if timed out.
        interaction_user_id: If set, only this user can press buttons.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.value: bool | None = None
        self.interaction_user_id: int | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict button presses to the original command invoker."""
        if self.interaction_user_id is not None:
            if interaction.user.id != self.interaction_user_id:
                await interaction.response.send_message(
                    "Only the command invoker can use these buttons.",
                    ephemeral=True,
                )
                return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Handle confirm button press."""
        self.value = True
        await interaction.response.send_message("Confirmed.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Handle cancel button press."""
        self.value = False
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        self.stop()
