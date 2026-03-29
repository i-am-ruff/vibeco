"""Tests for RuntimeAPI gateway (EXTRACT-02, EXTRACT-04).

Verifies RuntimeAPI methods using a mock CompanyRoot and NoopCommunicationPort.
"""

from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vcompany.daemon.comm import NoopCommunicationPort
from vcompany.daemon.runtime_api import RuntimeAPI


@pytest.fixture
def mock_company_root():
    root = AsyncMock()
    root.projects = {}
    root._company_agents = {}
    # health_tree is a sync method on CompanyRoot, so use MagicMock behavior
    health_result = MagicMock()
    health_result.model_dump.return_value = {"supervisor_id": "company-root"}
    root.health_tree = MagicMock(return_value=health_result)
    # hire returns a mock container with context.agent_id
    hired = MagicMock()
    hired.context.agent_id = "test-agent"
    root.hire.return_value = hired
    root._find_container = AsyncMock(return_value=AsyncMock())
    root.dismiss = AsyncMock()
    return root


@pytest.fixture
def runtime_api(mock_company_root):
    noop = NoopCommunicationPort()
    api = RuntimeAPI(mock_company_root, lambda: noop)
    return api


@pytest.mark.asyncio
async def test_hire(runtime_api, mock_company_root):
    result = await runtime_api.hire("test-agent")
    assert result == "test-agent"
    mock_company_root.hire.assert_awaited_once()


@pytest.mark.asyncio
async def test_give_task(runtime_api, mock_company_root):
    await runtime_api.give_task("agent-1", "do something")
    mock_company_root._find_container.assert_awaited_once_with("agent-1")


@pytest.mark.asyncio
async def test_dismiss(runtime_api, mock_company_root):
    await runtime_api.dismiss("agent-1")
    mock_company_root.dismiss.assert_awaited_once_with("agent-1")


@pytest.mark.asyncio
async def test_status(runtime_api):
    result = await runtime_api.status()
    assert "projects" in result
    assert "company_agents" in result


@pytest.mark.asyncio
async def test_health_tree(runtime_api, mock_company_root):
    result = await runtime_api.health_tree()
    assert "supervisor_id" in result


def test_register_channels(runtime_api):
    runtime_api.register_channels({"alerts": "123", "strategist": "456"})
    assert runtime_api.get_channel_id("alerts") == "123"
    assert runtime_api.get_channel_id("strategist") == "456"
    assert runtime_api.get_channel_id("nonexistent") is None


@pytest.mark.asyncio
async def test_relay_strategist_message(runtime_api):
    """COMM-04 receive path: relay_strategist_message reaches strategist container."""
    mock_container = AsyncMock()
    runtime_api._strategist_container = mock_container
    await runtime_api.relay_strategist_message("hello", "ch-123", "user1")
    mock_container.post_event.assert_awaited_once()
    event = mock_container.post_event.call_args[0][0]
    assert event["type"] == "user_message"
    assert event["content"] == "hello"


@pytest.mark.asyncio
async def test_relay_strategist_message_no_container(runtime_api):
    """relay_strategist_message logs warning when no strategist container."""
    runtime_api._strategist_container = None
    # Should not raise
    await runtime_api.relay_strategist_message("hello", "ch-123", "user1")


@pytest.mark.asyncio
async def test_handle_plan_approval(runtime_api, mock_company_root):
    """COMM-05 receive path: handle_plan_approval routes through RuntimeAPI."""
    runtime_api.register_channels({"plan-review": "789"})
    await runtime_api.handle_plan_approval("agent-1", "/path/to/plan.md")
    # Should have sent a message to plan-review channel
    # (NoopCommunicationPort silently succeeds)


@pytest.mark.asyncio
async def test_handle_plan_rejection(runtime_api, mock_company_root):
    """COMM-05 receive path: handle_plan_rejection routes through RuntimeAPI."""
    runtime_api.register_channels({"plan-review": "789"})
    await runtime_api.handle_plan_rejection(
        "agent-1", "/path/to/plan.md", "needs revision"
    )


def test_no_discord_imports():
    """RuntimeAPI must not import discord."""
    import vcompany.daemon.runtime_api as mod

    source_file = mod.__file__
    with open(source_file) as f:
        content = f.read()
    assert "import discord" not in content, "runtime_api.py must not import discord"
