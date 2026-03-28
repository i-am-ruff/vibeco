"""Embed builders for Discord bot messages.

Provides build_alert_embed (for #alerts),
build_plan_review_embed (for plan review), build_conflict_embed (for merge conflicts),
build_integration_embed (for integration results), build_standup_embed (for standup threads),
and build_checkin_embed (for checkins).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from vcompany.communication.checkin import CheckinData
    from vcompany.container.health import CompanyHealthTree
    from vcompany.integration.models import IntegrationResult


# ── Health tree state indicators (HLTH-03) ─────────────────────────
STATE_INDICATORS: dict[str, str] = {
    "running": "\U0001f7e2",    # green circle
    "sleeping": "\U0001f535",   # blue circle
    "errored": "\U0001f534",    # red circle
    "stopped": "\u26ab",        # black circle
    "creating": "\U0001f7e1",   # yellow circle
    "destroyed": "\u2b1b",      # black square
    "blocked": "\U0001f7e0",    # orange circle -- ARCH-02/ARCH-04 new state
    "stopping": "\U0001f7e1",   # yellow circle -- transient, same as creating
}

_DEFAULT_INDICATOR = "\u2753"   # question mark for unknown states


def _fmt_uptime(seconds: float) -> str:
    """Format uptime seconds as human-readable duration."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h > 0:
        return f"up {h}h {m}m"
    elif m > 0:
        return f"up {m}m"
    return f"up {s}s"


def _fmt_last_activity(last: datetime) -> str:
    """Format last_activity as time-ago string."""
    diff = (datetime.now(timezone.utc) - last).total_seconds()
    if diff < 60:
        return f"active {int(diff)}s ago"
    elif diff < 3600:
        return f"active {int(diff // 60)}m ago"
    return f"active {int(diff // 3600)}h ago"


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


def build_standup_embed(
    agent_id: str, phase: str, status: str, summary: str
) -> discord.Embed:
    """Build standup embed for per-agent thread per COMM-03.

    Args:
        agent_id: Agent identifier.
        phase: Current phase the agent is working on.
        status: Agent status (e.g. "active", "idle").
        summary: Recent work summary (truncated to 1024 chars).

    Returns:
        discord.Embed with Phase, Status, and Recent Work fields.
    """
    embed = discord.Embed(
        title=f"Standup: {agent_id}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Phase", value=phase, inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="Recent Work",
        value=summary[:1024] or "No recent commits",
        inline=False,
    )
    embed.set_footer(
        text="Reply in this thread to communicate with the agent. Click Release when done."
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


def build_health_tree_embed(
    tree: CompanyHealthTree,
    *,
    project_filter: str | None = None,
    agent_filter: str | None = None,
) -> discord.Embed:
    """Build a Discord embed rendering the supervision health tree (HLTH-03).

    Args:
        tree: CompanyHealthTree from CompanyRoot.health_tree().
        project_filter: If set, only include the project whose supervisor_id matches.
        agent_filter: If set, only include children whose agent_id matches.

    Returns:
        discord.Embed with color-coded state indicators per agent.
    """
    # Determine embed color: green if all agents/projects running, red otherwise
    all_running = True
    if tree.company_agents:
        all_running = all_running and all(
            c.report.state == "running" for c in tree.company_agents
        )
    if tree.projects:
        all_running = all_running and all(p.state == "running" for p in tree.projects)
    color = discord.Color.green() if all_running else discord.Color.red()

    embed = discord.Embed(
        title="Health Tree",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # HLTH-05: Show CompanyRoot as the explicit root node with lifecycle state
    root_emoji = STATE_INDICATORS.get(tree.state, _DEFAULT_INDICATOR)
    embed.description = f"{root_emoji} **{tree.supervisor_id}**: {tree.state}"

    # Render company-level agents (Strategist, etc.) before project sections
    if tree.company_agents:
        lines: list[str] = []
        for child in tree.company_agents:
            r = child.report
            emoji = STATE_INDICATORS.get(r.state, _DEFAULT_INDICATOR)
            inner = f" ({r.inner_state})" if r.inner_state else ""
            blocked = f" -- {r.blocked_reason}" if r.blocked_reason else ""
            uptime_str = _fmt_uptime(r.uptime)
            activity_str = _fmt_last_activity(r.last_activity)
            lines.append(f"{emoji} **{r.agent_id}**: {r.state}{inner} | {uptime_str} | {activity_str}{blocked}")
        value = "\n".join(lines)
        if len(value) > 1024:
            value = value[:1021] + "..."
        embed.add_field(
            name="Company Agents",
            value=value,
            inline=False,
        )

    projects = tree.projects
    if project_filter is not None:
        projects = [p for p in projects if p.supervisor_id == project_filter]

    if not projects and not tree.projects and not tree.company_agents:
        embed.description += "\nNo projects active"
        return embed

    if not projects and project_filter is not None:
        embed.description += "\nNo projects active"
        return embed

    field_count = 0
    remaining = len(projects)

    for project in projects:
        if field_count >= 24:
            embed.add_field(
                name=f"... and {remaining} more projects",
                value="Use project filter to see details",
                inline=False,
            )
            break

        # Build agent lines
        children = project.children
        if agent_filter is not None:
            children = [c for c in children if c.report.agent_id == agent_filter]

        if children:
            agent_lines: list[str] = []
            for child in children:
                r = child.report
                emoji = STATE_INDICATORS.get(r.state, _DEFAULT_INDICATOR)
                inner = f" ({r.inner_state})" if r.inner_state else ""
                blocked = f" -- {r.blocked_reason}" if r.blocked_reason else ""
                uptime_str = _fmt_uptime(r.uptime)
                activity_str = _fmt_last_activity(r.last_activity)
                agent_lines.append(f"{emoji} **{r.agent_id}**: {r.state}{inner} | {uptime_str} | {activity_str}{blocked}")
            value = "\n".join(agent_lines)
        else:
            value = "No agents"

        # Truncate to Discord's 1024-char field value limit
        if len(value) > 1024:
            value = value[:1021] + "..."

        embed.add_field(
            name=f"Project: {project.supervisor_id}",
            value=value,
            inline=False,
        )
        field_count += 1
        remaining -= 1

    return embed
