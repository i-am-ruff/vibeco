"""Sync context files from project context/ to all agent clones.

Copies INTERFACES.md, MILESTONE-SCOPE.md, and STRATEGIST-PROMPT.md to each
clone directory using write_atomic for safe concurrent reads.
"""

from dataclasses import dataclass, field
from pathlib import Path

from vcompany.models.config import ProjectConfig
from vcompany.shared.file_ops import write_atomic

# Files to sync from {project}/context/ to each clone
SYNC_FILES = ["INTERFACES.md", "MILESTONE-SCOPE.md", "STRATEGIST-PROMPT.md"]


@dataclass
class SyncResult:
    """Result of a sync-context operation."""

    clones_updated: int = 0
    files_synced: int = 0
    errors: list[str] = field(default_factory=list)


def sync_context_files(project_dir: Path, config: ProjectConfig) -> SyncResult:
    """Copy context files to all agent clones via write_atomic.

    Args:
        project_dir: Root project directory containing context/ and clones/.
        config: Project configuration with agent list.

    Returns:
        SyncResult with counts of updated clones, synced files, and errors.
    """
    result = SyncResult()
    context_dir = project_dir / "context"

    # Read source files (skip missing ones)
    source_files: dict[str, str] = {}
    for filename in SYNC_FILES:
        source_path = context_dir / filename
        if source_path.exists():
            source_files[filename] = source_path.read_text()

    # Copy to each clone
    for agent in config.agents:
        clone_dir = project_dir / "clones" / agent.id
        if not clone_dir.is_dir():
            result.errors.append(f"Clone directory missing for {agent.id}: {clone_dir}")
            continue

        clone_synced = False
        for filename, content in source_files.items():
            try:
                write_atomic(clone_dir / filename, content)
                result.files_synced += 1
                clone_synced = True
            except Exception as e:
                result.errors.append(f"Failed to sync {filename} to {agent.id}: {e}")

        if clone_synced:
            result.clones_updated += 1

    return result
