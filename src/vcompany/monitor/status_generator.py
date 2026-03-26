"""PROJECT-STATUS.md generation and distribution.

Reads each clone's ROADMAP.md and git log, assembles formatted status per
VCO-ARCHITECTURE.md spec (per-agent phase list with emoji markers, Key
Dependencies, Notes), and distributes to all clones via write_atomic.

Implements D-10, D-11, D-12.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from vcompany.git import ops as git_ops
from vcompany.models.config import ProjectConfig
from vcompany.shared.file_ops import write_atomic

logger = logging.getLogger("vcompany.monitor.status_generator")

# Emoji markers per VCO-ARCHITECTURE.md
_EMOJI_COMPLETE = "\u2705"  # checkmark
_EMOJI_EXECUTING = "\U0001f504"  # cycle arrows
_EMOJI_PENDING = "\u231b"  # hourglass

# Regex for checklist-style: - [x] **Phase N: Description**
_PHASE_CHECKLIST_RE = re.compile(r"- \[(x| )\] \*\*Phase (\d+): (.+?)\*\*")

# Regex for GSD heading-style: ### Phase N: Description
_PHASE_HEADING_RE = re.compile(r"^###\s+Phase\s+(\d+):\s+(.+)")

# Regex for plan/UAT checklist items under a phase heading
_CHECKLIST_ITEM_RE = re.compile(r"^- \[(x| )\]")


def _parse_checklist_format(content: str) -> list[dict]:
    """Parse checklist-style roadmap: - [x] **Phase N: Description**."""
    phases: list[dict] = []
    found_first_unchecked = False

    for line in content.splitlines():
        match = _PHASE_CHECKLIST_RE.search(line)
        if not match:
            continue

        checked = match.group(1) == "x"
        number = int(match.group(2))
        description = match.group(3)

        if checked:
            status = "complete"
        elif not found_first_unchecked:
            status = "executing"
            found_first_unchecked = True
        else:
            status = "pending"

        phases.append({"number": number, "description": description, "status": status})

    return phases


def _parse_heading_format(content: str) -> list[dict]:
    """Parse GSD heading-style roadmap: ### Phase N: Description.

    Determines phase status by inspecting plan/UAT checklist items under each
    phase heading. A phase is "complete" when all items are checked, "executing"
    if it's the first phase with unchecked items, and "pending" otherwise.
    """
    phases: list[dict] = []
    current_phase: dict | None = None
    current_total = 0
    current_checked = 0

    def _finalize_phase(phase: dict, total: int, checked: int) -> None:
        if total > 0 and checked == total:
            phase["_done"] = True
        else:
            phase["_done"] = False

    for line in content.splitlines():
        heading_match = _PHASE_HEADING_RE.match(line)
        if heading_match:
            # Finalize previous phase
            if current_phase is not None:
                _finalize_phase(current_phase, current_total, current_checked)

            number = int(heading_match.group(1))
            description = heading_match.group(2).strip()
            current_phase = {"number": number, "description": description}
            phases.append(current_phase)
            current_total = 0
            current_checked = 0
            continue

        if current_phase is not None:
            item_match = _CHECKLIST_ITEM_RE.match(line)
            if item_match:
                current_total += 1
                if item_match.group(1) == "x":
                    current_checked += 1

    # Finalize last phase
    if current_phase is not None:
        _finalize_phase(current_phase, current_total, current_checked)

    # Assign statuses: complete, executing (first incomplete), pending
    found_first_incomplete = False
    for phase in phases:
        if phase.pop("_done", False):
            phase["status"] = "complete"
        elif not found_first_incomplete:
            phase["status"] = "executing"
            found_first_incomplete = True
        else:
            phase["status"] = "pending"

    return phases


def parse_roadmap(roadmap_path: Path) -> list[dict]:
    """Parse ROADMAP.md to extract phase status information.

    Supports two formats:
    1. Checklist-style: ``- [x] **Phase N: Description**``
    2. GSD heading-style: ``### Phase N: Description`` with plan/UAT checklists

    Args:
        roadmap_path: Path to a ROADMAP.md file.

    Returns:
        List of dicts with keys: number, description, status.
        Status is one of: complete, executing, pending, unknown.
        On any failure returns a single-element list with status "unknown".
    """
    try:
        content = roadmap_path.read_text()
    except Exception:
        return [{"number": 0, "description": "Status unknown", "status": "unknown"}]

    # Try checklist format first (original format)
    phases = _parse_checklist_format(content)

    # Fall back to GSD heading format
    if not phases:
        phases = _parse_heading_format(content)

    if not phases:
        return [{"number": 0, "description": "Status unknown", "status": "unknown"}]

    return phases


def get_agent_activity(clone_dir: Path) -> str:
    """Get recent git activity for an agent clone.

    Args:
        clone_dir: Path to the agent's git clone directory.

    Returns:
        Recent git log output or "No recent activity" on failure.
    """
    result = git_ops.log(clone_dir, args=["--oneline", "-5"])
    if result.success and result.stdout.strip():
        return result.stdout.strip()
    return "No recent activity"


def generate_project_status(
    project_dir: Path,
    config: ProjectConfig,
    *,
    now: datetime | None = None,
) -> str:
    """Generate PROJECT-STATUS.md content from all agent clones.

    Reads each clone's ROADMAP.md and git log, assembles formatted markdown
    per VCO-ARCHITECTURE.md spec.

    Args:
        project_dir: Root project directory.
        config: Project configuration with agent list.
        now: Current timestamp (injectable for testing).

    Returns:
        Complete PROJECT-STATUS.md markdown string.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    timestamp = now.strftime("%Y-%m-%d %H:%M")

    lines: list[str] = [
        "# Project Status \u2014 auto-generated by vco, do not edit",
        f"# Last updated: {timestamp} UTC",
        "",
    ]

    emoji_map = {
        "complete": _EMOJI_COMPLETE,
        "executing": _EMOJI_EXECUTING,
        "pending": _EMOJI_PENDING,
        "unknown": "\u2753",
    }

    for agent in config.agents:
        clone_dir = project_dir / "clones" / agent.id
        roadmap_path = clone_dir / ".planning" / "ROADMAP.md"

        phases = parse_roadmap(roadmap_path)
        activity = get_agent_activity(clone_dir)

        # Determine current phase info
        total = len(phases) if phases[0]["status"] != "unknown" else 0
        current_phase_num = 0
        current_status = "unknown"
        for p in phases:
            if p["status"] == "executing":
                current_phase_num = p["number"]
                current_status = "executing"
                break
            elif p["status"] == "complete":
                current_phase_num = p["number"]
                current_status = "complete"

        # If all complete, show last phase as current
        if current_status == "complete" and total > 0:
            current_status = "complete"

        # Agent section header
        agent_id_upper = agent.id.upper()
        if total > 0:
            lines.append(f"## {agent_id_upper} (Phase {current_phase_num}/{total} \u2014 {current_status})")
        else:
            lines.append(f"## {agent_id_upper} (status unknown)")

        # Phase list with emoji
        for p in phases:
            emoji = emoji_map.get(p["status"], "\u2753")
            lines.append(f"- {emoji} Phase {p['number']}: {p['description']}")

        # Recent activity
        lines.append("")
        lines.append(f"**Recent activity:**")
        for activity_line in activity.splitlines():
            lines.append(f"  {activity_line}")
        lines.append("")

    # Key Dependencies section (placeholder -- Phase 6 Strategist will populate)
    lines.append("## Key Dependencies")
    lines.append("- (none detected yet)")
    lines.append("")

    # Notes section (placeholder)
    lines.append("## Notes")
    lines.append("- (no notes)")
    lines.append("")

    return "\n".join(lines)


def distribute_project_status(
    project_dir: Path,
    config: ProjectConfig,
    content: str,
) -> int:
    """Distribute PROJECT-STATUS.md to context dir and all agent clones.

    Args:
        project_dir: Root project directory.
        config: Project configuration with agent list.
        content: The PROJECT-STATUS.md content to distribute.

    Returns:
        Count of clones updated.
    """
    # Write to canonical context location
    context_path = project_dir / "context" / "PROJECT-STATUS.md"
    write_atomic(context_path, content)

    # Write to each clone's root
    clones_updated = 0
    for agent in config.agents:
        clone_path = project_dir / "clones" / agent.id / "PROJECT-STATUS.md"
        try:
            write_atomic(clone_path, content)
            clones_updated += 1
        except Exception:
            logger.exception("Failed to distribute status to %s", agent.id)

    return clones_updated
