"""Plan review view with Approve/Reject buttons.

Used by PlanReviewCog to gate plan execution per GATE-02/GATE-03.
Long timeout (3600s) per Pitfall 4 -- modal has its own Discord timeout.
"""

import discord

from vcompany.bot.views.reject_modal import RejectFeedbackModal


class PlanReviewView(discord.ui.View):
    """Approve/Reject buttons for plan review.

    Attributes:
        agent_id: Agent that created the plan.
        plan_path: Path to the PLAN.md file.
        result: "approved", "rejected", or None (timeout).
        feedback: Rejection feedback text (empty if approved).
    """

    def __init__(self, agent_id: str, plan_path: str, *, timeout: float = 3600.0) -> None:
        super().__init__(timeout=timeout)
        self.agent_id = agent_id
        self.plan_path = plan_path
        self.result: str | None = None
        self.feedback: str = ""

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="plan_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.result = "approved"
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"Plan approved for **{self.agent_id}**: `{self.plan_path}`",
            ephemeral=True,
        )
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="plan_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = RejectFeedbackModal()
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out:
            return  # user didn't submit modal, keep view active
        self.result = "rejected"
        self.feedback = modal.feedback_text
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        # edit_message via the original message since interaction was consumed by modal
        if interaction.message:
            await interaction.message.edit(view=self)
        self.stop()
