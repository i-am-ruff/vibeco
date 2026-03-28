"""Tests for ConflictResolver.

TDD RED phase: these tests define the expected behavior.
Note: AgentManager.dispatch_fix tests removed during MIGR-03 (v1 module deletion).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.integration.conflict_resolver import ConflictResolver


# ── ConflictResolver tests ────────────────────────────────────────────


@pytest.fixture
def mock_pm():
    """Create a mock PMTier that returns resolved content."""
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock()
    pm._answer_directly = AsyncMock()
    return pm


@pytest.fixture
def conflict_file(tmp_path: Path) -> Path:
    """Create a file with git conflict markers."""
    content = textwrap.dedent("""\
        line 1
        line 2
        line 3
        line 4
        line 5
        line 6
        line 7
        line 8
        line 9
        line 10
        <<<<<<< HEAD
        our change here
        =======
        their change here
        >>>>>>> feature-branch
        line after conflict
        line 17
        line 18
        line 19
        line 20
        line 21
    """)
    f = tmp_path / "conflicted.py"
    f.write_text(content)
    return f


@pytest.fixture
def no_conflict_file(tmp_path: Path) -> Path:
    """Create a file without conflict markers."""
    f = tmp_path / "clean.py"
    f.write_text("line 1\nline 2\nline 3\n")
    return f


@pytest.mark.asyncio
async def test_resolve_small_conflict_calls_pm(mock_pm, conflict_file, tmp_path):
    """ConflictResolver.resolve() with small conflict calls PMTier and returns resolved content."""
    mock_pm._answer_directly = AsyncMock(return_value="resolved line here")
    resolver = ConflictResolver(pm=mock_pm)

    result = await resolver.resolve(conflict_file, tmp_path)

    assert result is not None
    assert "resolved line here" in result
    # PM should have been called
    mock_pm._answer_directly.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_low_confidence_returns_none(mock_pm, conflict_file, tmp_path):
    """ConflictResolver.resolve() with PM low confidence returns None (escalation needed)."""
    mock_pm._answer_directly = AsyncMock(return_value="unsure about this conflict")
    resolver = ConflictResolver(pm=mock_pm)

    result = await resolver.resolve(conflict_file, tmp_path)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_no_pm_returns_none(conflict_file, tmp_path):
    """ConflictResolver.resolve() with no PM configured returns None immediately."""
    resolver = ConflictResolver(pm=None)

    result = await resolver.resolve(conflict_file, tmp_path)

    assert result is None


def test_extract_conflict_hunks_parses_markers(conflict_file, tmp_path):
    """ConflictResolver._extract_conflict_hunks() parses git conflict markers correctly."""
    resolver = ConflictResolver()

    hunks = resolver._extract_conflict_hunks(conflict_file, tmp_path)

    assert len(hunks) == 1
    assert "<<<<<<< HEAD" in hunks[0]
    assert "=======" in hunks[0]
    assert ">>>>>>> feature-branch" in hunks[0]
    assert "our change here" in hunks[0]
    assert "their change here" in hunks[0]


def test_extract_conflict_hunks_includes_context(conflict_file, tmp_path):
    """ConflictResolver._extract_conflict_hunks() extracts surrounding context (10-20 lines) per Pitfall 6."""
    resolver = ConflictResolver()

    hunks = resolver._extract_conflict_hunks(conflict_file, tmp_path)

    assert len(hunks) == 1
    # Context lines before the conflict should be included
    assert "line 1" in hunks[0]
    # Context lines after the conflict should be included
    assert "line after conflict" in hunks[0]


def test_extract_no_conflicts(no_conflict_file, tmp_path):
    """_extract_conflict_hunks returns empty list for clean file."""
    resolver = ConflictResolver()

    hunks = resolver._extract_conflict_hunks(no_conflict_file, tmp_path)

    assert hunks == []


@pytest.mark.asyncio
async def test_resolve_all_multiple_files(mock_pm, conflict_file, no_conflict_file, tmp_path):
    """resolve_all tries to resolve all conflicting files."""
    mock_pm._answer_directly = AsyncMock(return_value="resolved content")
    resolver = ConflictResolver(pm=mock_pm)

    results = await resolver.resolve_all(
        [str(conflict_file.name), str(no_conflict_file.name)],
        tmp_path,
    )

    assert isinstance(results, dict)
    assert len(results) == 2
