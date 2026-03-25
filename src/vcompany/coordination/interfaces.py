"""Interface change request logging and application.

Manages the append-only interface_changes.json audit trail and the canonical
INTERFACES.md contract file with atomic writes and sync distribution.
"""

from pathlib import Path

from vcompany.coordination.sync_context import SyncResult, sync_context_files
from vcompany.models.config import ProjectConfig
from vcompany.models.coordination_state import InterfaceChangeLog, InterfaceChangeRecord
from vcompany.shared.file_ops import write_atomic


def log_interface_change(project_dir: Path, record: InterfaceChangeRecord) -> None:
    """Append an interface change record to interface_changes.json.

    Creates the file if it doesn't exist. Preserves existing records.

    Args:
        project_dir: Root project directory containing context/.
        record: The interface change record to append.
    """
    changes_path = project_dir / "context" / "interface_changes.json"

    if changes_path.exists():
        log = InterfaceChangeLog.model_validate_json(changes_path.read_text())
    else:
        log = InterfaceChangeLog()

    log.records.append(record)
    write_atomic(changes_path, log.model_dump_json(indent=2))


def apply_interface_change(
    project_dir: Path,
    config: ProjectConfig,
    new_content: str,
    record: InterfaceChangeRecord,
) -> SyncResult:
    """Write new INTERFACES.md content and distribute to all clones.

    1. Writes new_content to {project}/context/INTERFACES.md atomically.
    2. Logs the record (with action="applied") to interface_changes.json.
    3. Calls sync_context_files to distribute to all clones.

    Args:
        project_dir: Root project directory.
        config: Project configuration with agent list.
        new_content: New INTERFACES.md content to write.
        record: The interface change record to log.

    Returns:
        SyncResult from the sync operation.
    """
    # Write canonical INTERFACES.md
    interfaces_path = project_dir / "context" / "INTERFACES.md"
    write_atomic(interfaces_path, new_content)

    # Log the change
    log_interface_change(project_dir, record)

    # Sync to all clones
    return sync_context_files(project_dir, config)
