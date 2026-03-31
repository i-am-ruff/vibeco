"""Tests for ChildSpec model and ChildSpecRegistry (CONT-05)."""

from vcompany.supervisor.child_spec import ChildSpec, ChildSpecRegistry, RestartPolicy
from vcompany.supervisor.child_spec import ContainerContext


def _make_context(agent_id: str = "agent-1", agent_type: str = "gsd") -> ContainerContext:
    """Helper to create a ContainerContext for tests."""
    return ContainerContext(agent_id=agent_id, agent_type=agent_type)


# --- RestartPolicy enum ---


def test_restart_policy_permanent() -> None:
    assert RestartPolicy.PERMANENT.value == "permanent"


def test_restart_policy_temporary() -> None:
    assert RestartPolicy.TEMPORARY.value == "temporary"


def test_restart_policy_transient() -> None:
    assert RestartPolicy.TRANSIENT.value == "transient"


# --- ChildSpec model ---


def test_child_spec_creation() -> None:
    ctx = _make_context()
    spec = ChildSpec(child_id="agent-1", agent_type="gsd", context=ctx)
    assert spec.child_id == "agent-1"
    assert spec.agent_type == "gsd"
    assert spec.context == ctx


def test_child_spec_defaults() -> None:
    ctx = _make_context()
    spec = ChildSpec(child_id="agent-1", agent_type="gsd", context=ctx)
    assert spec.restart_policy == RestartPolicy.PERMANENT
    assert spec.max_restarts == 3
    assert spec.restart_window_seconds == 600


def test_child_spec_serializable() -> None:
    ctx = _make_context()
    spec = ChildSpec(child_id="agent-1", agent_type="gsd", context=ctx)
    data = spec.model_dump()
    assert isinstance(data, dict)
    assert data["child_id"] == "agent-1"
    assert data["restart_policy"] == "permanent"


# --- ChildSpecRegistry ---


def test_registry_register_and_get() -> None:
    registry = ChildSpecRegistry()
    spec = ChildSpec(child_id="agent-1", agent_type="gsd", context=_make_context())
    registry.register(spec)
    assert registry.get("agent-1") is spec


def test_registry_get_nonexistent() -> None:
    registry = ChildSpecRegistry()
    assert registry.get("nonexistent") is None


def test_registry_all_specs() -> None:
    registry = ChildSpecRegistry()
    for i in range(3):
        ctx = _make_context(agent_id=f"agent-{i}")
        spec = ChildSpec(child_id=f"agent-{i}", agent_type="gsd", context=ctx)
        registry.register(spec)
    assert len(registry.all_specs()) == 3


def test_registry_register_overwrites() -> None:
    registry = ChildSpecRegistry()
    ctx = _make_context()
    spec1 = ChildSpec(child_id="agent-1", agent_type="gsd", context=ctx)
    spec2 = ChildSpec(child_id="agent-1", agent_type="continuous", context=ctx)
    registry.register(spec1)
    registry.register(spec2)
    result = registry.get("agent-1")
    assert result is not None
    assert result.agent_type == "continuous"


def test_registry_unregister() -> None:
    registry = ChildSpecRegistry()
    spec = ChildSpec(child_id="agent-1", agent_type="gsd", context=_make_context())
    registry.register(spec)
    registry.unregister("agent-1")
    assert registry.get("agent-1") is None
