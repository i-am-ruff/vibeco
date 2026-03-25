"""Embed builders for Discord bot messages.

Provides build_status_embed (for !status), build_alert_embed (for #alerts),
build_plan_review_embed (for plan review), build_conflict_embed (for merge conflicts),
build_integration_embed (for integration results), and build_checkin_embed (for checkins).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from vcompany.communication.checkin import CheckinData
    from vcompany.integration.models import IntegrationResult


def build_status_embed(status_text: str) -> discord.Embed:
    """Parse generate_project_status output into a rich Discord embed.

    Splits on "## " headers to create embed fields. Title "Agent Fleet Status",
    color blue, timestamp set to now.

    Args:
        status_text: Raw text from generate_project_status().

    Returns:
        discord.Embed with fields for each section.
    """
    embed = discord.Embed(
        title="Agent Fleet Status",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    # Split on markdown H2 headers
    sections = status_text.split("## ")
    field_count = 0

    for section in sections:
        if not section.strip():
            continue
        if field_count >= 25:
            break

        lines = section.strip().split("\n", 1)
        name = lines[0].strip()[:256]
        value = lines[1].strip() if len(lines) > 1 else "No details"
        value = value[:1024]

        embed.add_field(name=name, value=value, inline=False)
        field_count += 1

    if field_count == 0:
        # No sections found, put the whole text as description
        embed.description = status_text[:4096]

    return embed


_ALERT_COLORS: dict[str, discord.Color] = {
    "error": discord.Color.red(),
    "warning": discord.Color.orange(),
    "info": discord.Color.yellow(),
}


def build_alert_embed(
    title: str,
    description: str,
    alert_type: str = "warning",
) -> discord.Embed:
    """Build an alert embed with color based on severity.

    Args:
        title: Alert title.
        description: Alert body text.
        alert_type: One of "error", "warning", "info". Defaults to "warning".

    Returns:
        discord.Embed with appropriate color.
    """
    color = _ALERT_COLORS.get(alert_type, discord.Color.orange())
    return discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )


def build_plan_review_embed(
    agent_id: str,
    phase: str,
    plan_number: str,
    task_count: int,
    goal: str,
    plan_path: str,
    *,
    safety_valid: bool = True,
    safety_message: str = "",
) -> discord.Embed:
    """Build a rich embed for plan review posting per D-07.

    Args:
        agent_id: Agent that created the plan.
        phase: Phase name/number.
        plan_number: Plan number within phase.
        task_count: Number of tasks in the plan.
        goal: Plan objective/goal text.
        plan_path: Path to the PLAN.md file.
        safety_valid: Whether safety table validation passed.
        safety_message: Validation message from safety_validator.

    Returns:
        discord.Embed with plan summary fields.
    """
    color = discord.Color.green() if safety_valid else discord.Color.orange()
    embed = discord.Embed(
        title=f"Plan Review: {agent_id}",
        description=goal[:4096] if goal else "No objective found",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Phase", value=phase, inline=True)
    embed.add_field(name="Plan", value=plan_number, inline=True)
    embed.add_field(name="Tasks", value=str(task_count), inline=True)

    if not safety_valid:
        embed.add_field(
            name="Safety Warning",
            value=f"Missing or incomplete interaction safety table: {safety_message}",
            inline=False,
        )

    embed.set_footer(text=f"Path: {plan_path}")
    return embed


def build_conflict_embed(
    agent_branches: list[str],
    conflict_files: list[str],
    resolved: list[str],
    unresolved: list[str],
) -> discord.Embed:
    """Build an embed for merge conflict reporting per INTG-07.

    Args:
        agent_branches: Branch names involved in the conflict.
        conflict_files: All files with conflicts.
        resolved: Files that were auto-resolved by PM.
        unresolved: Files that need manual resolution.

    Returns:
        discord.Embed with conflict details.
    """
    embed = discord.Embed(
        title="Merge Conflict Detected",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Branches Involved",
        value=", ".join(agent_branches) if agent_branches else "None",
        inline=False,
    )
    embed.add_field(
        name="Conflict Files",
        value="\n".join(conflict_files) if conflict_files else "None",
        inline=False,
    )
    embed.add_field(
        name="Auto-Resolved",
        value="\n".join(resolved) if resolved else "None",
        inline=True,
    )
    embed.add_field(
        name="Needs Manual Resolution",
        value="\n".join(unresolved) if unresolved else "None",
        inline=True,
    )
    return embed


_INTEGRATION_COLORS: dict[str, discord.Color] = {
    "success": discord.Color.green(),
    "test_failure": discord.Color.red(),
    "merge_conflict": discord.Color.orange(),
    "error": discord.Color.greyple(),
}


def build_integration_embed(result: IntegrationResult) -> discord.Embed:
    """Build an embed for integration pipeline results.

    Args:
        result: IntegrationResult from the integration pipeline.

    Returns:
        discord.Embed with integration details, test counts, PR URL, and attribution.
    """
    color = _INTEGRATION_COLORS.get(result.status, discord.Color.greyple())
    embed = discord.Embed(
        title=f"Integration: {result.status.upper()}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Branch",
        value=result.branch_name or "N/A",
        inline=True,
    )
    embed.add_field(
        name="Merged Agents",
        value=", ".join(result.merged_agents) if result.merged_agents else "None",
        inline=True,
    )

    # Test results
    if result.test_results is not None:
        tr = result.test_results
        embed.add_field(
            name="Tests",
            value=f"Total: {tr.total}, Failed: {tr.failed}",
            inline=False,
        )

    # PR URL
    embed.add_field(
        name="PR",
        value=result.pr_url if result.pr_url else "N/A",
        inline=True,
    )

    # Attribution (agent -> failing tests)
    if result.attribution:
        attr_lines = []
        for agent, tests in result.attribution.items():
            attr_lines.append(f"**{agent}**: {', '.join(tests)}")
        embed.add_field(
            name="Attributed Failures",
            value="\n".join(attr_lines)[:1024],
            inline=False,
        )

    # Conflict files
    if result.conflict_files:
        embed.add_field(
            name="Conflicts",
            value="\n".join(result.conflict_files)[:1024],
            inline=False,
        )

    return embed


def build_checkin_embed(checkin: CheckinData) -> discord.Embed:
    """Build checkin embed per COMM-01/COMM-02.

    Displays: commit count, summary, gaps/notes, next phase, dependency status.

    Args:
        checkin: CheckinData from gather_checkin_data.

    Returns:
        discord.Embed with all checkin fields.
    """
    embed = discord.Embed(
        title=f"Phase Complete: {checkin.agent_id}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Commits", value=str(checkin.commit_count), inline=True)
    embed.add_field(name="Next Phase", value=checkin.next_phase, inline=True)
    embed.add_field(
        name="Summary",
        value=checkin.summary[:1024] or "No commits",
        inline=False,
    )
    if checkin.gaps:
        embed.add_field(
            name="Gaps / Notes",
            value=checkin.gaps[:1024],
            inline=False,
        )
    embed.add_field(
        name="Dependencies",
        value=checkin.dependency_status[:1024] or "None",
        inline=False,
    )
    return embed
