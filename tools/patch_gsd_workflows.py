"""GSD workflow patcher for autonomous agent operation.

Patches GSD workflow files at ~/.claude/get-shit-done/workflows/ to:
1. Add vco report signals to discuss-phase.md and discuss-phase-assumptions.md
2. Add AUTONOMOUS MODE instructions to auto-select non-AskUserQuestion prompts
   in plan-phase.md, execute-phase.md, and execute-plan.md

Patches are idempotent -- running twice produces the same result.
All agents inherit these global patches (D-12).

Usage:
    python tools/patch_gsd_workflows.py
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

GSD_WORKFLOWS_DIR = Path.home() / ".claude" / "get-shit-done" / "workflows"

PATCH_MARKER = "# VCOMPANY-PATCHED"

# --- vco report snippets ---

DISCUSS_REPORT_START = (
    '<step name="vco_report_start" priority="first">\n'
    "**MANDATORY** -- Run before anything else:\n"
    "```bash\n"
    'vco report "starting discuss-phase $PHASE" 2>/dev/null || true\n'
    "```\n"
    "</step>\n\n"
)

DISCUSS_REPORT_END = (
    '<step name="vco_report_end">\n'
    "**MANDATORY** -- Run after context is written:\n"
    "```bash\n"
    'vco report "discuss-phase complete" 2>/dev/null || true\n'
    "```\n"
    "</step>\n\n"
)

DISCUSS_ASSUMPTIONS_REPORT_START = (
    '<step name="vco_report_start" priority="first">\n'
    "**MANDATORY** -- Run before anything else:\n"
    "```bash\n"
    'vco report "starting discuss-phase-assumptions $PHASE" 2>/dev/null || true\n'
    "```\n"
    "</step>\n\n"
)

DISCUSS_ASSUMPTIONS_REPORT_END = (
    '<step name="vco_report_end">\n'
    "**MANDATORY** -- Run after context is written:\n"
    "```bash\n"
    'vco report "discuss-phase-assumptions complete" 2>/dev/null || true\n'
    "```\n"
    "</step>\n\n"
)

# --- AUTONOMOUS MODE instruction block ---

AUTONOMOUS_MODE_TEMPLATE = (
    "\n**AUTONOMOUS MODE**: When `mode` is `yolo` in config, "
    'skip this prompt and auto-select "{option}".\n'
)


def _is_patched(content: str) -> bool:
    """Check if file already has the patch marker."""
    return PATCH_MARKER in content


def _add_marker(content: str) -> str:
    """Add patch marker at the top of content."""
    return PATCH_MARKER + "\n" + content


def patch_discuss_phase() -> bool:
    """Add vco report start/end calls to discuss-phase.md.

    Returns True if patched (or already patched), False on error.
    """
    path = GSD_WORKFLOWS_DIR / "discuss-phase.md"
    if not path.exists():
        logger.warning("discuss-phase.md not found at %s", path)
        return False

    content = path.read_text()

    if _is_patched(content):
        logger.info("discuss-phase.md already patched")
        return True

    # Insert start report before check_existing step
    anchor_start = '<step name="check_existing">'
    if anchor_start not in content:
        logger.warning("Could not find check_existing step in discuss-phase.md")
        return False

    content = content.replace(
        anchor_start,
        DISCUSS_REPORT_START + anchor_start,
        1,
    )

    # Insert end report before auto_advance step
    anchor_end = '<step name="auto_advance">'
    if anchor_end not in content:
        logger.warning("Could not find auto_advance step in discuss-phase.md")
        return False

    content = content.replace(
        anchor_end,
        DISCUSS_REPORT_END + anchor_end,
        1,
    )

    content = _add_marker(content)
    path.write_text(content)
    logger.info("Patched discuss-phase.md with vco report signals")
    return True


def patch_discuss_phase_assumptions() -> bool:
    """Add vco report start/end calls to discuss-phase-assumptions.md.

    Returns True if patched (or already patched), False on error or missing file.
    """
    path = GSD_WORKFLOWS_DIR / "discuss-phase-assumptions.md"
    if not path.exists():
        logger.warning("discuss-phase-assumptions.md not found at %s", path)
        return False

    content = path.read_text()

    if _is_patched(content):
        logger.info("discuss-phase-assumptions.md already patched")
        return True

    # Insert start report before check_existing step
    anchor_start = '<step name="check_existing">'
    if anchor_start not in content:
        logger.warning(
            "Could not find check_existing step in discuss-phase-assumptions.md"
        )
        return False

    content = content.replace(
        anchor_start,
        DISCUSS_ASSUMPTIONS_REPORT_START + anchor_start,
        1,
    )

    # Insert end report before auto_advance step
    anchor_end = '<step name="auto_advance">'
    if anchor_end not in content:
        logger.warning(
            "Could not find auto_advance step in discuss-phase-assumptions.md"
        )
        return False

    content = content.replace(
        anchor_end,
        DISCUSS_ASSUMPTIONS_REPORT_END + anchor_end,
        1,
    )

    content = _add_marker(content)
    path.write_text(content)
    logger.info("Patched discuss-phase-assumptions.md with vco report signals")
    return True


def patch_plan_phase() -> bool:
    """Add autonomous mode instructions for context_gate and ui_gate in plan-phase.md.

    Returns True if patched, False on error.
    """
    path = GSD_WORKFLOWS_DIR / "plan-phase.md"
    if not path.exists():
        logger.warning("plan-phase.md not found at %s", path)
        return False

    content = path.read_text()

    if _is_patched(content):
        logger.info("plan-phase.md already patched")
        return True

    # Patch context_gate: auto-select "Continue without context"
    context_anchor = '- header: "No context"'
    if context_anchor in content:
        content = content.replace(
            context_anchor,
            AUTONOMOUS_MODE_TEMPLATE.format(option="Continue without context")
            + context_anchor,
            1,
        )

    # Patch ui_gate: auto-select "Continue without UI-SPEC"
    ui_anchor = '- header: "UI Design Contract"'
    if ui_anchor in content:
        content = content.replace(
            ui_anchor,
            AUTONOMOUS_MODE_TEMPLATE.format(option="Continue without UI-SPEC")
            + ui_anchor,
            1,
        )

    content = _add_marker(content)
    path.write_text(content)
    logger.info("Patched plan-phase.md with autonomous mode instructions")
    return True


def patch_execute_phase() -> bool:
    """Add autonomous mode instruction for regression_gate in execute-phase.md.

    Returns True if patched, False on error.
    """
    path = GSD_WORKFLOWS_DIR / "execute-phase.md"
    if not path.exists():
        logger.warning("execute-phase.md not found at %s", path)
        return False

    content = path.read_text()

    if _is_patched(content):
        logger.info("execute-phase.md already patched")
        return True

    # Patch regression_gate: auto-select "Fix regressions before verification"
    regression_anchor = "Use AskUserQuestion to present the options.\n</step>"
    if regression_anchor in content:
        content = content.replace(
            regression_anchor,
            AUTONOMOUS_MODE_TEMPLATE.format(
                option="Fix regressions before verification"
            )
            + regression_anchor,
            1,
        )

    content = _add_marker(content)
    path.write_text(content)
    logger.info("Patched execute-phase.md with autonomous mode instructions")
    return True


def patch_execute_plan() -> bool:
    """Add autonomous mode instruction for previous_phase_check in execute-plan.md.

    Returns True if patched, False on error.
    """
    path = GSD_WORKFLOWS_DIR / "execute-plan.md"
    if not path.exists():
        logger.warning("execute-plan.md not found at %s", path)
        return False

    content = path.read_text()

    if _is_patched(content):
        logger.info("execute-plan.md already patched")
        return True

    # Patch previous_phase_check: auto-select "Proceed anyway"
    previous_anchor = 'AskUserQuestion(header="Previous Issues"'
    if previous_anchor in content:
        content = content.replace(
            previous_anchor,
            AUTONOMOUS_MODE_TEMPLATE.format(option="Proceed anyway")
            + previous_anchor,
            1,
        )

    content = _add_marker(content)
    path.write_text(content)
    logger.info("Patched execute-plan.md with autonomous mode instructions")
    return True


def verify_patches() -> dict[str, bool]:
    """Check each workflow file for patches.

    Returns dict of filename -> patched status.
    """
    results: dict[str, bool] = {}

    # discuss-phase.md
    discuss_path = GSD_WORKFLOWS_DIR / "discuss-phase.md"
    if discuss_path.exists():
        content = discuss_path.read_text()
        results["discuss-phase.md"] = (
            _is_patched(content)
            and bool(re.search(r'vco report.*discuss-phase complete', content))
        )
    else:
        results["discuss-phase.md"] = False

    # discuss-phase-assumptions.md
    assumptions_path = GSD_WORKFLOWS_DIR / "discuss-phase-assumptions.md"
    if assumptions_path.exists():
        content = assumptions_path.read_text()
        results["discuss-phase-assumptions.md"] = (
            _is_patched(content)
            and bool(
                re.search(
                    r'vco report.*discuss-phase-assumptions complete', content
                )
            )
        )
    else:
        results["discuss-phase-assumptions.md"] = False

    # plan-phase.md
    plan_path = GSD_WORKFLOWS_DIR / "plan-phase.md"
    if plan_path.exists():
        content = plan_path.read_text()
        results["plan-phase.md"] = _is_patched(content)
    else:
        results["plan-phase.md"] = False

    # execute-phase.md
    exec_phase_path = GSD_WORKFLOWS_DIR / "execute-phase.md"
    if exec_phase_path.exists():
        content = exec_phase_path.read_text()
        results["execute-phase.md"] = _is_patched(content)
    else:
        results["execute-phase.md"] = False

    # execute-plan.md
    exec_plan_path = GSD_WORKFLOWS_DIR / "execute-plan.md"
    if exec_plan_path.exists():
        content = exec_plan_path.read_text()
        results["execute-plan.md"] = _is_patched(content)
    else:
        results["execute-plan.md"] = False

    return results


def patch_all() -> dict[str, bool]:
    """Apply all patches. Returns dict of filename -> success status."""
    return {
        "discuss-phase.md": patch_discuss_phase(),
        "discuss-phase-assumptions.md": patch_discuss_phase_assumptions(),
        "plan-phase.md": patch_plan_phase(),
        "execute-phase.md": patch_execute_phase(),
        "execute-plan.md": patch_execute_plan(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    results = patch_all()
    print("\nPatch results:")
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {name}: {status}")

    verify_results = verify_patches()
    print("\nVerification:")
    for name, verified in verify_results.items():
        status = "VERIFIED" if verified else "NOT VERIFIED"
        print(f"  {name}: {status}")
