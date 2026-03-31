"""Handler protocols for worker-side message processing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from vco_worker.channel.messages import InboundMessage
    from vco_worker.container.container import WorkerContainer


@runtime_checkable
class SessionHandler(Protocol):
    """Handles messages for interactive Claude Code session agents.

    Used by GSD agents, task agents, continuous agents. These agents have a
    tmux session with Claude Code running -- messages are delivered via
    send_keys, and idle/ready signals drive task queue draining.
    """

    async def handle_message(self, container: WorkerContainer, message: InboundMessage) -> None: ...
    async def on_start(self, container: WorkerContainer) -> None: ...
    async def on_stop(self, container: WorkerContainer) -> None: ...


@runtime_checkable
class ConversationHandler(Protocol):
    """Handles messages via piped claude -p --resume request-response pattern.

    Used by Strategist (CompanyAgent). Each inbound message triggers a
    subprocess call to claude with --resume, and the response is posted
    back via channel protocol.
    """

    async def handle_message(self, container: WorkerContainer, message: InboundMessage) -> None: ...
    async def on_start(self, container: WorkerContainer) -> None: ...
    async def on_stop(self, container: WorkerContainer) -> None: ...


@runtime_checkable
class TransientHandler(Protocol):
    """Handles messages via pure Python logic -- no Claude session involved.

    Used by PM (FulltimeAgent). Message processing is prefix-based dispatch
    (e.g., [Phase Complete], [Task Completed]) with state machine transitions.
    No external subprocess or tmux interaction.
    """

    async def handle_message(self, container: WorkerContainer, message: InboundMessage) -> None: ...
    async def on_start(self, container: WorkerContainer) -> None: ...
    async def on_stop(self, container: WorkerContainer) -> None: ...
