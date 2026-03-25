"""Tests for the atomic file write utility."""

import os
from pathlib import Path
from unittest.mock import patch

from vcompany.shared.file_ops import write_atomic


class TestWriteAtomic:
    def test_write_atomic_creates_file(self, tmp_path: Path) -> None:
        target = tmp_path / "output.txt"
        write_atomic(target, "hello world")
        assert target.exists()
        assert target.read_text() == "hello world"

    def test_write_atomic_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "dir" / "file.txt"
        write_atomic(target, "nested content")
        assert target.exists()
        assert target.read_text() == "nested content"

    def test_write_atomic_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "output.txt"
        write_atomic(target, "first")
        write_atomic(target, "second")
        assert target.read_text() == "second"

    def test_write_atomic_no_partial_reads(self, tmp_path: Path) -> None:
        target = tmp_path / "output.txt"
        write_atomic(target, "complete content")
        # No .tmp files should remain after successful write
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Leftover tmp files: {tmp_files}"

    def test_write_atomic_cleans_up_on_error(self, tmp_path: Path) -> None:
        target = tmp_path / "output.txt"
        with patch("vcompany.shared.file_ops.os.rename") as mock_rename:
            mock_rename.side_effect = OSError("rename failed")
            try:
                write_atomic(target, "content")
            except OSError:
                pass
        # No .tmp files should remain after failed write
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Leftover tmp files: {tmp_files}"

    def test_write_atomic_encoding(self, tmp_path: Path) -> None:
        target = tmp_path / "unicode.txt"
        content = "Hello \u4e16\u754c \u00e9\u00e8\u00ea \u2603"
        write_atomic(target, content)
        assert target.read_text(encoding="utf-8") == content
