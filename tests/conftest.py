"""Shared test fixtures for vCompany."""

import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def sample_agents_yaml() -> dict:
    """Return a valid agents.yaml content as a dict."""
    return {
        "project": "test-project",
        "repo": "git@github.com:owner/test-project.git",
        "agents": [
            {
                "id": "BACKEND",
                "role": "Backend API and database",
                "owns": ["src/api/", "src/db/"],
                "consumes": "INTERFACES.md",
                "gsd_mode": "full",
                "system_prompt": "agents/BACKEND.md",
            },
            {
                "id": "FRONTEND",
                "role": "Web application UI",
                "owns": ["src/app/", "src/components/"],
                "consumes": "INTERFACES.md",
                "gsd_mode": "full",
                "system_prompt": "agents/FRONTEND.md",
            },
        ],
        "shared_readonly": ["src/shared/types.ts", "package.json"],
    }


@pytest.fixture
def sample_agents_yaml_file(sample_agents_yaml: dict, tmp_path: Path) -> Path:
    """Write sample agents.yaml to a tmp file and return the path."""
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text(yaml.dump(sample_agents_yaml, default_flow_style=False))
    return yaml_path


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for project operations."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    return project_dir
