"""RuntimeAPI -- typed gateway to CompanyRoot operations.

All methods are async. No discord.py imports. Uses CommunicationPort
for any outbound messaging. The daemon layer accesses CompanyRoot
exclusively through this class.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from vcompany.daemon.comm import (
    CommunicationPort,
    CreateChannelPayload,
    SendMessagePayload,
)

if TYPE_CHECKING:
    from vcompany.models.config import ProjectConfig
    from vcompany.supervisor.company_root import CompanyRoot

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
        self._mention_router: Any | None = None

    def set_mention_router(self, router: Any) -> None:
        """Store reference to MentionRouterCog for agent handle registration.

        Args:
            router: MentionRouterCog instance (typed as Any to avoid discord.py import).
        """
        self._mention_router = router

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

    # ── Bot cog delegation methods ──────────────────────────────────

    async def dispatch(self, agent_id: str) -> None:
        """Start or restart an agent container.

        Finds the container by agent_id, then calls start() on it.
        If the container is already running, calls restart().

        Raises:
            KeyError: If agent_id is not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        if container.state in ("running", "idle"):
            await container.restart()
        else:
            await container.start()

    async def kill(self, agent_id: str) -> None:
        """Stop an agent container.

        Finds the container by agent_id, then calls stop().

        Raises:
            KeyError: If agent_id is not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        await container.stop()

    async def relaunch(self, agent_id: str) -> None:
        """Relaunch an agent container (stop then let supervisor restart).

        Finds the container by agent_id, calls stop(). The supervisor's
        restart policy handles bringing it back.

        Raises:
            KeyError: If agent_id is not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        await container.stop()

    async def new_project_from_name(self, name: str) -> None:
        """Initialize a project by name -- loads config, creates structure, clones repos, starts supervision.

        Called by bot /new-project command. Handles all business logic that was
        previously inline in CommandsCog.

        Raises:
            FileNotFoundError: If agents.yaml not found.
        """
        from vcompany.shared.paths import PROJECTS_BASE
        from vcompany.models.config import load_config
        from vcompany.shared.file_ops import write_atomic
        from vcompany.shared.templates import render_template

        project_dir = PROJECTS_BASE / name

        if not (project_dir / "agents.yaml").exists():
            raise FileNotFoundError(
                f"No agents.yaml found at {project_dir}/agents.yaml"
            )

        config = load_config(project_dir / "agents.yaml")

        # Create project directory structure
        context_dir = project_dir / "context"
        agents_dir = context_dir / "agents"
        context_dir.mkdir(parents=True, exist_ok=True)
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Generate agent system prompts
        for agent in config.agents:
            prompt_content = render_template(
                "agent_prompt.md.j2",
                agent_id=agent.id,
                role=agent.role,
                project_name=config.project,
                owned_dirs=agent.owns,
                consumes=agent.consumes,
                milestone_name="TBD",
                milestone_scope="See MILESTONE-SCOPE.md",
            )
            write_atomic(agents_dir / f"{agent.id}.md", prompt_content)

        # Clone repos if needed
        clones_dir = project_dir / "clones"
        needs_clone = not clones_dir.exists() or not any(clones_dir.iterdir())
        if needs_clone:
            import shutil

            from vcompany.cli.clone_cmd import _deploy_artifacts
            from vcompany.git import ops as git

            clones_dir.mkdir(exist_ok=True)
            for agent in config.agents:
                clone_dir = clones_dir / agent.id
                if clone_dir.exists():
                    continue
                result = await asyncio.to_thread(git.clone, config.repo, clone_dir)
                if not result.success:
                    logger.error("Error cloning for %s: %s", agent.id, result.stderr)
                    continue
                await asyncio.to_thread(
                    git.checkout_new_branch, f"agent/{agent.id.lower()}", clone_dir
                )
                await asyncio.to_thread(_deploy_artifacts, clone_dir, agent, config, project_dir)

        # Wire project through supervision tree
        await self.new_project(config, project_dir, persona_path=None)

    async def remove_project(self, project_name: str) -> None:
        """Remove a project from CompanyRoot.

        Unregisters agent handles from MentionRouterCog, stops all agents
        in the project, and removes the project supervisor.

        Raises:
            KeyError: If project_name is not found.
        """
        # Unregister agent handles before removing project
        if self._mention_router:
            project_sup = self._root.projects.get(project_name)
            if project_sup is not None:
                from vcompany.agent.fulltime_agent import FulltimeAgent

                for child_id, child in project_sup.children.items():
                    if isinstance(child, FulltimeAgent):
                        self._mention_router.unregister_agent(f"PM{project_name}")
                    else:
                        self._mention_router.unregister_agent(f"agent-{child_id}")
            self._mention_router.unregister_agent("Strategist")
        await self._root.remove_project(project_name)

    async def relay_channel_message(self, agent_id: str, content: str) -> bool:
        """Relay a message to an agent's tmux pane.

        Finds the container, gets the pane_id, and uses TmuxManager
        to send keys to the pane.

        Returns:
            True if the message was relayed, False if container/pane not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            return False
        # Access pane_id from container's tmux bridge
        pane_id = getattr(container, "_pane_id", None)
        if pane_id is None:
            return False
        # Lazy import -- TmuxManager is acceptable in daemon layer
        from vcompany.tmux.session import TmuxManager

        tmux = TmuxManager()
        try:
            tmux.send_keys(pane_id, content)
            return True
        except Exception:
            logger.warning("Failed to relay message to %s", agent_id, exc_info=True)
            return False

    async def get_agent_states(self) -> list[dict]:
        """Return state info for all agents across company and projects.

        Returns:
            List of dicts with agent_id, agent_type, state fields.
        """
        states: list[dict] = []
        # Company-level agents
        for agent_id, container in self._root._company_agents.items():
            states.append({
                "agent_id": agent_id,
                "agent_type": getattr(container.context, "agent_type", "unknown"),
                "state": container.state,
            })
        # Project agents
        for _pid, ps in self._root._projects.items():
            for agent_id, container in ps.children.items():
                states.append({
                    "agent_id": agent_id,
                    "agent_type": getattr(container.context, "agent_type", "unknown"),
                    "state": container.state,
                })
        return states

    async def checkin(self) -> dict:
        """Gather checkin data from all agents.

        Returns:
            Dict with checkin data.
        """
        from vcompany.communication.checkin import gather_checkin_data

        return await gather_checkin_data(self._root)

    async def standup(self) -> dict:
        """Run a standup session across all agents.

        Returns:
            Dict with standup data.
        """
        from vcompany.communication.standup import StandupSession

        session = StandupSession(self._root)
        return await session.run()

    async def run_integration(self) -> dict:
        """Run the integration pipeline for the current project.

        Returns:
            Dict with integration results.
        """
        from vcompany.integration.pipeline import IntegrationPipeline

        if self._project_config is None or self._project_dir is None:
            return {"error": "No project configured"}
        pipeline = IntegrationPipeline(
            project_config=self._project_config,
            project_dir=self._project_dir,
        )
        return await pipeline.run()

    async def resolve_review(self, agent_id: str, decision: str) -> bool:
        """Resolve a GsdAgent's review gate with the given decision.

        Returns True if a pending review was resolved, False otherwise.
        """
        from vcompany.agent.gsd_agent import GsdAgent

        container = await self._root._find_container(agent_id)
        if container is None:
            return False
        if not isinstance(container, GsdAgent):
            return False
        return container.resolve_review(decision)

    async def verify_agent_execution(self, agent_id: str) -> dict:
        """Check git log for recent commits in an agent's clone directory.

        Returns dict with 'success', 'stdout' keys.
        """
        from vcompany.git import ops as git_ops

        if self._project_dir is None:
            return {"success": False, "stdout": ""}
        clone_dir = self._project_dir / "clones" / agent_id
        result = await asyncio.to_thread(
            git_ops.log, clone_dir, args=["--oneline", "-5"]
        )
        return {"success": result.success, "stdout": result.stdout.strip() if result.stdout else ""}

    async def get_container_info(self, agent_id: str) -> dict | None:
        """Get container info dict (state, type, has completion event support).

        Returns None if container not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            return None
        info = {
            "agent_id": agent_id,
            "state": container.state,
            "agent_type": getattr(container.context, "agent_type", "unknown"),
            "has_make_completion_event": hasattr(container, "make_completion_event"),
        }
        return info

    async def log_decision(
        self,
        agent_id: str,
        question: str,
        decision: str,
        confidence_level: str,
        decided_by: str,
    ) -> None:
        """Log a decision via the Strategist's DecisionLogger.

        Called by QuestionHandlerCog instead of importing DecisionLogEntry directly.
        """
        from vcompany.strategist.models import DecisionLogEntry
        from datetime import datetime, timezone

        strategist = self._root._company_agents.get("strategist")
        if strategist is not None:
            decision_logger = getattr(strategist, "decision_logger", None)
            if decision_logger:
                await decision_logger.log_decision(
                    DecisionLogEntry(
                        timestamp=datetime.now(timezone.utc),
                        question_or_plan=question,
                        decision=decision,
                        confidence_level=confidence_level,
                        decided_by=decided_by,
                        agent_id=agent_id,
                    )
                )

    async def initialize_workflow_master(self, worktree_path: Path) -> None:
        """Initialize the workflow-master conversation in the daemon layer.

        Called by WorkflowMasterCog.initialize() instead of creating
        StrategistConversation directly.
        """
        from vcompany.strategist.conversation import StrategistConversation
        from vcompany.strategist.workflow_master_persona import (
            WORKFLOW_MASTER_SESSION_UUID,
            build_workflow_master_persona,
        )

        persona_text = build_workflow_master_persona(worktree_path)
        runtime_persona_path = Path.home() / "vco-workflow-master-persona.md"
        runtime_persona_path.write_text(persona_text)

        self._wm_conversation = StrategistConversation(
            persona_path=runtime_persona_path,
            session_id=WORKFLOW_MASTER_SESSION_UUID,
            allowed_tools="Bash Read Write Edit Glob Grep",
        )
        logger.info("Workflow-master conversation initialized (worktree: %s)", worktree_path)

    def detect_active_project(self) -> tuple[Path, object] | None:
        """Scan ~/vco-projects/ for the most recently active project.

        Looks for projects with state/agents.json (meaning they were dispatched).
        Returns the one with the newest agents.json mtime as (project_dir, config).
        """
        from vcompany.shared.paths import PROJECTS_BASE
        from vcompany.models.config import load_config

        if not PROJECTS_BASE.exists():
            return None

        best: tuple[Path, float] | None = None
        for project_dir in PROJECTS_BASE.iterdir():
            if not project_dir.is_dir():
                continue
            agents_json = project_dir / "state" / "agents.json"
            agents_yaml = project_dir / "agents.yaml"
            if agents_json.exists() and agents_yaml.exists():
                mtime = agents_json.stat().st_mtime
                if best is None or mtime > best[1]:
                    best = (project_dir, mtime)

        if best is None:
            return None

        try:
            config = load_config(best[0] / "agents.yaml")
            return (best[0], config)
        except Exception:
            logger.warning("Failed to load config for detected project %s", best[0])
            return None

    async def relay_workflow_master_message(self, content: str) -> str:
        """Relay a message to the workflow-master conversation.

        Called by WorkflowMasterCog._send_to_channel() instead of calling
        StrategistConversation.send_streaming() directly.

        Returns:
            Full response text from the conversation.
        """
        conversation = getattr(self, "_wm_conversation", None)
        if conversation is None:
            return "Workflow-master conversation not initialized."
        return await conversation.send(content)

    # ── Category D: Review gate callbacks ─────────────────────────

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
        """Initialize a project: Strategist, supervision tree, Discord routing.

        Creates Strategist as a company agent, builds project supervisor from
        agents.yaml specs, wires PM backlog with on_mutation callback to
        #backlog channel, and registers all agent handles with MentionRouterCog.

        All inter-agent communication flows through Discord -- no internal
        event sinks or callback wiring needed (D-10, D-11).
        """
        from vcompany.agent.company_agent import CompanyAgent
        from vcompany.agent.fulltime_agent import FulltimeAgent
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

        # Wire Strategist conversation
        if isinstance(strategist_container, CompanyAgent):
            strategist_container.initialize_conversation(persona_path)
            # Register Strategist handle with MentionRouterCog
            if self._mention_router:
                self._mention_router.register_agent(
                    "Strategist",
                    strategist_container,
                    channel_id=self.get_channel_id("strategist"),
                )

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

        # 3. Wire PM backlog with on_mutation callback to #backlog channel
        pm_container: FulltimeAgent | None = None
        for child in project_sup.children.values():
            if isinstance(child, FulltimeAgent):
                pm_container = child
                break

        if pm_container is not None:
            # Create backlog mutation callback that posts to #backlog channel
            backlog_channel = self.get_channel_id("backlog")

            async def _backlog_notify(msg: str) -> None:
                if backlog_channel:
                    await self._get_comm().send_message(
                        SendMessagePayload(channel_id=backlog_channel, content=msg)
                    )

            backlog = BacklogQueue(pm_container.memory, on_mutation=_backlog_notify)
            await backlog.load()
            state_mgr = ProjectStateManager(backlog, pm_container.memory)
            pm_container.backlog = backlog
            pm_container._project_state = state_mgr

            # Register PM handle with MentionRouterCog
            if self._mention_router:
                self._mention_router.register_agent(
                    f"PM{project_config.project}",
                    pm_container,
                    channel_id=self.get_channel_id("decisions"),
                )

        # 4. Register all agent handles with MentionRouterCog
        if self._mention_router:
            for child_id, child in project_sup.children.items():
                if isinstance(child, FulltimeAgent):
                    continue  # PM already registered above
                self._mention_router.register_agent(
                    f"agent-{child_id}",
                    child,
                    channel_id=self.get_channel_id(f"agent-{child_id}"),
                )
