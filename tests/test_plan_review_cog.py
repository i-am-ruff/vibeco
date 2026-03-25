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
from vcompany.bot.cogs.plan_review import (
    PlanReviewCog,
    _extract_frontmatter_field,
    _extract_objective,
)
from vcompany.models.monitor_state import AgentMonitorState


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


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for _extract_frontmatter_field and _extract_objective."""

    def test_extract_frontmatter_field(self):
        """Extracts phase and plan fields from frontmatter."""
        content = "---\nphase: 05-hooks\nplan: 03\ntype: execute\n---\n"
        assert _extract_frontmatter_field(content, "phase") == "05-hooks"
        assert _extract_frontmatter_field(content, "plan") == "03"
        assert _extract_frontmatter_field(content, "type") == "execute"

    def test_extract_frontmatter_field_missing(self):
        """Returns None for missing fields."""
        content = "---\nphase: 01\n---\n"
        assert _extract_frontmatter_field(content, "plan") is None

    def test_extract_objective(self):
        """Extracts text from <objective> tags."""
        content = "<objective>\nBuild the plan review UI.\n</objective>"
        assert _extract_objective(content) == "Build the plan review UI."

    def test_extract_objective_missing(self):
        """Returns default when no objective tags."""
        assert _extract_objective("no objective here") == "No objective found"

    def test_extract_objective_truncates(self):
        """Objective text is truncated to 500 characters."""
        long_text = "A" * 600
        content = f"<objective>{long_text}</objective>"
        result = _extract_objective(content)
        assert len(result) == 500


# ---------------------------------------------------------------------------
# PlanReviewCog tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    """Create a mock VcoBot with required attributes."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot._ready_flag = True
    bot.is_bot_ready = True
    bot._guild_id = 123456
    bot.loop = asyncio.new_event_loop()
    bot.project_dir = Path("/tmp/test-project")
    bot.agent_manager = None
    bot.monitor_loop = None
    yield bot
    bot.loop.close()


@pytest.fixture
def cog(mock_bot):
    """Create a PlanReviewCog with mock bot."""
    return PlanReviewCog(mock_bot)


@pytest.fixture
def mock_plan_review_channel():
    """Create a mock #plan-review text channel."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "plan-review"
    return channel


@pytest.fixture
def mock_alerts_channel():
    """Create a mock #alerts text channel."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "alerts"
    return channel


class TestGateStateTransitions:
    """Tests for _update_gate_state state machine."""

    def test_idle_to_awaiting_review(self, cog, mock_bot):
        """Setting awaiting_review adds plan to pending and updates status."""
        state = AgentMonitorState(agent_id="agent-1")
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}

        cog._update_gate_state("agent-1", "/plans/01-01-PLAN.md", status="awaiting_review")

        assert state.plan_gate_status == "awaiting_review"
        assert "/plans/01-01-PLAN.md" in state.pending_plans

    def test_awaiting_to_approved(self, cog, mock_bot):
        """Approving moves plan from pending to approved."""
        state = AgentMonitorState(
            agent_id="agent-1",
            plan_gate_status="awaiting_review",
            pending_plans=["/plans/01-01-PLAN.md"],
        )
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}

        cog._update_gate_state("agent-1", "/plans/01-01-PLAN.md", status="approved")

        assert state.plan_gate_status == "approved"
        assert "/plans/01-01-PLAN.md" not in state.pending_plans
        assert "/plans/01-01-PLAN.md" in state.approved_plans

    def test_awaiting_to_rejected(self, cog, mock_bot):
        """Rejecting removes plan from pending."""
        state = AgentMonitorState(
            agent_id="agent-1",
            plan_gate_status="awaiting_review",
            pending_plans=["/plans/01-01-PLAN.md"],
        )
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}

        cog._update_gate_state("agent-1", "/plans/01-01-PLAN.md", status="rejected")

        assert state.plan_gate_status == "rejected"
        assert "/plans/01-01-PLAN.md" not in state.pending_plans
        assert "/plans/01-01-PLAN.md" not in state.approved_plans

    def test_no_state_does_not_raise(self, cog, mock_bot):
        """When no monitor_loop or unknown agent, update is a no-op."""
        mock_bot.monitor_loop = None
        cog._update_gate_state("unknown", "/plans/PLAN.md", status="approved")
        # Should not raise


