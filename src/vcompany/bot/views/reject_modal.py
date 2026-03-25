"""Rejection feedback modal for plan review.

Prompts the reviewer to explain why a plan is rejected.
Feedback is sent to the agent's tmux pane for replanning.
"""

import discord


class RejectFeedbackModal(discord.ui.Modal, title="Plan Rejection Feedback"):
    """Modal dialog for collecting rejection reason text."""

    feedback = discord.ui.TextInput(
        label="Why is this plan rejected?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what needs to change...",
        required=True,
        max_length=2000,
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.feedback_text: str = ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.feedback_text = self.feedback.value
        await interaction.response.send_message("Feedback recorded.", ephemeral=True)
