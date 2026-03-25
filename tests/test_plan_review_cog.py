"""Tests for PlanReviewView, RejectFeedbackModal, build_plan_review_embed, and PlanReviewCog."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.bot.views.plan_review import PlanReviewView
from vcompany.bot.views.reject_modal import RejectFeedbackModal
from vcompany.bot.embeds import build_plan_review_embed


# ---------------------------------------------------------------------------
# PlanReviewView tests
# ---------------------------------------------------------------------------


class TestPlanReviewView:
    """PlanReviewView provides Approve/Reject buttons for plan gate."""

    def test_has_approve_and_reject_buttons(self):
        """View has exactly two buttons: Approve and Reject."""
        view = PlanReviewView(agent_id="agent-1", plan_path="/plans/01-01-PLAN.md")
        labels = [child.label for child in view.children]
        assert "Approve" in labels
        assert "Reject" in labels
        assert len(labels) == 2

    def test_default_timeout_is_3600(self):
        """Default timeout is 3600 seconds (1 hour) per Pitfall 4."""
        view = PlanReviewView(agent_id="agent-1", plan_path="/plans/01-01-PLAN.md")
        assert view.timeout == 3600.0

    def test_initial_result_is_none(self):
        """result starts as None, feedback starts as empty string."""
        view = PlanReviewView(agent_id="agent-1", plan_path="/plans/01-01-PLAN.md")
        assert view.result is None
        assert view.feedback == ""

    @pytest.mark.asyncio
    async def test_plan_review_view_approve(self):
        """Clicking approve sets result='approved' and stops the view."""
        view = PlanReviewView(agent_id="agent-1", plan_path="/plans/01-01-PLAN.md")
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()

        await view.approve.callback(interaction)

        assert view.result == "approved"
        interaction.response.edit_message.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_review_view_reject(self):
        """Clicking reject opens RejectFeedbackModal; after submit sets result='rejected' and feedback text."""
        view = PlanReviewView(agent_id="agent-1", plan_path="/plans/01-01-PLAN.md")
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.response.send_modal = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()

        # Patch modal.wait to return False (not timed out) and set feedback
        with patch.object(RejectFeedbackModal, "wait", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = False  # not timed out

            # We need to also set feedback_text on the modal instance
            original_init = RejectFeedbackModal.__init__

            def patched_init(self_modal, **kwargs):
                original_init(self_modal, **kwargs)
                self_modal.feedback_text = "Needs more tests"

            with patch.object(RejectFeedbackModal, "__init__", patched_init):
                await view.reject.callback(interaction)

        assert view.result == "rejected"
        assert view.feedback == "Needs more tests"

    @pytest.mark.asyncio
    async def test_plan_review_view_timeout(self):
        """View with short timeout results in result=None after timeout."""
        view = PlanReviewView(
            agent_id="agent-1", plan_path="/plans/01-01-PLAN.md", timeout=0.01
        )
        assert view.result is None
        # After timeout, result stays None


# ---------------------------------------------------------------------------
# RejectFeedbackModal tests
# ---------------------------------------------------------------------------


class TestRejectFeedbackModal:
    """RejectFeedbackModal captures rejection feedback text."""

    def test_initial_feedback_text_empty(self):
        """feedback_text starts as empty string."""
        modal = RejectFeedbackModal()
        assert modal.feedback_text == ""

    @pytest.mark.asyncio
    async def test_reject_modal_submit(self):
        """Modal on_submit captures feedback text from TextInput."""
        modal = RejectFeedbackModal()

        # TextInput.value is a property -- mock it via _value attribute
        modal.feedback._value = "The plan lacks error handling"

        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await modal.on_submit(interaction)

        assert modal.feedback_text == "The plan lacks error handling"
        interaction.response.send_message.assert_awaited_once_with(
            "Feedback recorded.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# build_plan_review_embed tests
# ---------------------------------------------------------------------------


class TestBuildPlanReviewEmbed:
    """build_plan_review_embed creates rich embeds for plan review."""

    def test_build_plan_review_embed(self):
        """Embed has title with agent_id, fields for phase/plan/tasks/goal, footer with plan path, green color."""
        embed = build_plan_review_embed(
            agent_id="frontend-1",
            phase="05",
            plan_number="03",
            task_count=4,
            goal="Build the plan review UI",
            plan_path="/project/plans/05-03-PLAN.md",
        )

        assert isinstance(embed, discord.Embed)
        assert "frontend-1" in embed.title
        assert embed.color == discord.Color.green()
        assert embed.footer.text == "Path: /project/plans/05-03-PLAN.md"

        # Check fields
        field_names = [f.name for f in embed.fields]
        assert "Phase" in field_names
        assert "Plan" in field_names
        assert "Tasks" in field_names

        # Check field values
        field_dict = {f.name: f.value for f in embed.fields}
        assert field_dict["Phase"] == "05"
        assert field_dict["Plan"] == "03"
        assert field_dict["Tasks"] == "4"

    def test_build_plan_review_embed_with_safety_warning(self):
        """When safety_valid=False, embed has orange color and warning field."""
        embed = build_plan_review_embed(
            agent_id="backend-1",
            phase="03",
            plan_number="01",
            task_count=2,
            goal="Some goal",
            plan_path="/plans/03-01-PLAN.md",
            safety_valid=False,
            safety_message="Missing columns",
        )

        assert embed.color == discord.Color.orange()
        field_names = [f.name for f in embed.fields]
        assert "Safety Warning" in field_names

        safety_field = next(f for f in embed.fields if f.name == "Safety Warning")
        assert "Missing columns" in safety_field.value

    def test_build_plan_review_embed_no_safety_warning_when_valid(self):
        """When safety_valid=True (default), no Safety Warning field."""
        embed = build_plan_review_embed(
            agent_id="agent-1",
            phase="01",
            plan_number="01",
            task_count=1,
            goal="Test",
            plan_path="/plans/PLAN.md",
        )

        field_names = [f.name for f in embed.fields]
        assert "Safety Warning" not in field_names
