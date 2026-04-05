"""Typed schema for model-routing.yaml.

This file defines the current provider/model routing policy and the escalation
chains that move work from cheap lanes to premium lanes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ProviderConfig(BaseModel):
    """Configuration for a model provider."""

    auth: Literal["api_key"]
    notes: str = ""


class ModelProfile(BaseModel):
    """Named route profile for a provider/model pair."""

    provider: str
    model: str
    purpose: str
    max_attempts: int = Field(default=1, ge=1)
    allowed_actions: list[str] = Field(default_factory=list)


class EscalationChain(BaseModel):
    """Ordered escalation path for a class of tasks."""

    steps: list[str] = Field(min_length=1)
    terminal: Literal["human"] = "human"


class SituationRoute(BaseModel):
    """Situation classifier output mapped to a profile and escalation chain."""

    description: str
    profile: str
    chain: str
    when: list[str] = Field(default_factory=list)


class RoutingThresholds(BaseModel):
    """Numeric thresholds used by deterministic routing logic."""

    default_max_files: int = Field(default=5, ge=1)
    default_max_changed_lines: int = Field(default=600, ge=1)
    reviewer_max_files: int = Field(default=8, ge=1)
    reviewer_max_changed_lines: int = Field(default=1000, ge=1)
    worker_failed_attempts_before_reviewer: int = Field(default=1, ge=1)
    worker_failed_attempts_before_premium: int = Field(default=2, ge=1)
    premium_failed_attempts_before_strategist: int = Field(default=1, ge=1)
    strategist_failed_attempts_before_human: int = Field(default=1, ge=1)


class ModelAlias(BaseModel):
    """Pending cutover from a current model to a candidate model."""

    current: str
    candidate: str
    cutover_requirements: list[str] = Field(default_factory=list)


class ModelRoutingConfig(BaseModel):
    """Top-level schema for model-routing.yaml."""

    version: int = 1
    providers: dict[str, ProviderConfig]
    profiles: dict[str, ModelProfile]
    escalation_chains: dict[str, EscalationChain]
    situations: dict[str, SituationRoute]
    thresholds: RoutingThresholds = Field(default_factory=RoutingThresholds)
    high_risk_paths: list[str] = Field(default_factory=list)
    strategic_triggers: list[str] = Field(default_factory=list)
    model_aliases: dict[str, ModelAlias] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "ModelRoutingConfig":
        """Ensure all named references point at defined profiles/chains/providers."""
        for profile_name, profile in self.profiles.items():
            if profile.provider not in self.providers:
                raise ValueError(
                    f"profile '{profile_name}' references unknown provider '{profile.provider}'"
                )

        for chain_name, chain in self.escalation_chains.items():
            for step in chain.steps:
                if step not in self.profiles:
                    raise ValueError(
                        f"escalation chain '{chain_name}' references unknown profile '{step}'"
                    )

        for situation_name, situation in self.situations.items():
            if situation.profile not in self.profiles:
                raise ValueError(
                    f"situation '{situation_name}' references unknown profile '{situation.profile}'"
                )
            if situation.chain not in self.escalation_chains:
                raise ValueError(
                    f"situation '{situation_name}' references unknown chain '{situation.chain}'"
                )

        for alias_name, alias in self.model_aliases.items():
            if alias_name not in self.profiles:
                raise ValueError(
                    f"model alias '{alias_name}' must match a defined profile name"
                )
            if self.profiles[alias_name].model != alias.current:
                raise ValueError(
                    f"model alias '{alias_name}' current model '{alias.current}' "
                    f"does not match profile model '{self.profiles[alias_name].model}'"
                )

        return self

    def profile_for_situation(self, situation_name: str) -> ModelProfile:
        """Return the primary profile for a named situation."""
        return self.profiles[self.situations[situation_name].profile]

    def escalation_steps_for_situation(self, situation_name: str) -> list[str]:
        """Return the ordered profile names for a named situation."""
        situation = self.situations[situation_name]
        return list(self.escalation_chains[situation.chain].steps)


def load_model_routing(config_path: Path) -> ModelRoutingConfig:
    """Load and validate model-routing.yaml."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return ModelRoutingConfig(**raw)
