"""Atomic file write utility.

All coordination file writes should use write_atomic() to prevent partial reads
from the monitor or other concurrent processes.
"""

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to path atomically using tmp-then-rename.

    Creates a temporary file in the same directory as the target, writes content,
    then uses os.rename() for an atomic swap. This guarantees readers never see
    partial content.

    Args:
        path: Target file path.
        content: String content to write.
        encoding: File encoding (default utf-8).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.rename(tmp_path, path)  # Atomic on same filesystem
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
