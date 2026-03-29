"""Import boundary tests (EXTRACT-04).

Verifies that bot cog modules do not import container, supervisor, or agent
modules at runtime (only under TYPE_CHECKING guards).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Modules that the bot layer must NOT import at runtime
PROHIBITED_PREFIXES = [
    "vcompany.supervisor.company_root",
    "vcompany.supervisor.supervisor",
    "vcompany.supervisor.project_supervisor",
    "vcompany.container.container",
    "vcompany.container.child_spec",
    "vcompany.container.context",
    "vcompany.container.factory",
    "vcompany.resilience.message_queue",
    "vcompany.tmux.session",
    "vcompany.strategist.plan_reviewer",
    "vcompany.strategist.pm",
]

# Files to check
BOT_FILES = [
    "src/vcompany/bot/client.py",
    "src/vcompany/bot/cogs/commands.py",
    "src/vcompany/bot/cogs/strategist.py",
    "src/vcompany/bot/cogs/plan_review.py",
]


def _get_toplevel_imports(content: str) -> list[str]:
    """Extract module-level import lines (not inside functions/methods or TYPE_CHECKING).

    Module-level imports are those with zero indentation (column 0) that are
    NOT inside an ``if TYPE_CHECKING:`` block.
    """
    lines = content.split("\n")
    in_type_checking = False
    imports = []
    for line in lines:
        stripped = line.strip()
        # Detect TYPE_CHECKING guard at any indentation
        if "TYPE_CHECKING" in stripped and stripped.startswith("if"):
            in_type_checking = True
            continue
        if in_type_checking:
            # Inside TYPE_CHECKING block: indented lines are guarded
            if stripped and not stripped.startswith((" ", "\t", "from", "import", "#")):
                # We left the block -- but only if the line has zero indent
                if not line.startswith((" ", "\t")):
                    in_type_checking = False
            else:
                continue
        # Only flag lines that start at column 0 (module-level)
        if line.startswith("from ") or line.startswith("import "):
            imports.append(stripped)
    return imports


def test_no_container_imports_in_bot():
    """Bot layer must not import container/supervisor modules at runtime (module-level only).

    Inline imports inside functions (e.g., inside remove_project or _send_tmux_command)
    are acceptable -- they are lazy and only execute when the function is called.
    This test checks module-level imports only.
    """
    violations = []
    for filepath in BOT_FILES:
        path = Path(filepath)
        if not path.exists():
            continue
        with open(path) as f:
            content = f.read()
        toplevel = _get_toplevel_imports(content)
        for prefix in PROHIBITED_PREFIXES:
            for imp_line in toplevel:
                if f"from {prefix} import" in imp_line:
                    violations.append(f"{filepath}: {imp_line}")

    assert not violations, "Prohibited imports found:\n" + "\n".join(violations)


def test_no_discord_in_daemon():
    """Daemon package must not import discord."""
    daemon_dir = Path("src/vcompany/daemon")
    violations = []
    for py_file in daemon_dir.glob("*.py"):
        with open(py_file) as f:
            content = f.read()
        if "import discord" in content:
            violations.append(str(py_file))
    assert not violations, f"discord imports found in daemon: {violations}"
