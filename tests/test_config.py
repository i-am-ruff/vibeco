"""Tests for Pydantic config models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vcompany.models.config import AgentConfig, ProjectConfig, load_config


class TestValidConfig:
    """Tests for valid configuration parsing."""

    def test_valid_config(self, sample_agents_yaml: dict) -> None:
        """Parse sample_agents_yaml, assert all fields populated correctly."""
        config = ProjectConfig(**sample_agents_yaml)
        assert config.project == "test-project"
        assert config.repo == "git@github.com:owner/test-project.git"
        assert len(config.agents) == 2
        assert config.agents[0].id == "BACKEND"
        assert config.agents[0].role == "Backend API and database"
        assert config.agents[0].owns == ["src/api/", "src/db/"]
        assert config.agents[0].consumes == "INTERFACES.md"
        assert config.agents[0].gsd_mode == "full"
        assert config.agents[0].system_prompt == "agents/BACKEND.md"
        assert config.agents[1].id == "FRONTEND"
        assert config.shared_readonly == ["src/shared/types.ts", "package.json"]

    def test_non_overlapping_dirs_accepted(self, sample_agents_yaml: dict) -> None:
        """Agents owning src/api/ and src/app/ should pass validation."""
        config = ProjectConfig(**sample_agents_yaml)
        assert len(config.agents) == 2

    def test_load_config_from_file(self, sample_agents_yaml_file: Path) -> None:
        """load_config parses yaml file successfully."""
        config = load_config(sample_agents_yaml_file)
        assert config.project == "test-project"
        assert len(config.agents) == 2


class TestAgentIdValidation:
    """Tests for agent ID validation."""

    def test_agent_id_validation(self, sample_agents_yaml: dict) -> None:
        """Invalid chars in ID raise ValidationError."""
        sample_agents_yaml["agents"][0]["id"] = "BACK END"  # space not allowed
        with pytest.raises(ValidationError, match="alphanumeric"):
            ProjectConfig(**sample_agents_yaml)

    def test_agent_id_with_hyphens_accepted(self, sample_agents_yaml: dict) -> None:
        """Hyphens in agent ID should be accepted."""
        sample_agents_yaml["agents"][0]["id"] = "BACK-END"
        config = ProjectConfig(**sample_agents_yaml)
        assert config.agents[0].id == "BACK-END"

    def test_agent_id_with_underscores_accepted(self, sample_agents_yaml: dict) -> None:
        """Underscores in agent ID should be accepted."""
        sample_agents_yaml["agents"][0]["id"] = "BACK_END"
        config = ProjectConfig(**sample_agents_yaml)
        assert config.agents[0].id == "BACK_END"


class TestOwnershipValidation:
    """Tests for directory ownership validation."""

    def test_empty_owns_rejected(self, sample_agents_yaml: dict) -> None:
        """Agent with empty owns list rejected."""
        sample_agents_yaml["agents"][0]["owns"] = []
        with pytest.raises(ValidationError, match="at least one directory"):
            ProjectConfig(**sample_agents_yaml)

    def test_overlapping_dirs_rejected(self, sample_agents_yaml: dict) -> None:
        """Two agents owning src/api/ and src/api/routes/ rejected."""
        sample_agents_yaml["agents"][1]["owns"] = ["src/api/routes/", "src/components/"]
        with pytest.raises(ValidationError, match="Overlapping"):
            ProjectConfig(**sample_agents_yaml)

    def test_exact_duplicate_dirs_rejected(self, sample_agents_yaml: dict) -> None:
        """Two agents owning same dir rejected."""
        sample_agents_yaml["agents"][1]["owns"] = ["src/api/", "src/components/"]
        with pytest.raises(ValidationError, match="Overlapping"):
            ProjectConfig(**sample_agents_yaml)


class TestDuplicateAgentIds:
    """Tests for duplicate agent ID validation."""

    def test_duplicate_agent_ids_rejected(self, sample_agents_yaml: dict) -> None:
        """Two agents with same id rejected."""
        sample_agents_yaml["agents"][1]["id"] = "BACKEND"
        sample_agents_yaml["agents"][1]["owns"] = ["src/app/", "src/components/"]
        with pytest.raises(ValidationError, match="Duplicate agent"):
            ProjectConfig(**sample_agents_yaml)


class TestInvalidConfig:
    """Tests for invalid configuration handling."""

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        """Missing required fields raise ValidationError."""
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("project: test\n")  # missing required fields
        with pytest.raises(ValidationError):
            load_config(yaml_path)

    def test_gsd_mode_literal(self, sample_agents_yaml: dict) -> None:
        """Invalid gsd_mode value rejected."""
        sample_agents_yaml["agents"][0]["gsd_mode"] = "invalid"
        with pytest.raises(ValidationError):
            ProjectConfig(**sample_agents_yaml)
