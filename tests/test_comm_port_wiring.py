"""Tests for NoopCommunicationPort and comm_port wiring through Supervisor/CompanyRoot."""

from __future__ import annotations

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.communication import CommunicationPort, NoopCommunicationPort
from vcompany.container.context import ContainerContext
from vcompany.supervisor.company_root import CompanyRoot
from vcompany.supervisor.supervisor import Supervisor
from vcompany.supervisor.strategies import RestartStrategy


def _make_spec(child_id: str) -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
    )


class TestNoopCommunicationPort:
    @pytest.mark.asyncio
    async def test_send_message_returns_true(self):
        """NoopCommunicationPort.send_message always returns True."""
        port = NoopCommunicationPort()
        result = await port.send_message("target-agent", "hello")
        assert result is True

    @pytest.mark.asyncio
    async def test_receive_message_returns_none(self):
        """NoopCommunicationPort.receive_message always returns None."""
        port = NoopCommunicationPort()
        result = await port.receive_message()
        assert result is None

    def test_satisfies_communication_port_protocol(self):
        """NoopCommunicationPort is an instance of CommunicationPort Protocol."""
        port = NoopCommunicationPort()
        assert isinstance(port, CommunicationPort)


class TestSupervisorCommPortWiring:
    @pytest.mark.asyncio
    async def test_supervisor_stores_comm_port(self, tmp_path):
        """Supervisor stores comm_port when provided in __init__."""
        port = NoopCommunicationPort()
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
            comm_port=port,
        )
        assert sup._comm_port is port

    @pytest.mark.asyncio
    async def test_supervisor_comm_port_none_by_default(self, tmp_path):
        """Supervisor._comm_port is None when not provided."""
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
        )
        assert sup._comm_port is None

    @pytest.mark.asyncio
    async def test_containers_created_with_non_none_comm_port(self, tmp_path):
        """Containers created via Supervisor._start_child have non-None comm_port."""
        port = NoopCommunicationPort()
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
            comm_port=port,
        )
        await sup.start()
        container = sup.children["a"]
        assert container.comm_port is port
        await sup.stop()

    @pytest.mark.asyncio
    async def test_company_root_add_project_passes_comm_port(self, tmp_path):
        """Containers in projects created by CompanyRoot have non-None comm_port."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps = await root.add_project("proj1", [_make_spec("a1")])
        container = ps.children["a1"]
        # CompanyRoot creates a NoopCommunicationPort internally
        assert container.comm_port is not None

        await root.stop()
