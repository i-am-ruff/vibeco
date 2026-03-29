"""Centralized path constants for vCompany.

Projects live OUTSIDE the orchestrator repo to prevent agents from
accidentally modifying vCompany source code. Default: ~/vco-projects/
"""

import os
from pathlib import Path

# Default project root — OUTSIDE the orchestrator repo
# Override with VCO_PROJECTS_DIR env var
PROJECTS_BASE = Path(os.environ.get("VCO_PROJECTS_DIR", str(Path.home() / "vco-projects")))

# Daemon socket and PID file paths
# Override with VCO_SOCKET_PATH / VCO_PID_PATH env vars
VCO_SOCKET_PATH = Path(os.environ.get("VCO_SOCKET_PATH", "/tmp/vco-daemon.sock"))
VCO_PID_PATH = Path(os.environ.get("VCO_PID_PATH", "/tmp/vco-daemon.pid"))
