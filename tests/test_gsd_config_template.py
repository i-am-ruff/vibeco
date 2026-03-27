"""Tests for GSD config template values (D-18)."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "src" / "vcompany" / "templates" / "gsd_config.json.j2"


def _load_config() -> dict:
    """Load the GSD config template as JSON (no Jinja2 variables in workflow section)."""
    content = TEMPLATE_PATH.read_text()
    return json.loads(content)


class TestGsdConfigTemplate:
    """Verify GSD config template has correct autonomous operation values."""

    def test_discuss_mode_is_discuss(self) -> None:
        config = _load_config()
        assert config["workflow"]["discuss_mode"] == "discuss"

    def test_skip_discuss_is_false(self) -> None:
        config = _load_config()
        assert config["workflow"]["skip_discuss"] is False

    def test_auto_advance_is_false(self) -> None:
        config = _load_config()
        assert config["workflow"]["auto_advance"] is False

    def test_auto_chain_active_is_false(self) -> None:
        config = _load_config()
        assert config["workflow"]["_auto_chain_active"] is False

    def test_research_enabled(self) -> None:
        config = _load_config()
        assert config["workflow"]["research"] is True

    def test_plan_check_enabled(self) -> None:
        config = _load_config()
        assert config["workflow"]["plan_check"] is True

    def test_mode_is_yolo(self) -> None:
        config = _load_config()
        assert config["mode"] == "yolo"

    def test_template_file_exists(self) -> None:
        assert TEMPLATE_PATH.exists(), f"Template not found at {TEMPLATE_PATH}"
