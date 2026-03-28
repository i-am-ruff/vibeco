"""Tests for health embed building and HealthCog behavior (HLTH-03, HLTH-04)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.container.health import (
    CompanyHealthTree,
    HealthNode,
    HealthReport,
    HealthTree,
)
from vcompany.bot.embeds import STATE_INDICATORS, build_health_tree_embed
from vcompany.resilience.message_queue import MessagePriority


def _make_report(
    agent_id: str = "agent-1",
    state: str = "running",
    inner_state: str | None = None,
    error_count: int = 0,
) -> HealthReport:
    """Create a HealthReport for testing."""
    now = datetime.now(timezone.utc)
    return HealthReport(
        agent_id=agent_id,
        state=state,
        inner_state=inner_state,
        uptime=100.0,
        last_heartbeat=now,
        error_count=error_count,
        last_activity=now,
    )


def _make_tree(
    projects: list[HealthTree] | None = None,
    state: str = "running",
) -> CompanyHealthTree:
    """Create a CompanyHealthTree for testing."""
    return CompanyHealthTree(
        supervisor_id="company-root",
        state=state,
        projects=projects or [],
    )


def _make_project(
    supervisor_id: str = "project-alpha",
    state: str = "running",
    agents: list[tuple[str, str, str | None]] | None = None,
) -> HealthTree:
    """Create a HealthTree for a project.

    agents: list of (agent_id, state, inner_state) tuples.
    """
    children = []
    if agents:
        for aid, st, inner in agents:
            children.append(HealthNode(report=_make_report(aid, st, inner)))
    return HealthTree(
        supervisor_id=supervisor_id,
        state=state,
        children=children,
    )


class TestHealthEmbed:
    """Tests for build_health_tree_embed with various tree shapes."""

    def test_embed_has_health_tree_title(self):
        """Embed title is 'Health Tree'."""
        tree = _make_tree()
        embed = build_health_tree_embed(tree)
        assert embed.title == "Health Tree"

    def test_embed_one_field_per_project(self):
        """Each project gets its own embed field."""
        projects = [
            _make_project("project-alpha", agents=[("a1", "running", None)]),
            _make_project("project-beta", agents=[("b1", "running", None)]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        assert len(embed.fields) == 2
        field_names = [f.name for f in embed.fields]
        assert "Project: project-alpha" in field_names
        assert "Project: project-beta" in field_names

    def test_agent_line_has_correct_state_emoji(self):
        """Agent lines include the correct state emoji."""
        projects = [
            _make_project(agents=[("a1", "running", None)]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        field_value = embed.fields[0].value
        assert STATE_INDICATORS["running"] in field_value
        assert "**a1**" in field_value

    def test_inner_state_displayed_in_parentheses(self):
        """Inner state shown in parentheses when present."""
        projects = [
            _make_project(agents=[("a1", "running", "PLAN")]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        field_value = embed.fields[0].value
        assert "(PLAN)" in field_value

    def test_inner_state_absent_when_none(self):
        """No parentheses when inner_state is None."""
        projects = [
            _make_project(agents=[("a1", "running", None)]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        field_value = embed.fields[0].value
        assert "(" not in field_value

    def test_embed_color_green_when_all_running(self):
        """Embed color is green when all projects are running."""
        projects = [
            _make_project("p1", state="running"),
            _make_project("p2", state="running"),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        assert embed.color == discord.Color.green()

    def test_embed_color_red_when_any_errored(self):
        """Embed color is red when any project is not running."""
        projects = [
            _make_project("p1", state="running"),
            _make_project("p2", state="errored"),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        assert embed.color == discord.Color.red()

    def test_empty_projects_shows_description(self):
        """Empty projects list sets embed description (HLTH-05: root header preserved)."""
        tree = _make_tree(projects=[])
        embed = build_health_tree_embed(tree)
        assert "No projects active" in embed.description
        assert "company-root" in embed.description
        assert len(embed.fields) == 0

    def test_project_with_no_children(self):
        """Project with no children shows 'No agents' in field value."""
        projects = [_make_project(agents=[])]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        assert embed.fields[0].value == "No agents"

    def test_project_filter_returns_only_matching(self):
        """project_filter limits output to matching project."""
        projects = [
            _make_project("project-alpha", agents=[("a1", "running", None)]),
            _make_project("project-beta", agents=[("b1", "running", None)]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree, project_filter="project-alpha")
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "Project: project-alpha"

    def test_agent_filter_returns_only_matching(self):
        """agent_filter limits output to matching agent."""
        projects = [
            _make_project(
                "project-alpha",
                agents=[("a1", "running", None), ("a2", "errored", None)],
            ),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree, agent_filter="a1")
        field_value = embed.fields[0].value
        assert "**a1**" in field_value
        assert "**a2**" not in field_value


class TestEmbedLimits:
    """Tests for Discord embed field/char limits."""

    def test_25_field_limit(self):
        """Embed respects 25-field limit with truncation message."""
        projects = [
            _make_project(f"project-{i}", agents=[(f"a-{i}", "running", None)])
            for i in range(30)
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        assert len(embed.fields) <= 25
        # Last field should indicate truncation
        last_field = embed.fields[-1]
        assert "more" in last_field.name.lower() or "more" in last_field.value.lower()

    def test_1024_char_field_value_limit(self):
        """Field values are truncated to 1024 characters."""
        # Create a project with many agents to exceed 1024 chars
        agents = [(f"agent-with-long-name-{i:04d}", "running", "SOME_INNER_STATE") for i in range(100)]
        projects = [_make_project("big-project", agents=agents)]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        for field in embed.fields:
            assert len(field.value) <= 1024


class TestHealthEmbedIndicators:
    """Tests for state -> emoji mapping."""

    def test_running_indicator(self):
        """Running state maps to green circle."""
        assert STATE_INDICATORS["running"] == "\U0001f7e2"

    def test_sleeping_indicator(self):
        """Sleeping state maps to blue circle."""
        assert STATE_INDICATORS["sleeping"] == "\U0001f535"

    def test_errored_indicator(self):
        """Errored state maps to red circle."""
        assert STATE_INDICATORS["errored"] == "\U0001f534"

    def test_stopped_indicator(self):
        """Stopped state maps to black circle."""
        assert STATE_INDICATORS["stopped"] == "\u26ab"

    def test_creating_indicator(self):
        """Creating state maps to yellow circle."""
        assert STATE_INDICATORS["creating"] == "\U0001f7e1"

    def test_destroyed_indicator(self):
        """Destroyed state maps to black square."""
        assert STATE_INDICATORS["destroyed"] == "\u2b1b"

    def test_unknown_state_uses_default(self):
        """Unknown states use a fallback indicator."""
        projects = [
            _make_project(agents=[("a1", "unknown_state", None)]),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        # Should not raise, should use a fallback
        assert len(embed.fields) == 1


class TestNotifyStateChange:
    """Tests for HealthCog._notify_state_change behavior (queue-routed)."""

    @pytest.mark.asyncio
    async def test_notify_sends_for_errored(self):
        """_notify_state_change enqueues message for errored state."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        bot.guilds = []
        cog = HealthCog(bot)

        # Create mock guild with alerts channel
        mock_channel = AsyncMock()
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        bot.guilds = [mock_guild]

        report = _make_report("a1", "errored")
        await cog._notify_state_change(report)

        bot.message_queue.enqueue.assert_called_once()
        queued = bot.message_queue.enqueue.call_args[0][0]
        assert queued.priority == MessagePriority.STATUS
        assert queued.channel_id == 12345
        assert "a1" in queued.content
        assert "errored" in queued.content

    @pytest.mark.asyncio
    async def test_notify_sends_for_running(self):
        """_notify_state_change enqueues message for running state."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "running")
        await cog._notify_state_change(report)

        bot.message_queue.enqueue.assert_called_once()
        queued = bot.message_queue.enqueue.call_args[0][0]
        assert queued.priority == MessagePriority.STATUS

    @pytest.mark.asyncio
    async def test_notify_sends_for_stopped(self):
        """_notify_state_change enqueues message for stopped state."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "stopped")
        await cog._notify_state_change(report)

        bot.message_queue.enqueue.assert_called_once()
        queued = bot.message_queue.enqueue.call_args[0][0]
        assert queued.priority == MessagePriority.STATUS

    @pytest.mark.asyncio
    async def test_notify_skips_non_significant(self):
        """_notify_state_change does NOT enqueue for creating state."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "creating")
        await cog._notify_state_change(report)

        bot.message_queue.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_does_not_raise_on_failure(self):
        """_notify_state_change swallows exceptions to protect callback chain."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        bot.message_queue.enqueue.side_effect = RuntimeError("Queue error")
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "errored")
        # Should not raise
        await cog._notify_state_change(report)

    @pytest.mark.asyncio
    async def test_errored_state_reflected_in_health_embed(self):
        """When container health_report returns errored (tmux dead), embed reflects it."""
        # Build a tree with an errored agent (as would happen when tmux dies)
        projects = [
            _make_project(
                "project-alpha",
                agents=[("a1", "errored", None), ("a2", "running", None)],
            ),
        ]
        tree = _make_tree(projects=projects)
        embed = build_health_tree_embed(tree)
        field_value = embed.fields[0].value
        # Errored agent should show red circle indicator
        assert STATE_INDICATORS["errored"] in field_value
        assert "**a1**" in field_value
        # Running agent should show green circle
        assert STATE_INDICATORS["running"] in field_value
        assert "**a2**" in field_value

    @pytest.mark.asyncio
    async def test_notify_includes_inner_state(self):
        """_notify_state_change includes inner_state when present."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "running", inner_state="PLAN")
        await cog._notify_state_change(report)

        queued = bot.message_queue.enqueue.call_args[0][0]
        assert "PLAN" in queued.content

    @pytest.mark.asyncio
    async def test_notify_skips_when_queue_none(self):
        """_notify_state_change does nothing when message_queue is None."""
        from vcompany.bot.cogs.health import HealthCog

        bot = MagicMock()
        bot.message_queue = None
        mock_channel = AsyncMock()
        mock_channel.name = "alerts"
        mock_channel.id = 12345
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        cog = HealthCog(bot)
        report = _make_report("a1", "errored")
        # Should not raise
        await cog._notify_state_change(report)


# ── HLTH-05: CompanyRoot header in embed description ─────────────────


def test_embed_description_shows_company_root():
    """Embed description shows company-root state as tree root (HLTH-05)."""
    tree = _make_tree(state="running")
    embed = build_health_tree_embed(tree)
    assert embed.description is not None
    assert "company-root" in embed.description
    assert "running" in embed.description
    assert STATE_INDICATORS["running"] in embed.description


def test_embed_description_shows_company_root_non_running():
    """CompanyRoot header reflects non-running states (HLTH-05)."""
    tree = _make_tree(state="errored")
    embed = build_health_tree_embed(tree)
    assert "errored" in embed.description
    assert STATE_INDICATORS["errored"] in embed.description


def test_no_projects_preserves_root_header():
    """'No projects active' message preserves CompanyRoot header (HLTH-05)."""
    tree = _make_tree(projects=[], state="running")
    embed = build_health_tree_embed(tree)
    assert "company-root" in embed.description


# ── HLTH-06: Per-agent uptime and last_activity in lines ─────────────


def test_company_agent_line_shows_uptime_and_activity():
    """Company agent lines include uptime and last_activity (HLTH-06)."""
    tree = _make_tree()
    tree.company_agents = [HealthNode(report=_make_report(agent_id="strategist", state="running", inner_state="listening"))]
    embed = build_health_tree_embed(tree)
    field = embed.fields[0]
    assert "up " in field.value
    assert "active " in field.value
    assert "ago" in field.value


def test_project_agent_line_shows_uptime_and_activity():
    """Project agent lines include uptime and last_activity (HLTH-06)."""
    project = HealthTree(
        supervisor_id="project-alpha",
        state="running",
        children=[HealthNode(report=_make_report(agent_id="dev-1", state="running", inner_state="PLAN"))],
    )
    tree = _make_tree(projects=[project])
    embed = build_health_tree_embed(tree)
    # Find the project field
    project_field = [f for f in embed.fields if "project-alpha" in f.name][0]
    assert "up " in project_field.value
    assert "active " in project_field.value


# ── Helper function unit tests ────────────────────────────────────────


def test_fmt_uptime_hours():
    from vcompany.bot.embeds import _fmt_uptime
    assert _fmt_uptime(7380.0) == "up 2h 3m"


def test_fmt_uptime_minutes():
    from vcompany.bot.embeds import _fmt_uptime
    assert _fmt_uptime(300.0) == "up 5m"


def test_fmt_uptime_seconds():
    from vcompany.bot.embeds import _fmt_uptime
    assert _fmt_uptime(45.0) == "up 45s"
