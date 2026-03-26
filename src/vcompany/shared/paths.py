"""Centralized path constants for vCompany.

Projects live OUTSIDE the orchestrator repo to prevent agents from
accidentally modifying vCompany source code. Default: ~/vco-projects/
"""

import os
from pathlib import Path

# Default project root — OUTSIDE the orchestrator repo
# Override with VCO_PROJECTS_DIR env var
PROJECTS_BASE = Path(os.environ.get("VCO_PROJECTS_DIR", str(Path.home() / "vco-projects")))
