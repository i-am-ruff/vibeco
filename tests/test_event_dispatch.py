"""Tests for GsdAgent -> PM event dispatch via WorkflowOrchestratorCog (AUTO-05)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from vcompany.bot.cogs.workflow_orchestrator_cog import WorkflowOrchestratorCog


def _make_cog_with_pm(*, pm_container=None, container=None):
    """Create a WorkflowOrchestratorCog with mocked bot, company_root, and PM."""
    bot = MagicMock()
    bot._guild_id = 99999
    bot.get_guild.return_value = None

    # PM container on bot
    bot._pm_container = pm_container

    # CompanyRoot with find_container
    mock_root = MagicMock()
    mock_root._find_container = AsyncMock(return_value=container)
    bot.company_root = mock_root

    cog = WorkflowOrchestratorCog(bot)
    cog.set_company_root(MagicMock(), Path("/tmp/test-project"))
    return cog


@pytest.mark.asyncio
async def test_phase_complete_routes_event_to_pm():
    """_handle_phase_complete calls post_event on PM with task_completed event when agent has assignment."""
    pm = MagicMock()
    pm.post_event = AsyncMock()

    container = MagicMock()
    container.get_assignment = AsyncMock(return_value={"item_id": "TASK-1"})
    container.make_completion_event = MagicMock(
        return_value={
            "type": "task_completed",
            "agent_id": "test-agent",
            "item_id": "TASK-1",
            "result": "success",
        }
    )

    cog = _make_cog_with_pm(pm_container=pm, container=container)
    await cog._handle_phase_complete("test-agent")

    pm.post_event.assert_awaited_once_with({
        "type": "task_completed",
        "agent_id": "test-agent",
        "item_id": "TASK-1",
        "result": "success",
    })


@pytest.mark.asyncio
async def test_phase_complete_no_crash_when_pm_none():
    """_handle_phase_complete does not crash when PM container is None."""
    cog = _make_cog_with_pm(pm_container=None, container=MagicMock())
    # Should not raise
    await cog._handle_phase_complete("test-agent")


@pytest.mark.asyncio
async def test_phase_complete_uses_agent_id_when_no_assignment():
    """_handle_phase_complete uses agent_id as item_id fallback when no assignment."""
    pm = MagicMock()
    pm.post_event = AsyncMock()

    container = MagicMock()
    container.get_assignment = AsyncMock(return_value=None)
    container.make_completion_event = MagicMock(
        return_value={
            "type": "task_completed",
            "agent_id": "test-agent",
            "item_id": "test-agent",
            "result": "success",
        }
    )

    cog = _make_cog_with_pm(pm_container=pm, container=container)
    await cog._handle_phase_complete("test-agent")

    # make_completion_event called with agent_id as fallback
    container.make_completion_event.assert_called_once_with("test-agent")
    pm.post_event.assert_awaited_once()
