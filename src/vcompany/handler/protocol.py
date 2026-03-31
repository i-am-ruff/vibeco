"""Handler protocols for agent message processing (D-01).

Defines three @runtime_checkable Protocol classes that describe how different
agent types process inbound Discord messages. All methods are async (the
codebase is async-native). Separate types enable isinstance checks even though
the interface shape is identical -- they have fundamentally different semantics.

SessionHandler: Interactive Claude Code session agents (tmux send_keys, idle/ready).
ConversationHandler: Piped claude -p --resume request-response pattern.
TransientHandler: Pure Python logic -- prefix matching, state machine, no Claude session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from vcompany.container.container import AgentContainer
    from vcompany.models.messages import MessageContext


@runtime_checkable
class SessionHandler(Protocol):
    """Handles messages for interactive Claude Code session agents.

    Used by GSD agents, task agents, continuous agents. These agents have a
    tmux session with Claude Code running -- messages are delivered via
    send_keys, and idle/ready signals drive task queue draining.

    Per D-01: handler protocols are orthogonal to transport.
    """

    async def handle_message(self, container: AgentContainer, context: MessageContext) -> None: ...
    async def on_start(self, container: AgentContainer) -> None: ...
    async def on_stop(self, container: AgentContainer) -> None: ...


@runtime_checkable
class ConversationHandler(Protocol):
    """Handles messages via piped claude -p --resume request-response pattern.

    Used by Strategist (CompanyAgent). Each inbound message triggers a
    subprocess call to claude with --resume, and the response is posted
    back to Discord.

    Per D-01: handler protocols are orthogonal to transport.
    """

    async def handle_message(self, container: AgentContainer, context: MessageContext) -> None: ...
    async def on_start(self, container: AgentContainer) -> None: ...
    async def on_stop(self, container: AgentContainer) -> None: ...


@runtime_checkable
class TransientHandler(Protocol):
    """Handles messages via pure Python logic -- no Claude session involved.

    Used by PM (FulltimeAgent). Message processing is prefix-based dispatch
    (e.g., [Phase Complete], [Task Completed]) with state machine transitions.
    No external subprocess or tmux interaction.

    Per D-01: handler protocols are orthogonal to transport.
    """

    async def handle_message(self, container: AgentContainer, context: MessageContext) -> None: ...
    async def on_start(self, container: AgentContainer) -> None: ...
    async def on_stop(self, container: AgentContainer) -> None: ...
