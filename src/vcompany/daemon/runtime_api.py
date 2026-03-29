"""RuntimeAPI -- typed gateway to CompanyRoot operations.

All methods are async. No discord.py imports. Uses CommunicationPort
for any outbound messaging. The daemon layer accesses CompanyRoot
exclusively through this class.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from vcompany.daemon.comm import (
    CommunicationPort,
    CreateChannelPayload,
    SendMessagePayload,
)

if TYPE_CHECKING:
    from vcompany.agent.company_agent import CompanyAgent
    from vcompany.agent.continuous_agent import ContinuousAgent
    from vcompany.agent.fulltime_agent import FulltimeAgent
    from vcompany.agent.gsd_agent import GsdAgent
    from vcompany.autonomy.backlog import BacklogQueue
    from vcompany.autonomy.project_state import ProjectStateManager
    from vcompany.container.child_spec import ChildSpec
    from vcompany.container.context import ContainerContext
    from vcompany.models.config import ProjectConfig
    from vcompany.supervisor.company_root import CompanyRoot
    from vcompany.supervisor.project_supervisor import ProjectSupervisor

logger = logging.getLogger("vcompany.daemon.runtime_api")


class RuntimeAPI:
    """Typed gateway to CompanyRoot operations.

    Provides async methods for all agent lifecycle and status operations.
    Uses CommunicationPort (via lazy getter) for outbound messaging --
    no discord.py imports allowed in this module.
    """

    def __init__(
        self,
        company_root: CompanyRoot,
        comm_port_getter: Callable[[], CommunicationPort],
    ) -> None:
        self._root = company_root
        self._get_comm = comm_port_getter
        self._channel_ids: dict[str, str] = {}
        self._project_config: ProjectConfig | None = None
        self._project_dir: Path | None = None
        self._strategist_container: CompanyAgent | None = None

    # ── Core lifecycle methods ────────────────────────────────────────

    async def hire(
        self, agent_id: str, template: str = "generic"
    ) -> str:
        """Hire a company-level agent with optional channel creation.

        Creates a task channel via CommunicationPort before hiring,
        then delegates to CompanyRoot.hire() (no guild param -- channel
        creation is handled through the communication port).

        Returns:
            The agent_id of the hired container.
        """
        # Create channel via comm port (platform-agnostic)
        result = await self._get_comm().create_channel(
            CreateChannelPayload(
                category_name="vco-tasks",
                channel_name=f"task-{agent_id}",
            )
        )
        if result is not None:
            self._channel_ids[f"task-{agent_id}"] = result.channel_id
            logger.info(
                "Created channel task-%s (id=%s)", agent_id, result.channel_id
            )

        container = await self._root.hire(agent_id, template=template)
        return container.context.agent_id

    async def give_task(self, agent_id: str, task: str) -> None:
        """Assign a task to an existing agent.

        Finds the container by agent_id across company agents and
        project supervisors, then calls give_task on it.

        Raises:
            KeyError: If agent_id is not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        await container.give_task(task)

    async def dismiss(self, agent_id: str) -> None:
        """Dismiss (stop) a company-level agent.

        Delegates to CompanyRoot.dismiss().

        Raises:
            KeyError: If agent_id is not found in company agents.
        """
        await self._root.dismiss(agent_id)

    async def status(self) -> dict:
        """Return a status summary of projects and company agents.

        Returns:
            Dict with 'projects' (project_id -> agent count) and
            'company_agents' (list of agent IDs).
        """
        return {
            "projects": {
                pid: {"agents": len(ps.children)}
                for pid, ps in self._root.projects.items()
            },
            "company_agents": list(self._root._company_agents.keys()),
        }

    async def health_tree(self) -> dict:
        """Return the full company health tree as a dict.

        Calls CompanyRoot.health_tree() and serializes to dict via
        pydantic model_dump().
        """
        return self._root.health_tree().model_dump()

    def register_channels(self, channels: dict[str, str]) -> None:
        """Register channel name -> ID mappings.

        Used during bot startup to populate known channel IDs.

        Args:
            channels: Dict of channel_name -> channel_id.
        """
        self._channel_ids.update(channels)

    def get_channel_id(self, name: str) -> str | None:
        """Look up a channel ID by name.

        Returns:
            The channel ID string, or None if not registered.
        """
        return self._channel_ids.get(name)

    # ── Category A: Alert/Notification callbacks ──────────────────────

    async def _on_escalation(self, msg: str) -> None:
        """Closure #1: escalation alert."""
        alerts_id = self.get_channel_id("alerts")
        if alerts_id:
            await self._get_comm().send_message(
                SendMessagePayload(channel_id=alerts_id, content=f"ESCALATION: {msg}")
            )

    async def _on_degraded(self) -> None:
        """Closure #2: degraded mode alert."""
        alerts_id = self.get_channel_id("alerts")
        if alerts_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=alerts_id,
                    content="WARNING: System entered degraded mode (Claude API unreachable). "
                    "New dispatches blocked. Will auto-recover.",
                )
            )

    async def _on_recovered(self) -> None:
        """Closure #3: recovery alert."""
        alerts_id = self.get_channel_id("alerts")
        if alerts_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=alerts_id,
                    content="RECOVERED: System recovered from degraded mode. "
                    "Claude API reachable. Normal operations resumed.",
                )
            )

    async def _on_trigger_integration_review(self) -> None:
        """Closure #4: integration review notification."""
        alerts_id = self.get_channel_id("alerts")
        if alerts_id and self._project_config:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=alerts_id,
                    content=f"[PM] Integration review requested for project "
                    f"{self._project_config.project}. "
                    "Please review agent branches for merge readiness.",
                )
            )

    async def _on_send_intervention(self, agent_id: str, message: str) -> None:
        """Closure #5: PM intervention message to agent channel."""
        # Try agent's own channel first, fall back to alerts
        agent_ch_id = self.get_channel_id(agent_id)
        if agent_ch_id:
            await self._get_comm().send_message(
                SendMessagePayload(channel_id=agent_ch_id, content=f"[PM] {message}")
            )
        else:
            alerts_id = self.get_channel_id("alerts")
            if alerts_id:
                await self._get_comm().send_message(
                    SendMessagePayload(channel_id=alerts_id, content=f"[PM] {message}")
                )

    # ── Category B: Strategist response callback ─────────────────────

    async def _on_strategist_response(self, response: str, channel_id: int) -> None:
        """Closure #6: post strategist response to channel via CommunicationPort."""
        ch_id = str(channel_id)
        if len(response) > 2000:
            remaining = response
            while remaining:
                chunk = remaining[:2000]
                await self._get_comm().send_message(
                    SendMessagePayload(channel_id=ch_id, content=chunk)
                )
                remaining = remaining[2000:]
        else:
            await self._get_comm().send_message(
                SendMessagePayload(channel_id=ch_id, content=response)
            )

    # ── Category C: PM event routing (internal, no Discord) ──────────

    def _make_pm_event_sink(self, pm_container: FulltimeAgent) -> Callable:
        """Closure #10: PM event sink."""

        async def pm_event_sink(event: dict[str, Any]) -> None:
            await pm_container.post_event(event)

        return pm_event_sink

    def _make_gsd_cb(self, sink: Callable) -> Callable:
        """Closure #11: GSD phase transition -> PM event."""

        async def _cb(agent_id: str, from_phase: str, to_phase: str) -> None:
            await sink(
                {
                    "type": "gsd_transition",
                    "agent_id": agent_id,
                    "from_phase": from_phase,
                    "to_phase": to_phase,
                }
            )

        return _cb

    def _make_briefing_cb(self, sink: Callable) -> Callable:
        """Closure #12: briefing -> PM event."""

        async def _cb(agent_id: str, content: str) -> None:
            await sink(
                {
                    "type": "briefing",
                    "agent_id": agent_id,
                    "content": content,
                }
            )

        return _cb

    # ── Category D: Review gate callbacks ─────────────────────────────

    async def _post_review_request(self, agent_id: str, stage: str) -> None:
        """Closure #13: post review request via CommunicationPort (replaces PlanReviewCog.post_review_request)."""
        review_ch_id = self.get_channel_id("plan-review")
        if review_ch_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=review_ch_id,
                    content=f"[Review Request] Agent {agent_id} requests review at stage: {stage}",
                )
            )

    async def _dispatch_pm_review(self, agent_id: str, stage: str) -> None:
        """Closure #14: dispatch PM review via CommunicationPort."""
        review_ch_id = self.get_channel_id("plan-review")
        if review_ch_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=review_ch_id,
                    content=f"[PM Review] Agent {agent_id} PM review at stage: {stage}",
                )
            )

    # ── Category E: PM action callbacks ───────────────────────────────

    async def _on_assign_task(
        self, agent_id: str, item: Any, project_sup: ProjectSupervisor
    ) -> None:
        """Closure #15: assign task to GSD agent."""
        from vcompany.agent.gsd_agent import GsdAgent

        for child in project_sup.children.values():
            if isinstance(child, GsdAgent) and child.context.agent_id == agent_id:
                await child.set_assignment(item.model_dump())
                break

    async def _on_recruit_agent(
        self,
        spec: Any,
        project_sup: ProjectSupervisor,
        pm_event_sink: Callable,
    ) -> None:
        """Closure #16: recruit new agent into project."""
        from vcompany.agent.continuous_agent import ContinuousAgent
        from vcompany.agent.gsd_agent import GsdAgent

        await project_sup.add_child_spec(spec)
        new_child = project_sup.children.get(spec.child_id)
        if isinstance(new_child, GsdAgent):
            new_child._on_phase_transition = self._make_gsd_cb(pm_event_sink)
            # Review request wiring
            def _make_review_cb(api: RuntimeAPI) -> Callable:
                async def _cb(agent_id: str, stage: str) -> None:
                    await api._post_review_request(agent_id, stage)

                return _cb

            new_child._on_review_request = _make_review_cb(self)
        elif isinstance(new_child, ContinuousAgent):
            new_child._on_briefing = self._make_briefing_cb(pm_event_sink)
            new_child._request_delegation = project_sup.handle_delegation_request

    async def _on_remove_agent(
        self, agent_id: str, project_sup: ProjectSupervisor
    ) -> None:
        """Closure #17: remove agent from project."""
        await project_sup.remove_child(agent_id)

    async def _on_escalate_to_strategist(
        self, agent_id: str, question: str, score: float
    ) -> str | None:
        """Closure #18: route PM escalation to Strategist via CompanyAgent."""
        if self._strategist_container is None:
            return None
        future: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        await self._strategist_container.post_event(
            {
                "type": "pm_escalation",
                "agent_id": agent_id,
                "question": question,
                "confidence": score,
                "_response_future": future,
            }
        )
        return await future

    # ── Category F: Inbound relay methods (COMM-04/COMM-05) ──────────

    async def relay_strategist_message(
        self, user_message: str, channel_id: str, user_name: str = "user"
    ) -> None:
        """COMM-04 receive path: relay inbound user message to Strategist.

        Called by StrategistCog.on_message instead of calling CompanyAgent.post_event directly.
        This keeps the bot cog decoupled from agent container internals.
        """
        if self._strategist_container is None:
            logger.warning("relay_strategist_message: no strategist container")
            return
        await self._strategist_container.post_event(
            {
                "type": "user_message",
                "content": user_message,
                "channel_id": channel_id,
                "user_name": user_name,
            }
        )

    async def relay_strategist_escalation_reply(
        self, reply_text: str, escalation_message_id: str
    ) -> None:
        """COMM-04 receive path: relay owner reply to a pending escalation.

        Called by StrategistCog when owner replies to an escalation message.
        """
        if self._strategist_container is None:
            return
        await self._strategist_container.post_event(
            {
                "type": "escalation_reply",
                "reply": reply_text,
                "escalation_message_id": escalation_message_id,
            }
        )

    async def handle_plan_approval(self, agent_id: str, plan_path: str) -> None:
        """COMM-05 receive path: handle plan approval from Discord button click.

        Called by PlanReviewCog._handle_approval instead of calling plan_reviewer directly.
        Routes through daemon so review state machine stays in daemon context.
        """
        from vcompany.agent.gsd_agent import GsdAgent

        # Notify plan-review channel
        review_ch_id = self.get_channel_id("plan-review")
        if review_ch_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=review_ch_id,
                    content=f"Plan **approved** for `{agent_id}`: `{Path(plan_path).name}`",
                )
            )
        # Trigger execution via GSD agent resume (if applicable)
        container = await self._root._find_container(agent_id)
        if container is not None and isinstance(container, GsdAgent):
            await container.post_event({"type": "plan_approved", "plan_path": plan_path})

    async def handle_plan_rejection(
        self, agent_id: str, plan_path: str, feedback: str
    ) -> None:
        """COMM-05 receive path: handle plan rejection from Discord button click.

        Called by PlanReviewCog._handle_rejection instead of calling plan_reviewer directly.
        Routes through daemon so review state machine stays in daemon context.
        """
        from vcompany.agent.gsd_agent import GsdAgent

        review_ch_id = self.get_channel_id("plan-review")
        if review_ch_id:
            await self._get_comm().send_message(
                SendMessagePayload(
                    channel_id=review_ch_id,
                    content=f"Plan **rejected** for `{agent_id}`: `{Path(plan_path).name}`\nFeedback: {feedback}",
                )
            )
        # Send feedback to agent via event
        container = await self._root._find_container(agent_id)
        if container is not None and isinstance(container, GsdAgent):
            feedback_cmd = (
                f"Your plan {Path(plan_path).name} was rejected. "
                f"Feedback: {feedback}. Please revise the plan."
            )
            await container.post_event(
                {"type": "plan_rejected", "plan_path": plan_path, "feedback": feedback_cmd}
            )

    # ── new_project: replaces on_ready project initialization ─────────

    async def new_project(
        self,
        project_config: ProjectConfig,
        project_dir: Path,
        persona_path: Path | None = None,
    ) -> None:
        """Initialize a project: Strategist, supervision tree, PM wiring.

        Replaces the entire project-only section of on_ready() (lines 206-614).
        CRITICAL: PM event sink must be wired LAST (Research Pitfall 2).
        """
        from vcompany.agent.company_agent import CompanyAgent
        from vcompany.agent.continuous_agent import ContinuousAgent
        from vcompany.agent.fulltime_agent import FulltimeAgent
        from vcompany.agent.gsd_agent import GsdAgent
        from vcompany.autonomy.backlog import BacklogQueue
        from vcompany.autonomy.project_state import ProjectStateManager
        from vcompany.container.child_spec import ChildSpec
        from vcompany.container.context import ContainerContext

        self._project_config = project_config
        self._project_dir = project_dir

        # 1. Add Strategist as company-level agent
        strategist_ctx = ContainerContext(
            agent_id="strategist",
            agent_type="company",
            parent_id="company-root",
            project_id=None,
        )
        strategist_spec = ChildSpec(
            child_id="strategist",
            agent_type="company",
            context=strategist_ctx,
        )
        strategist_container = await self._root.add_company_agent(strategist_spec)

        # Wire Strategist conversation and callbacks
        if isinstance(strategist_container, CompanyAgent):
            self._strategist_container = strategist_container
            strategist_container.initialize_conversation(persona_path)
            strategist_container._on_response = self._on_strategist_response
            strategist_container._on_hire = self.hire
            strategist_container._on_give_task = self.give_task
            strategist_container._on_dismiss = self.dismiss

        # 2. Build child specs from agents.yaml
        specs = []
        for agent_cfg in project_config.agents:
            ctx = ContainerContext(
                agent_id=agent_cfg.id,
                agent_type=agent_cfg.type,
                parent_id="project-supervisor",
                project_id=project_config.project,
                owned_dirs=agent_cfg.owns,
                gsd_mode=agent_cfg.gsd_mode,
                system_prompt=agent_cfg.system_prompt,
                gsd_command="/gsd:discuss-phase 1" if agent_cfg.type == "gsd" else None,
                uses_tmux=agent_cfg.type in ("gsd", "continuous"),
            )
            specs.append(
                ChildSpec(child_id=agent_cfg.id, agent_type=ctx.agent_type, context=ctx)
            )

        project_sup = await self._root.add_project(
            project_id=project_config.project,
            child_specs=specs,
        )

        # 3. Wire PM backlog and project state
        pm_container: FulltimeAgent | None = None
        for child in project_sup.children.values():
            if isinstance(child, FulltimeAgent):
                pm_container = child
                break

        pm_event_sink: Callable | None = None
        if pm_container is not None:
            backlog = BacklogQueue(pm_container.memory)
            await backlog.load()
            state_mgr = ProjectStateManager(backlog, pm_container.memory)
            pm_container.backlog = backlog
            pm_container._project_state = state_mgr

            pm_event_sink = self._make_pm_event_sink(pm_container)

            # Wire GSD transitions and briefings
            for child in project_sup.children.values():
                if isinstance(child, GsdAgent):
                    child._on_phase_transition = self._make_gsd_cb(pm_event_sink)
                elif isinstance(child, ContinuousAgent):
                    child._on_briefing = self._make_briefing_cb(pm_event_sink)
                    child._request_delegation = project_sup.handle_delegation_request

        # 4. Wire review gate callbacks
        for child in project_sup.children.values():
            if isinstance(child, GsdAgent):

                def _make_review_cb(api: RuntimeAPI) -> Callable:
                    async def _cb(agent_id: str, stage: str) -> None:
                        await api._post_review_request(agent_id, stage)

                    return _cb

                child._on_review_request = _make_review_cb(self)

        if pm_container is not None:

            async def _gsd_review_cb(agent_id: str, stage: str) -> None:
                await self._dispatch_pm_review(agent_id, stage)

            pm_container._on_gsd_review = _gsd_review_cb

        # 5. Wire PM action callbacks
        if pm_container is not None:

            # Assign task
            async def _assign(agent_id: str, item: Any) -> None:
                await self._on_assign_task(agent_id, item, project_sup)

            pm_container._on_assign_task = _assign

            pm_container._on_trigger_integration_review = (
                self._on_trigger_integration_review
            )

            # Recruit agent
            async def _recruit(spec: Any) -> None:
                await self._on_recruit_agent(spec, project_sup, pm_event_sink)

            pm_container._on_recruit_agent = _recruit

            # Remove agent
            async def _remove(agent_id: str) -> None:
                await self._on_remove_agent(agent_id, project_sup)

            pm_container._on_remove_agent = _remove

            # Escalate to strategist
            pm_container._on_escalate_to_strategist = self._on_escalate_to_strategist

            # Send intervention
            pm_container._on_send_intervention = self._on_send_intervention

        # 6. LAST: Wire PM event sink (Research Pitfall 2 -- must be after all callbacks)
        if pm_container is not None and pm_event_sink is not None:
            project_sup.set_pm_event_sink(pm_event_sink)
