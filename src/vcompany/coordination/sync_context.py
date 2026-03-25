"""Sync context files from project context/ to all agent clones.

Copies INTERFACES.md, MILESTONE-SCOPE.md, and PM-CONTEXT.md to each
clone directory using write_atomic for safe concurrent reads.

Per D-20: PM-CONTEXT.md replaces STRATEGIST-PROMPT.md. Backward compat
renames old file if PM-CONTEXT.md doesn't exist yet.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from vcompany.models.config import ProjectConfig
from vcompany.shared.file_ops import write_atomic

logger = logging.getLogger("vcompany.coordination.sync_context")

# Files to sync from {project}/context/ to each clone (D-20: PM-CONTEXT.md replaces STRATEGIST-PROMPT.md)
SYNC_FILES = ["INTERFACES.md", "MILESTONE-SCOPE.md", "PM-CONTEXT.md"]


@dataclass
class SyncResult:
    """Result of a sync-context operation."""

    clones_updated: int = 0
    files_synced: int = 0
    errors: list[str] = field(default_factory=list)


def sync_context_files(project_dir: Path, config: ProjectConfig) -> SyncResult:
    """Copy context files to all agent clones via write_atomic.

    Before syncing, generates PM-CONTEXT.md if context_builder is available.
    Handles backward compat: renames STRATEGIST-PROMPT.md to PM-CONTEXT.md
    if the old file exists and the new one doesn't (D-20).

    Args:
        project_dir: Root project directory containing context/ and clones/.
        config: Project configuration with agent list.

    Returns:
        SyncResult with counts of updated clones, synced files, and errors.
    """
    result = SyncResult()
    context_dir = project_dir / "context"

    # D-20 backward compat: rename STRATEGIST-PROMPT.md -> PM-CONTEXT.md
    old_prompt = context_dir / "STRATEGIST-PROMPT.md"
    new_prompt = context_dir / "PM-CONTEXT.md"
    if old_prompt.exists() and not new_prompt.exists():
        old_prompt.rename(new_prompt)
        logger.info("Renamed STRATEGIST-PROMPT.md -> PM-CONTEXT.md (D-20)")

    # Generate PM-CONTEXT.md before syncing if context_builder is available
    try:
        from vcompany.strategist.context_builder import write_pm_context

        write_pm_context(project_dir)
    except ImportError:
        logger.debug("context_builder not available, skipping PM-CONTEXT.md generation")
    except Exception:
        logger.exception("Failed to generate PM-CONTEXT.md")

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
