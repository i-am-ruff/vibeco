"""Embed builders for Discord bot messages.

Provides build_status_embed (for !status) and build_alert_embed (for #alerts).
"""

from datetime import datetime, timezone

import discord


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
