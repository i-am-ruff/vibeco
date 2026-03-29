"""Import boundary tests (EXTRACT-04, Phase 22).

Verifies that bot cog modules do not import container, supervisor, or agent
modules at runtime (only under TYPE_CHECKING guards).

Expanded in Phase 22 to cover all 9 cog files + client.py with strict
PROHIBITED_PREFIXES. New tests for function-level imports and company_root
attribute access are xfail until Plans 02-03 rewrite the cogs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Modules that the bot layer must NOT import at runtime
PROHIBITED_PREFIXES = [
    # Supervisor layer
    "vcompany.supervisor.company_root",
    "vcompany.supervisor.supervisor",
    "vcompany.supervisor.project_supervisor",
    # Container layer
    "vcompany.container.container",
    "vcompany.container.child_spec",
    "vcompany.container.context",
    "vcompany.container.factory",
    # Resilience layer
    "vcompany.resilience.message_queue",
    # Tmux layer
    "vcompany.tmux.session",
    # Strategist layer
    "vcompany.strategist.plan_reviewer",
    "vcompany.strategist.pm",
    "vcompany.strategist.conversation",
    "vcompany.strategist.decision_log",
    "vcompany.strategist.models",
    "vcompany.strategist.workflow_master_persona",
    # Communication layer (should go through RuntimeAPI)
    "vcompany.communication.checkin",
    "vcompany.communication.standup",
    # Integration layer
    "vcompany.integration.pipeline",
    # Monitor layer
    "vcompany.monitor.safety_validator",
    # Models layer
    "vcompany.models.config",
    "vcompany.models.agent_state",
    # Git layer
    "vcompany.git.ops",
    # CLI layer
    "vcompany.cli.clone_cmd",
    # Agent layer
    "vcompany.agent.company_agent",
    "vcompany.agent.gsd_agent",
    "vcompany.agent.continuous_agent",
    "vcompany.agent.fulltime_agent",
    "vcompany.agent.task_agent",
]

# All bot files to check (client + all 9 cogs)
BOT_FILES = [
    "src/vcompany/bot/client.py",
    "src/vcompany/bot/cogs/commands.py",
    "src/vcompany/bot/cogs/strategist.py",
    "src/vcompany/bot/cogs/plan_review.py",
    "src/vcompany/bot/cogs/health.py",
    "src/vcompany/bot/cogs/task_relay.py",
    "src/vcompany/bot/cogs/workflow_master.py",
    "src/vcompany/bot/cogs/workflow_orchestrator_cog.py",
    "src/vcompany/bot/cogs/question_handler.py",
    "src/vcompany/bot/cogs/alerts.py",
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


def _get_all_import_lines(content: str) -> list[tuple[int, str]]:
    """Extract ALL import lines (module-level and function-level), excluding TYPE_CHECKING blocks.

    Returns list of (line_number, line_text) tuples.
    """
    lines = content.split("\n")
    in_type_checking = False
    type_checking_indent = 0
    imports = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Detect TYPE_CHECKING guard
        if "TYPE_CHECKING" in stripped and stripped.startswith("if"):
            in_type_checking = True
            type_checking_indent = len(line) - len(line.lstrip())
            continue
        if in_type_checking:
            # Still inside TYPE_CHECKING block if indented more than the if
            if stripped == "" or (len(line) - len(line.lstrip())) > type_checking_indent:
                continue
            # Left the block
            in_type_checking = False
        # Check for import statements at any indentation
        if "from " in stripped and " import " in stripped:
            imports.append((i, stripped))
        elif stripped.startswith("import ") and not stripped.startswith("import_"):
            imports.append((i, stripped))
    return imports


@pytest.mark.xfail(reason="Phase 22 plans 02-03 will fix these violations")
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


@pytest.mark.xfail(reason="Phase 22 plans 02-03 will fix these violations")
def test_no_function_level_prohibited_imports():
    """Bot cog files must not have prohibited imports even inside function bodies.

    Function-level (lazy) imports of prohibited modules should be moved to
    RuntimeAPI. This catches imports at any indentation level, excluding
    TYPE_CHECKING blocks.
    """
    violations = []
    for filepath in BOT_FILES:
        path = Path(filepath)
        if not path.exists():
            continue
        with open(path) as f:
            content = f.read()
        all_imports = _get_all_import_lines(content)
        for prefix in PROHIBITED_PREFIXES:
            for lineno, imp_line in all_imports:
                if f"from {prefix} import" in imp_line or f"from {prefix}" in imp_line:
                    violations.append(f"{filepath}:{lineno}: {imp_line}")

    assert not violations, (
        "Prohibited imports found (including function-level):\n" + "\n".join(violations)
    )


@pytest.mark.xfail(reason="Phase 22 plans 02-03 will fix these violations")
def test_no_company_root_attribute_access():
    """Bot cog files must not access company_root directly.

    Cogs should use RuntimeAPI instead of self.bot.company_root,
    _get_company_root, or getattr(self.bot, "company_root").
    """
    patterns = [
        re.compile(r"company_root"),
        re.compile(r"_get_company_root"),
        re.compile(r"getattr\s*\([^,]+,\s*['\"]company_root['\"]"),
    ]
    violations = []
    for filepath in BOT_FILES:
        path = Path(filepath)
        if not path.exists():
            continue
        with open(path) as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and TYPE_CHECKING imports
            if stripped.startswith("#"):
                continue
            for pattern in patterns:
                if pattern.search(line):
                    violations.append(f"{filepath}:{lineno}: {stripped}")
                    break  # One violation per line is enough

    assert not violations, (
        "company_root access found in bot cogs:\n" + "\n".join(violations)
    )
