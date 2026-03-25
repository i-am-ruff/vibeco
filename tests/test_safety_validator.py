"""Tests for safety table validator for PLAN.md files."""

import pytest

from vcompany.monitor.safety_validator import validate_safety_table


# ---------------------------------------------------------------------------
# Fixtures: plan content samples
# ---------------------------------------------------------------------------

VALID_PLAN = """\
---
phase: 01-setup
plan: 01
---

# Phase 1 Plan 1: Setup

## Tasks

- Task 1: Do something

## Interaction Safety

| Agent/Component | Circumstance | Action | Concurrent With | Safe? | Mitigation |
|-----------------|--------------|--------|-----------------|-------|------------|
| Monitor | Status check | Read git log | Agent commit | Yes | Read-only operation |
"""

VALID_PLAN_MULTIPLE_ROWS = """\
## Interaction Safety

| Agent/Component | Circumstance | Action | Concurrent With | Safe? | Mitigation |
|-----------------|--------------|--------|-----------------|-------|------------|
| Monitor | Status check | Read git log | Agent commit | Yes | Read-only |
| Agent A | Write config | File write | Agent B read | Yes | Lock file |
| Bot | Send message | Discord API | Monitor cycle | Yes | Independent |
"""

MISSING_HEADING = """\
---
phase: 01-setup
plan: 01
---

# Phase 1 Plan 1: Setup

## Tasks

- Task 1: Do something
"""

MISSING_COLUMNS = """\
## Interaction Safety

| Agent/Component | Circumstance | Action |
|-----------------|--------------|--------|
| Monitor | Status check | Read git log |
"""

NO_DATA_ROWS = """\
## Interaction Safety

| Agent/Component | Circumstance | Action | Concurrent With | Safe? | Mitigation |
|-----------------|--------------|--------|-----------------|-------|------------|
"""

PARTIAL_COLUMNS = """\
## Interaction Safety

| Agent/Component | Circumstance | Action | Safe? |
|-----------------|--------------|--------|-------|
| Monitor | Status check | Read git log | Yes |
"""

CASE_INSENSITIVE = """\
## Interaction Safety

| agent/component | circumstance | action | concurrent with | safe? | mitigation |
|-----------------|--------------|--------|-----------------|-------|------------|
| Monitor | Status check | Read git log | Agent commit | Yes | Read-only |
"""

H3_HEADING = """\
### Interaction Safety

| Agent/Component | Circumstance | Action | Concurrent With | Safe? | Mitigation |
|-----------------|--------------|--------|-----------------|-------|------------|
| Monitor | Status check | Read git log | Agent commit | Yes | Read-only |
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSafetyValidator:
    """Tests for validate_safety_table function."""

    def test_valid_table(self) -> None:
        """Plan with correct heading and 6-column table passes."""
        is_valid, reason = validate_safety_table(VALID_PLAN)
        assert is_valid is True
        assert reason == "Safety table validated"

    def test_missing_heading(self) -> None:
        """Plan without ## Interaction Safety heading fails."""
        is_valid, reason = validate_safety_table(MISSING_HEADING)
        assert is_valid is False
        assert "Missing '## Interaction Safety' section" in reason

    def test_missing_columns(self) -> None:
        """Plan with heading but table missing required columns fails."""
        is_valid, reason = validate_safety_table(MISSING_COLUMNS)
        assert is_valid is False
        assert "missing required columns" in reason.lower()

    def test_no_data_rows(self) -> None:
        """Plan with heading and header row but no data rows fails."""
        is_valid, reason = validate_safety_table(NO_DATA_ROWS)
        assert is_valid is False
        assert "no data rows" in reason.lower()

    def test_partial_columns(self) -> None:
        """Plan with only 4 of 6 required columns fails."""
        is_valid, reason = validate_safety_table(PARTIAL_COLUMNS)
        assert is_valid is False
        assert "missing required columns" in reason.lower()

    def test_case_insensitive_columns(self) -> None:
        """Column headers with different casing still validate."""
        is_valid, reason = validate_safety_table(CASE_INSENSITIVE)
        assert is_valid is True
        assert reason == "Safety table validated"

    def test_multiple_data_rows(self) -> None:
        """Plan with 3+ data rows passes validation."""
        is_valid, reason = validate_safety_table(VALID_PLAN_MULTIPLE_ROWS)
        assert is_valid is True

    def test_heading_at_different_levels(self) -> None:
        """### Interaction Safety (h3) does NOT match -- must be h2."""
        is_valid, reason = validate_safety_table(H3_HEADING)
        assert is_valid is False
        assert "Missing '## Interaction Safety' section" in reason
