"""Tests for checkin data gathering and posting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.communication.checkin import CheckinData, gather_checkin_data, post_checkin
from vcompany.git.ops import GitResult


class TestGatherCheckinData:
    """Tests for gather_checkin_data."""

    def test_commit_count_from_git_log(self, tmp_path: Path) -> None:
        """gather_checkin_data returns commit_count from git log --oneline count."""
        log_output = "abc1234 feat: add X\ndef5678 fix: fix Y\nghi9012 chore: update Z"
        mock_result = GitResult(success=True, stdout=log_output, stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        assert data.commit_count == 3

    def test_summary_from_git_log(self, tmp_path: Path) -> None:
        """gather_checkin_data returns summary from git log --oneline (last 10 commits)."""
        commits = [f"hash{i} commit message {i}" for i in range(15)]
        log_output = "\n".join(commits)
        mock_result = GitResult(success=True, stdout=log_output, stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        # Only first 10 commits in summary
        assert data.summary.count("\n") == 9  # 10 lines = 9 newlines
        assert "hash0" in data.summary
        assert "hash9" in data.summary
        assert "hash10" not in data.summary

    def test_next_phase_from_roadmap(self, tmp_path: Path) -> None:
        """gather_checkin_data reads .planning/ROADMAP.md to determine next phase."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        roadmap = planning / "ROADMAP.md"
        roadmap.write_text(
            "# Roadmap\n\n"
            "| Phase | Name | Status |\n"
            "|-------|------|--------|\n"
            "| 01 | Foundation | Complete |\n"
            "| 02 | Lifecycle | Complete |\n"
            "| 03 | Monitor | In Progress |\n"
            "| 04 | Discord | Planned |\n"
        )
        mock_result = GitResult(success=True, stdout="abc fix", stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        assert data.next_phase == "04"

    def test_gaps_from_state_blockers(self, tmp_path: Path) -> None:
        """gather_checkin_data reads .planning/STATE.md for gaps/notes from Blockers section."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        state = planning / "STATE.md"
        state.write_text(
            "# State\n\n"
            "## Blockers/Concerns\n\n"
            "- libtmux API stability unknown\n"
            "- GSD resume-work needs testing\n\n"
            "## Other\n"
        )
        mock_result = GitResult(success=True, stdout="", stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        assert "libtmux API stability" in data.gaps
        assert "GSD resume-work" in data.gaps

    def test_dependency_status_from_roadmap(self, tmp_path: Path) -> None:
        """gather_checkin_data reads .planning/ROADMAP.md dependency chain for dependency_status."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        roadmap = planning / "ROADMAP.md"
        roadmap.write_text(
            "# Roadmap\n\n"
            "| Phase | Name | Status | Depends on |\n"
            "|-------|------|--------|------------|\n"
            "| 01 | Foundation | Complete | - |\n"
            "| 02 | Lifecycle | Complete | 01 |\n"
            "| 03 | Monitor | In Progress | 02 |\n"
            "| 04 | Discord | Planned | 03 |\n"
        )
        mock_result = GitResult(success=True, stdout="abc fix", stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        # Next phase is 04, depends on 03
        assert "03" in data.dependency_status

    def test_missing_roadmap_returns_unknown(self, tmp_path: Path) -> None:
        """gather_checkin_data handles missing ROADMAP.md gracefully (returns 'unknown')."""
        mock_result = GitResult(success=True, stdout="", stderr="", returncode=0)

        with patch("vcompany.communication.checkin.git_ops") as mock_git:
            mock_git.log.return_value = mock_result
            data = gather_checkin_data("agent-01", tmp_path)

        assert data.next_phase == "unknown"

    @pytest.mark.asyncio
    async def test_post_checkin_sends_embed(self) -> None:
        """post_checkin sends embed to the correct channel."""
        checkin = CheckinData(
            agent_id="agent-01",
            commit_count=5,
            summary="abc feat: something",
            gaps="",
            next_phase="04",
            dependency_status="Depends on 03",
        )
        mock_channel = AsyncMock()

        with patch("vcompany.communication.checkin.build_checkin_embed") as mock_build:
            mock_embed = MagicMock()
            mock_build.return_value = mock_embed
            await post_checkin(checkin, mock_channel)

        mock_build.assert_called_once_with(checkin)
        mock_channel.send.assert_awaited_once_with(embed=mock_embed)
