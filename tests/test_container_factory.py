"""Tests for container factory registry (TYPE-03/04/05 prerequisite)."""

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.factory import create_container, get_registry, register_agent_type


class StubContainer(AgentContainer):
    """Minimal subclass for testing factory dispatch."""

    pass


class AnotherStubContainer(AgentContainer):
    """Second subclass for multi-registration test."""

    pass


def _make_spec(agent_type: str = "test", child_id: str = "child-1") -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type=agent_type,
        context=ContainerContext(agent_id=child_id, agent_type=agent_type),
    )


class TestFactoryRegistry:
    def setup_method(self):
        """Clear registry between tests."""
        from vcompany.container import factory

        factory._REGISTRY.clear()

    def test_register_stores_mapping(self):
        """register_agent_type stores the class in the registry."""
        register_agent_type("test", StubContainer)
        registry = get_registry()
        assert "test" in registry
        assert registry["test"] is StubContainer

    def test_create_container_returns_registered_type(self, tmp_path):
        """create_container returns instance of registered subclass."""
        register_agent_type("test", StubContainer)
        spec = _make_spec("test")
        container = create_container(spec, data_dir=tmp_path)
        assert isinstance(container, StubContainer)

    def test_create_container_falls_back_to_base(self, tmp_path):
        """create_container returns base AgentContainer for unregistered type."""
        spec = _make_spec("unknown")
        container = create_container(spec, data_dir=tmp_path)
        assert type(container) is AgentContainer

    def test_multiple_types_registered(self, tmp_path):
        """Multiple agent types can be registered and created correctly."""
        register_agent_type("test", StubContainer)
        register_agent_type("another", AnotherStubContainer)

        spec_test = _make_spec("test")
        spec_another = _make_spec("another", child_id="child-2")

        container_test = create_container(spec_test, data_dir=tmp_path)
        container_another = create_container(spec_another, data_dir=tmp_path)

        assert isinstance(container_test, StubContainer)
        assert isinstance(container_another, AnotherStubContainer)

    def test_from_spec_called_with_registered_class(self, tmp_path):
        """Polymorphic from_spec: cls= is the registered class, not base."""
        register_agent_type("test", StubContainer)
        spec = _make_spec("test")
        container = create_container(spec, data_dir=tmp_path)
        # from_spec uses cls(), so the type proves polymorphic dispatch
        assert type(container) is StubContainer
        # Verify context was passed through correctly
        assert container.context.agent_id == "child-1"
        assert container.context.agent_type == "test"

    def test_get_registry_returns_copy(self):
        """get_registry returns a copy, not the internal dict."""
        register_agent_type("test", StubContainer)
        registry = get_registry()
        registry["hacked"] = AgentContainer
        assert "hacked" not in get_registry()


class TestFactoryAgentTypeRouting:
    """Tests for factory routing from AgentConfig.type (TYPE-04, TYPE-05)."""

    def setup_method(self):
        """Register default agent types before each test."""
        from vcompany.container import factory
        factory._REGISTRY.clear()
        from vcompany.container.factory import register_defaults
        register_defaults()

    def test_factory_routes_fulltime_type(self, tmp_path):
        """type='fulltime' AgentConfig produces FulltimeAgent via ContainerFactory."""
        from vcompany.agent.fulltime_agent import FulltimeAgent

        spec = ChildSpec(
            child_id="pm-1",
            agent_type="fulltime",
            context=ContainerContext(agent_id="pm-1", agent_type="fulltime"),
        )
        container = create_container(spec, data_dir=tmp_path)
        assert isinstance(container, FulltimeAgent)

    def test_factory_routes_company_type(self, tmp_path):
        """type='company' AgentConfig produces CompanyAgent via ContainerFactory."""
        from vcompany.agent.company_agent import CompanyAgent

        spec = ChildSpec(
            child_id="strategist-1",
            agent_type="company",
            context=ContainerContext(agent_id="strategist-1", agent_type="company"),
        )
        container = create_container(spec, data_dir=tmp_path)
        assert isinstance(container, CompanyAgent)
