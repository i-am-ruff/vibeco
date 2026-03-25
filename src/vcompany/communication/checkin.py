"""Checkin ritual: gather phase completion data and post to Discord.

Gathers commit count, summary, gaps, next phase, and dependency status
from an agent's clone directory. Posts formatted embed to agent's Discord channel.

References: COMM-01 (Discord posting), COMM-02 (checkin data fields).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from vcompany.git import ops as git_ops

if TYPE_CHECKING:
    import discord


class CheckinData(BaseModel):
    """Data gathered for a phase completion checkin per COMM-02."""

    agent_id: str
    commit_count: int = 0
    summary: str = ""
    gaps: str = ""
    next_phase: str = "unknown"
    dependency_status: str = ""


def _parse_roadmap_phases(roadmap_text: str) -> list[dict[str, str]]:
    """Parse phase rows from ROADMAP.md table.

    Returns list of dicts with keys: phase, name, status, depends_on.
    """
    phases: list[dict[str, str]] = []
    for line in roadmap_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue
        # Skip header and separator rows
        if cells[0] in ("Phase", "-------", "---", "") or "-" * 3 in cells[0]:
            continue
        phase_info: dict[str, str] = {
            "phase": cells[0],
            "name": cells[1] if len(cells) > 1 else "",
            "status": cells[2] if len(cells) > 2 else "",
            "depends_on": cells[3] if len(cells) > 3 else "-",
        }
        phases.append(phase_info)
    return phases


def _extract_blockers(state_text: str) -> str:
    """Extract Blockers/Concerns section from STATE.md."""
    match = re.search(
        r"## Blockers/Concerns\s*\n(.*?)(?=\n## |\Z)",
        state_text,
        re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def gather_checkin_data(agent_id: str, clone_dir: Path) -> CheckinData:
    """Gather checkin data from an agent's clone directory.

    Reads:
    - git log --oneline for commit count and summary (since branch diverged from main)
    - .planning/ROADMAP.md for current phase status, next phase, and dependencies
    - .planning/STATE.md for any noted blockers/concerns

    Args:
        agent_id: The agent identifier.
        clone_dir: Path to the agent's clone directory.

    Returns:
        CheckinData with all fields populated.
    """
    # git log --oneline main..HEAD for commits on this branch
    log_result = git_ops.log(clone_dir, ["--oneline", "main..HEAD"])
    commits = log_result.stdout.strip().splitlines() if log_result.success and log_result.stdout.strip() else []
    commit_count = len(commits)
    summary = "\n".join(commits[:10])

    # Read ROADMAP.md for phase info
    roadmap_path = clone_dir / ".planning" / "ROADMAP.md"
    next_phase = "unknown"
    dependency_status = ""
    if roadmap_path.exists():
        roadmap_text = roadmap_path.read_text()
        phases = _parse_roadmap_phases(roadmap_text)

        # Find the first non-complete phase after current in-progress one
        found_in_progress = False
        for phase_info in phases:
            status_lower = phase_info["status"].lower()
            if "in progress" in status_lower:
                found_in_progress = True
                continue
            if found_in_progress and "complete" not in status_lower:
                next_phase = phase_info["phase"]
                deps = phase_info.get("depends_on", "-")
                if deps and deps != "-":
                    dependency_status = f"Depends on {deps}"
                break

    # Read STATE.md for blockers
    state_path = clone_dir / ".planning" / "STATE.md"
    gaps = ""
    if state_path.exists():
        state_text = state_path.read_text()
        gaps = _extract_blockers(state_text)

    return CheckinData(
        agent_id=agent_id,
        commit_count=commit_count,
        summary=summary,
        gaps=gaps,
        next_phase=next_phase,
        dependency_status=dependency_status,
    )


async def post_checkin(checkin: CheckinData, channel: discord.TextChannel) -> None:
    """Post a checkin embed to the agent's Discord channel per COMM-01.

    Args:
        checkin: Gathered checkin data.
        channel: The #agent-{id} Discord channel.
    """
    from vcompany.bot.embeds import build_checkin_embed

    embed = build_checkin_embed(checkin)
    await channel.send(embed=embed)