class TestPlanReviewCogHandlers:
    """Tests for handle_new_plan, _handle_approval, _handle_rejection."""

    @pytest.mark.asyncio
    async def test_handle_new_plan_posts_embed(self, cog, mock_bot, mock_plan_review_channel, tmp_path):
        """handle_new_plan reads plan, validates safety, posts embed with file."""
        plan_file = tmp_path / "05-03-PLAN.md"
        plan_content = (
            "---\nphase: 05\nplan: 03\n---\n"
            "<objective>Test plan goal</objective>\n"
            '<task type="auto">\n</task>\n'
            "## Interaction Safety\n"
            "| Agent/Component | Circumstance | Action | Concurrent With | Safe? | Mitigation |\n"
            "|---|---|---|---|---|---|\n"
            "| A | B | C | D | Yes | None |\n"
        )
        plan_file.write_text(plan_content)

        cog._plan_review_channel = mock_plan_review_channel

        # Mock the view wait to return immediately (approved)
        with patch("vcompany.bot.cogs.plan_review.PlanReviewView") as MockView:
            mock_view = MagicMock()
            mock_view.wait = AsyncMock(return_value=False)
            mock_view.result = "approved"
            mock_view.feedback = ""
            MockView.return_value = mock_view

            # Mock _handle_approval
            cog._handle_approval = AsyncMock()

            await cog.handle_new_plan("agent-1", plan_file)

        mock_plan_review_channel.send.assert_awaited_once()
        call_kwargs = mock_plan_review_channel.send.call_args.kwargs
        assert "embed" in call_kwargs
        assert "view" in call_kwargs
        assert "file" in call_kwargs

    @pytest.mark.asyncio
    async def test_handle_approval_updates_state(self, cog, mock_bot, mock_plan_review_channel):
        """Approval updates gate state and posts confirmation."""
        state = AgentMonitorState(
            agent_id="agent-1",
            plan_gate_status="awaiting_review",
            pending_plans=["/plans/01-01-PLAN.md"],
        )
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}
        cog._plan_review_channel = mock_plan_review_channel

        await cog._handle_approval("agent-1", "/plans/01-01-PLAN.md")

        assert state.plan_gate_status == "approved"
        assert "/plans/01-01-PLAN.md" in state.approved_plans
        mock_plan_review_channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_rejection_sends_feedback(self, cog, mock_bot, mock_plan_review_channel, tmp_path):
        """Rejection calls tmux.send_command with feedback text."""
        state = AgentMonitorState(
            agent_id="agent-1",
            plan_gate_status="awaiting_review",
            pending_plans=["/plans/01-01-PLAN.md"],
        )
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}
        cog._plan_review_channel = mock_plan_review_channel

        # No agent_manager -> feedback still posted to channel
        mock_bot.agent_manager = None

        await cog._handle_rejection("agent-1", "/plans/01-01-PLAN.md", "Needs more tests")

        assert state.plan_gate_status == "rejected"
        mock_plan_review_channel.send.assert_awaited_once()
        sent_text = mock_plan_review_channel.send.call_args[0][0]
        assert "rejected" in sent_text
        assert "Needs more tests" in sent_text

    @pytest.mark.asyncio
    async def test_all_plans_approved_triggers_execution(self, cog, mock_bot, mock_plan_review_channel, mock_alerts_channel):
        """When pending_plans empties, _trigger_execution is called."""
        state = AgentMonitorState(
            agent_id="agent-1",
            plan_gate_status="awaiting_review",
            pending_plans=["/plans/01-01-PLAN.md"],
        )
        mock_bot.monitor_loop = MagicMock()
        mock_bot.monitor_loop._agent_states = {"agent-1": state}
        cog._plan_review_channel = mock_plan_review_channel
        cog._alerts_channel = mock_alerts_channel

        # Mock _trigger_execution to verify it's called
        cog._trigger_execution = AsyncMock()

        await cog._handle_approval("agent-1", "/plans/01-01-PLAN.md")

        # pending_plans should be empty after approval -> trigger called
        cog._trigger_execution.assert_awaited_once_with("agent-1", state)

    @pytest.mark.asyncio
    async def test_handle_new_plan_no_channel_returns(self, cog, mock_bot):
        """handle_new_plan returns early when no #plan-review channel."""
        cog._plan_review_channel = None
        cog._resolve_channels = AsyncMock()  # still returns None

        await cog.handle_new_plan("agent-1", Path("/fake/PLAN.md"))
        # Should not raise, just return


class TestMakeSyncCallback:
    """Tests for make_sync_callback."""

    def test_returns_on_plan_detected_callback(self, cog):
        """make_sync_callback returns dict with on_plan_detected key."""
        callbacks = cog.make_sync_callback()
        assert "on_plan_detected" in callbacks
        assert callable(callbacks["on_plan_detected"])

    def test_callback_schedules_coroutine(self, cog):
        """Sync callback should call run_coroutine_threadsafe."""
        callbacks = cog.make_sync_callback()

        with patch("asyncio.run_coroutine_threadsafe") as mock_rct:
            callbacks["on_plan_detected"]("test-agent", Path("/plans/PLAN.md"))
            mock_rct.assert_called_once()
            assert mock_rct.call_args[0][1] is cog.bot.loop


@pytest.mark.asyncio
async def test_on_ready_resolves_channels(cog):
    """on_ready calls _resolve_channels."""
    cog._resolve_channels = AsyncMock()
    await cog.on_ready()
    cog._resolve_channels.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_channels(cog):
    """_resolve_channels finds #plan-review and #alerts channels."""
    plan_ch = MagicMock(spec=discord.TextChannel)
    plan_ch.name = "plan-review"
    alerts_ch = MagicMock(spec=discord.TextChannel)
    alerts_ch.name = "alerts"
    other_ch = MagicMock(spec=discord.TextChannel)
    other_ch.name = "general"

    guild = MagicMock()
    guild.text_channels = [other_ch, plan_ch, alerts_ch]
    cog.bot.get_guild.return_value = guild

    await cog._resolve_channels()

    assert cog._plan_review_channel is plan_ch
    assert cog._alerts_channel is alerts_ch
