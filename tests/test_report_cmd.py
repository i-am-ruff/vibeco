"""Tests for vco report command -- direct Discord HTTP API posting."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vcompany.cli.report_cmd import _channel_cache, report


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the module-level channel cache between tests."""
    _channel_cache.clear()
    yield
    _channel_cache.clear()


@pytest.fixture
def env_vars(monkeypatch):
    """Set required env vars for report command."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("DISCORD_GUILD_ID", "999888777")
    monkeypatch.setenv("AGENT_ID", "frontend")


def _mock_channels_response():
    """Build a mock channels list response."""
    return [
        {"id": "111", "name": "general", "type": 0},
        {"id": "222", "name": "agent-frontend", "type": 0},
        {"id": "333", "name": "agent-backend", "type": 0},
    ]


class TestReportHappyPath:
    """Test successful report posting to Discord."""

    def test_posts_to_correct_channel(self, env_vars):
        """Report finds #agent-frontend and posts message."""
        runner = CliRunner()

        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = _mock_channels_response()
        mock_get_resp.raise_for_status = MagicMock()

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()

        with patch("vcompany.cli.report_cmd.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_get_resp
            mock_httpx.post.return_value = mock_post_resp

            result = runner.invoke(report, ["starting", "phase", "1"])

        assert result.exit_code == 0
        assert "Reported: frontend: starting phase 1" in result.output

        # Verify GET was called for channel lookup
        mock_httpx.get.assert_called_once()
        call_args = mock_httpx.get.call_args
        assert "guilds/999888777/channels" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bot test-token-123"

        # Verify POST was called with correct channel
        mock_httpx.post.assert_called_once()
        post_args = mock_httpx.post.call_args
        assert "channels/222/messages" in post_args[0][0]
        assert "frontend:" in post_args[1]["json"]["content"]


class TestChannelCaching:
    """Test that channel lookup is cached after first call."""

    def test_second_call_skips_channel_lookup(self, env_vars):
        """Second report should use cached channel_id, not re-fetch."""
        runner = CliRunner()

        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = _mock_channels_response()
        mock_get_resp.raise_for_status = MagicMock()

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()

        with patch("vcompany.cli.report_cmd.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_get_resp
            mock_httpx.post.return_value = mock_post_resp

            # First call
            runner.invoke(report, ["first", "message"])
            # Second call
            runner.invoke(report, ["second", "message"])

        # GET should only be called once (cached on second call)
        assert mock_httpx.get.call_count == 1
        # POST should be called twice
        assert mock_httpx.post.call_count == 2


class TestErrorFallback:
    """Test graceful fallback when Discord API fails."""

    def test_channel_lookup_failure_prints_to_stderr(self, env_vars):
        """When channel lookup fails, prints warning but doesn't crash."""
        runner = CliRunner()

        with patch("vcompany.cli.report_cmd.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Connection refused")

            result = runner.invoke(report, ["test", "message"])

        assert result.exit_code == 0
        assert "Warning: Could not find #agent-frontend channel" in result.output

    def test_post_failure_prints_to_stderr(self, env_vars):
        """When message post fails, prints warning but doesn't crash."""
        runner = CliRunner()

        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = _mock_channels_response()
        mock_get_resp.raise_for_status = MagicMock()

        with patch("vcompany.cli.report_cmd.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_get_resp
            mock_httpx.post.side_effect = Exception("Rate limited")

            result = runner.invoke(report, ["test", "message"])

        assert result.exit_code == 0
        assert "Warning: Failed to post to Discord" in result.output


class TestMissingEnvVars:
    """Test behavior when required env vars are missing."""

    def test_missing_bot_token(self, monkeypatch):
        """Exits with error when DISCORD_BOT_TOKEN is missing."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "123")
        monkeypatch.setenv("AGENT_ID", "frontend")
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

        runner = CliRunner()
        result = runner.invoke(report, ["test"])
        assert result.exit_code == 1

    def test_missing_guild_id(self, monkeypatch):
        """Exits with error when DISCORD_GUILD_ID is missing."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
        monkeypatch.setenv("AGENT_ID", "frontend")
        monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)

        runner = CliRunner()
        result = runner.invoke(report, ["test"])
        assert result.exit_code == 1

    def test_missing_agent_id(self, monkeypatch):
        """Exits with error when AGENT_ID is missing."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
        monkeypatch.setenv("DISCORD_GUILD_ID", "123")
        monkeypatch.delenv("AGENT_ID", raising=False)

        runner = CliRunner()
        result = runner.invoke(report, ["test"])
        assert result.exit_code == 1
