"""PM-CONTEXT.md assembly from project documents (D-20, MILE-03).

Generates the PM context document that the PM tier reads fresh on each call.
Assembles from: PROJECT-BLUEPRINT.md, INTERFACES.md, MILESTONE-SCOPE.md,
PROJECT-STATUS.md, and recent decisions from decisions.jsonl.

Per MILE-02, three input documents define a project: BLUEPRINT, INTERFACES,
MILESTONE-SCOPE. PROJECT-STATUS.md and decisions provide additional context.
"""

import json
from pathlib import Path

from vcompany.shared.file_ops import write_atomic

# Source files and their section headers for PM-CONTEXT.md assembly.
CONTEXT_SOURCES: list[tuple[str, str]] = [
    ("PROJECT-BLUEPRINT.md", "## Project Blueprint"),
    ("INTERFACES.md", "## Interface Contracts"),
    ("MILESTONE-SCOPE.md", "## Current Milestone Scope"),
    ("PROJECT-STATUS.md", "## Project Status"),
]

# Maximum number of recent decisions to include in context.
MAX_DECISIONS = 50


def build_pm_context(project_dir: Path) -> str:
    """Assemble PM-CONTEXT.md content from project documents.

    Reads source files from project_dir/context/ and decisions from
    project_dir/state/decisions.jsonl. Missing files are gracefully skipped.

    Args:
        project_dir: Root directory of the project (contains context/ and state/).

    Returns:
        Assembled PM context as a markdown string.
    """
    sections: list[str] = ["# PM Context -- auto-generated, do not edit\n"]

    context_dir = project_dir / "context"
    for filename, header in CONTEXT_SOURCES:
        path = context_dir / filename
        if path.exists():
            content = path.read_text()
            sections.append(f"\n{header}\n\n{content}\n")

    # Append recent decisions from decisions.jsonl
    decisions_path = project_dir / "state" / "decisions.jsonl"
    if decisions_path.exists():
        entries: list[dict] = []
        for line in decisions_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        # Keep only the last MAX_DECISIONS entries
        recent = entries[-MAX_DECISIONS:]
        if recent:
            lines = ["\n## Recent Decisions\n"]
            for entry in recent:
                ts = entry.get("timestamp", "?")
                decided_by = entry.get("decided_by", "?")
                decision = entry.get("decision", "?")
                confidence = entry.get("confidence_level", "?")
                lines.append(
                    f"- [{ts}] {decided_by}: {decision} (confidence: {confidence})"
                )
            sections.append("\n".join(lines) + "\n")

    return "\n".join(sections)


def write_pm_context(project_dir: Path) -> Path:
    """Build and write PM-CONTEXT.md to the project context directory.

    Calls build_pm_context() and writes the result atomically to
    project_dir/context/PM-CONTEXT.md.

    Args:
        project_dir: Root directory of the project.

    Returns:
        Path to the written PM-CONTEXT.md file.
    """
    content = build_pm_context(project_dir)
    output_path = project_dir / "context" / "PM-CONTEXT.md"
    write_atomic(output_path, content)
    return output_path
