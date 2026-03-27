"""Tests for Supervisor restart strategies and escalation."""

import asyncio

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


def _make_spec(child_id: str, restart_policy: RestartPolicy = RestartPolicy.PERMANENT) -> ChildSpec:
    """Create a minimal ChildSpec for testing."""
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
        restart_policy=restart_policy,
    )


class TestOneForOne:
    @pytest.mark.asyncio
    async def test_one_for_one_restarts_only_failed(self, tmp_path):
        """In one_for_one, only the failed child is restarted; siblings stay."""
        specs = [_make_spec("a"), _make_spec("b"), _make_spec("c")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        # Capture original container references
        original_a = sup.children["a"]
        original_c = sup.children["c"]

        # Fail child B
        await sup.children["b"].error()
        # Give the monitor task time to process the event
        await asyncio.sleep(0.1)

        # A and C should be the SAME objects (untouched)
        assert sup.children["a"] is original_a
        assert sup.children["c"] is original_c
        # B should be a NEW container in running state
        assert sup.children["b"] is not None
        assert sup.children["b"].state == "running"

        await sup.stop()


class TestAllForOne:
    @pytest.mark.asyncio
    async def test_all_for_one_restarts_all(self, tmp_path):
        """In all_for_one, all children are restarted when one fails."""
        specs = [_make_spec("a"), _make_spec("b"), _make_spec("c")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ALL_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        original_a = sup.children["a"]
        original_b = sup.children["b"]
        original_c = sup.children["c"]

        # Fail child B
        await sup.children["b"].error()
        await asyncio.sleep(0.1)

        # All children should be NEW containers
        assert sup.children["a"] is not original_a
        assert sup.children["b"] is not original_b
        assert sup.children["c"] is not original_c
        # All should be running
        assert sup.children["a"].state == "running"
        assert sup.children["b"].state == "running"
        assert sup.children["c"].state == "running"

        await sup.stop()


class TestRestForOne:
    @pytest.mark.asyncio
    async def test_rest_for_one_restarts_failed_and_later(self, tmp_path):
        """In rest_for_one, failed child + later children are restarted; earlier stay."""
        specs = [_make_spec("a"), _make_spec("b"), _make_spec("c")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.REST_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        original_a = sup.children["a"]
        original_b = sup.children["b"]
        original_c = sup.children["c"]

        # Fail child B
        await sup.children["b"].error()
        await asyncio.sleep(0.1)

        # A stays (earlier than B)
        assert sup.children["a"] is original_a
        # B and C are restarted (B failed, C is after B)
        assert sup.children["b"] is not original_b
        assert sup.children["c"] is not original_c
        assert sup.children["b"].state == "running"
        assert sup.children["c"].state == "running"

        await sup.stop()


class TestRestartPolicies:
    @pytest.mark.asyncio
    async def test_temporary_never_restarted(self, tmp_path):
        """TEMPORARY child is never restarted on failure."""
        specs = [_make_spec("a", RestartPolicy.TEMPORARY)]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        original_a = sup.children["a"]
        await sup.children["a"].error()
        await asyncio.sleep(0.1)

        # Container should be the same object still in errored state
        assert sup.children["a"] is original_a
        assert sup.children["a"].state == "errored"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_transient_restarted_on_error(self, tmp_path):
        """TRANSIENT child in errored state gets restarted."""
        specs = [_make_spec("a", RestartPolicy.TRANSIENT)]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        original_a = sup.children["a"]
        await sup.children["a"].error()
        await asyncio.sleep(0.1)

        # Should be restarted (new container)
        assert sup.children["a"] is not original_a
        assert sup.children["a"].state == "running"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_transient_not_restarted_on_normal_stop(self, tmp_path):
        """TRANSIENT child that stops normally is NOT restarted."""
        specs = [_make_spec("a", RestartPolicy.TRANSIENT)]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        original_a = sup.children["a"]
        await sup.children["a"].stop()
        await asyncio.sleep(0.1)

        # Should NOT be restarted -- same object, still stopped
        assert sup.children["a"] is original_a
        assert sup.children["a"].state == "stopped"

        await sup.stop()


class TestEscalation:
    @pytest.mark.asyncio
    async def test_escalation_on_intensity_exceeded(self, tmp_path):
        """Exhaust restart budget, 4th failure triggers escalation callback."""
        escalation_messages = []

        async def on_escalation(msg: str) -> None:
            escalation_messages.append(msg)

        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            max_restarts=3,
            window_seconds=600,
            on_escalation=on_escalation,
            data_dir=tmp_path,
        )
        await sup.start()

        # Trigger 4 failures (3 restarts + 1 that exceeds)
        for _ in range(4):
            if sup.children["a"].state == "running":
                await sup.children["a"].error()
                await asyncio.sleep(0.1)

        # Escalation should have been called
        assert len(escalation_messages) >= 1
        assert "test-sup" in escalation_messages[0]

        # Supervisor should stop after escalation
        # (children stopped as part of escalation)

    @pytest.mark.asyncio
    async def test_escalation_calls_parent(self, tmp_path):
        """Supervisor with parent escalates to parent on intensity exceeded."""
        parent_escalations = []

        class MockParent:
            async def handle_child_escalation(self, child_supervisor_id: str) -> None:
                parent_escalations.append(child_supervisor_id)

        parent = MockParent()
        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="child-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            max_restarts=3,
            window_seconds=600,
            parent=parent,
            data_dir=tmp_path,
        )
        await sup.start()

        # Trigger 4 failures
        for _ in range(4):
            if sup.children.get("a") and sup.children["a"].state == "running":
                await sup.children["a"].error()
                await asyncio.sleep(0.1)

        assert "child-sup" in parent_escalations
