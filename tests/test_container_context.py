"""Tests for ContainerContext — CONT-03."""

from vcompany.container.context import ContainerContext


class TestContainerContext:
    """CONT-03: Container context holds all required fields."""

    def test_accepts_all_required_fields(self):
        ctx = ContainerContext(
            agent_id="agent-1",
            agent_type="gsd",
            parent_id="proj-1",
            project_id="myproject",
            owned_dirs=["src/api"],
            gsd_mode="full",
            system_prompt="You are an agent",
        )
        assert ctx.agent_id == "agent-1"
        assert ctx.agent_type == "gsd"
        assert ctx.parent_id == "proj-1"
        assert ctx.project_id == "myproject"
        assert ctx.owned_dirs == ["src/api"]
        assert ctx.gsd_mode == "full"
        assert ctx.system_prompt == "You are an agent"

    def test_defaults(self):
        ctx = ContainerContext(agent_id="agent-1", agent_type="gsd")
        assert ctx.parent_id is None
        assert ctx.project_id is None
        assert ctx.owned_dirs == []
        assert ctx.gsd_mode == "full"
        assert ctx.system_prompt == ""

    def test_serializable_to_dict(self):
        ctx = ContainerContext(agent_id="agent-1", agent_type="continuous")
        d = ctx.model_dump()
        assert isinstance(d, dict)
        assert d["agent_id"] == "agent-1"
        assert d["agent_type"] == "continuous"
