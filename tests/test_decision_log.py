"""Tests for DecisionLogger: dual storage to #decisions channel + JSONL file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.strategist.decision_log import DecisionLogger
from vcompany.strategist.models import DecisionLogEntry


def _make_entry(
    *,
    decided_by: str = "PM",
    confidence: str = "HIGH",
    agent_id: str = "agent-alpha",
    question: str = "Should we use REST or GraphQL?",
    decision: str = "Use REST for v1 simplicity.",
) -> DecisionLogEntry:
    return DecisionLogEntry(
        timestamp=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
        question_or_plan=question,
        decision=decision,
        confidence_level=confidence,
        decided_by=decided_by,
        agent_id=agent_id,
    )


@pytest.mark.asyncio
async def test_log_decision_appends_to_jsonl(tmp_path: Path) -> None:
    """log_decision appends entry to decisions.jsonl as JSON line."""
    jsonl_path = tmp_path / "state" / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path)

    entry = _make_entry()
    await logger.log_decision(entry)

    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["decided_by"] == "PM"
    assert data["decision"] == "Use REST for v1 simplicity."


@pytest.mark.asyncio
async def test_log_decision_posts_embed_to_channel(tmp_path: Path) -> None:
    """log_decision posts compact embed to #decisions channel."""
    jsonl_path = tmp_path / "decisions.jsonl"
    channel = AsyncMock(spec=discord.TextChannel)

    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=channel)
    entry = _make_entry()
    await logger.log_decision(entry)

    channel.send.assert_awaited_once()
    call_kwargs = channel.send.call_args
    embed = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
    assert isinstance(embed, discord.Embed)


@pytest.mark.asyncio
async def test_multiple_log_calls_produce_multiple_lines(tmp_path: Path) -> None:
    """Multiple log_decision calls produce multiple JSONL lines (append-only)."""
    jsonl_path = tmp_path / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path)

    await logger.log_decision(_make_entry(decided_by="PM"))
    await logger.log_decision(_make_entry(decided_by="Strategist"))
    await logger.log_decision(_make_entry(decided_by="Owner"))

    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 3
    assert json.loads(lines[0])["decided_by"] == "PM"
    assert json.loads(lines[1])["decided_by"] == "Strategist"
    assert json.loads(lines[2])["decided_by"] == "Owner"


@pytest.mark.asyncio
async def test_embed_includes_required_fields(tmp_path: Path) -> None:
    """Embed includes timestamp, decided_by, confidence_level, and truncated decision text."""
    jsonl_path = tmp_path / "decisions.jsonl"
    channel = AsyncMock(spec=discord.TextChannel)
    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=channel)

    entry = _make_entry(confidence="MEDIUM", decided_by="Strategist")
    await logger.log_decision(entry)

    embed: discord.Embed = channel.send.call_args.kwargs["embed"]
    # Check title includes decided_by
    assert "Strategist" in embed.title
    # Check fields contain agent and confidence
    field_names = [f.name for f in embed.fields]
    assert "Agent" in field_names
    assert "Confidence" in field_names


@pytest.mark.asyncio
async def test_missing_channel_gracefully_skipped(tmp_path: Path) -> None:
    """Missing #decisions channel gracefully skipped (no crash)."""
    jsonl_path = tmp_path / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=None)

    entry = _make_entry()
    # Should not raise
    await logger.log_decision(entry)

    # File should still be written
    assert jsonl_path.exists()


@pytest.mark.asyncio
async def test_file_write_uses_append_mode(tmp_path: Path) -> None:
    """File write uses append mode, not overwrite."""
    jsonl_path = tmp_path / "decisions.jsonl"
    # Pre-populate with existing content
    jsonl_path.write_text('{"existing": true}\n')

    logger = DecisionLogger(decisions_path=jsonl_path)
    await logger.log_decision(_make_entry())

    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"existing": True}
    assert json.loads(lines[1])["decided_by"] == "PM"


@pytest.mark.asyncio
async def test_load_decisions_reads_all_entries(tmp_path: Path) -> None:
    """load_decisions reads all entries from decisions.jsonl."""
    jsonl_path = tmp_path / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path)

    await logger.log_decision(_make_entry(decided_by="PM"))
    await logger.log_decision(_make_entry(decided_by="Owner"))

    entries = logger.load_decisions()
    assert len(entries) == 2
    assert entries[0].decided_by == "PM"
    assert entries[1].decided_by == "Owner"


@pytest.mark.asyncio
async def test_load_decisions_skips_malformed_lines(tmp_path: Path) -> None:
    """load_decisions skips malformed lines with warning."""
    jsonl_path = tmp_path / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path)

    # Write valid + malformed lines
    await logger.log_decision(_make_entry())
    with open(jsonl_path, "a") as f:
        f.write("not valid json\n")
    await logger.log_decision(_make_entry(decided_by="Owner"))

    entries = logger.load_decisions()
    assert len(entries) == 2
    assert entries[0].decided_by == "PM"
    assert entries[1].decided_by == "Owner"


@pytest.mark.asyncio
async def test_load_decisions_empty_file(tmp_path: Path) -> None:
    """load_decisions returns empty list for non-existent file."""
    jsonl_path = tmp_path / "decisions.jsonl"
    logger = DecisionLogger(decisions_path=jsonl_path)

    entries = logger.load_decisions()
    assert entries == []


@pytest.mark.asyncio
async def test_embed_color_by_confidence(tmp_path: Path) -> None:
    """Embed color varies by confidence level: green HIGH, yellow MEDIUM, red LOW."""
    jsonl_path = tmp_path / "decisions.jsonl"
    channel = AsyncMock(spec=discord.TextChannel)
    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=channel)

    for confidence, expected_color in [
        ("HIGH", discord.Colour.green()),
        ("MEDIUM", discord.Colour.yellow()),
        ("LOW", discord.Colour.red()),
    ]:
        channel.reset_mock()
        await logger.log_decision(_make_entry(confidence=confidence))
        embed: discord.Embed = channel.send.call_args.kwargs["embed"]
        assert embed.colour == expected_color, f"Expected {expected_color} for {confidence}"


@pytest.mark.asyncio
async def test_embed_decision_truncated(tmp_path: Path) -> None:
    """Decision text in embed is truncated to 200 chars."""
    jsonl_path = tmp_path / "decisions.jsonl"
    channel = AsyncMock(spec=discord.TextChannel)
    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=channel)

    long_decision = "A" * 300
    await logger.log_decision(_make_entry(decision=long_decision))

    embed: discord.Embed = channel.send.call_args.kwargs["embed"]
    # Find the Decision field
    decision_field = next(f for f in embed.fields if f.name == "Decision")
    assert len(decision_field.value) <= 203  # 200 + "..."


@pytest.mark.asyncio
async def test_channel_error_does_not_crash(tmp_path: Path) -> None:
    """Channel send error is caught and logged, not raised."""
    jsonl_path = tmp_path / "decisions.jsonl"
    channel = AsyncMock(spec=discord.TextChannel)
    channel.send.side_effect = discord.HTTPException(MagicMock(), "rate limited")

    logger = DecisionLogger(decisions_path=jsonl_path, decisions_channel=channel)
    # Should not raise
    await logger.log_decision(_make_entry())

    # File should still be written
    assert jsonl_path.exists()
