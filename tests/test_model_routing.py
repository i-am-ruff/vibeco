"""Tests for model routing policy schema."""

from pathlib import Path

import pytest

from vcompany.models.model_routing import ModelRoutingConfig, load_model_routing


def test_load_model_routing_from_repo_file() -> None:
    """Repository model-routing.yaml parses successfully."""
    config = load_model_routing(Path("model-routing.yaml"))

    assert config.version == 1
    assert config.profile_for_situation("project_kickoff").model == "claude-opus-4.6"
    assert config.profile_for_situation("routine_coding").model == "deepseek-chat"
    assert config.escalation_steps_for_situation("routine_coding") == [
        "worker_default",
        "reviewer",
        "premium_coder",
        "strategist",
    ]


def test_invalid_chain_reference_rejected() -> None:
    """Unknown profile in escalation chain should fail validation."""
    with pytest.raises(ValueError, match="unknown profile"):
        ModelRoutingConfig(
            providers={"anthropic": {"auth": "api_key"}},
            profiles={
                "strategist": {
                    "provider": "anthropic",
                    "model": "claude-opus-4.6",
                    "purpose": "strategy",
                }
            },
            escalation_chains={"coding": {"steps": ["missing"]}},
            situations={
                "kickoff": {
                    "description": "kickoff",
                    "profile": "strategist",
                    "chain": "coding",
                }
            },
        )


def test_invalid_situation_profile_rejected() -> None:
    """Unknown profile in a situation should fail validation."""
    with pytest.raises(ValueError, match="unknown profile"):
        ModelRoutingConfig(
            providers={"anthropic": {"auth": "api_key"}},
            profiles={
                "strategist": {
                    "provider": "anthropic",
                    "model": "claude-opus-4.6",
                    "purpose": "strategy",
                }
            },
            escalation_chains={"coding": {"steps": ["strategist"]}},
            situations={
                "kickoff": {
                    "description": "kickoff",
                    "profile": "missing",
                    "chain": "coding",
                }
            },
        )


def test_alias_must_match_profile_model() -> None:
    """Alias current model must match the referenced profile."""
    with pytest.raises(ValueError, match="does not match profile model"):
        ModelRoutingConfig(
            providers={"deepseek": {"auth": "api_key"}},
            profiles={
                "worker_default": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "purpose": "default worker",
                }
            },
            escalation_chains={"coding": {"steps": ["worker_default"]}},
            situations={
                "routine_coding": {
                    "description": "routine coding",
                    "profile": "worker_default",
                    "chain": "coding",
                }
            },
            model_aliases={
                "worker_default": {
                    "current": "DeepSeek V4",
                    "candidate": "DeepSeek V5",
                }
            },
        )
