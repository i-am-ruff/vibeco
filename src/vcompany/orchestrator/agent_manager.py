"""Agent lifecycle manager: dispatch, kill, and relaunch Claude Code sessions.

Orchestrates Claude Code sessions in tmux panes. All tmux operations go through
the injected TmuxManager (for testability). State is persisted to agents.json
via write_atomic for crash-safe reads by the monitor.
"""

import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vcompany.models.agent_state import AgentEntry, AgentsRegistry
from vcompany.models.config import ProjectConfig
from vcompany.shared.file_ops import write_atomic
from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.orchestrator")

CLAUDE_READY_MARKERS = [
    "bypass permissions",
    "what can i help",
    "type your prompt",
    "tips:",
]


@dataclass
class DispatchResult:
    """Result of a dispatch operation. Follows GitResult pattern from Phase 1."""

    success: bool
    agent_id: str
    pane_id: str = ""
    pid: int | None = None
    error: str = ""


class AgentManager:
    """Manages agent lifecycle: dispatch, kill, relaunch.

    All business logic for launching Claude Code sessions in tmux panes,
    gracefully terminating them, and relaunching with resume. CLI commands
    are thin wrappers around this class.
    """

    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        tmux: TmuxManager | None = None,
        bot_token: str = "",
        guild_id: str = "",
    ) -> None:
        self._project_dir = Path(project_dir)
        self._config = config
        self._tmux = tmux or TmuxManager()
        self._agents_json_path = self._project_dir / "state" / "agents.json"
        self._registry = self._load_registry()
        self._session_name = f"vco-{config.project}"
        self._bot_token = bot_token or os.environ.get("DISCORD_BOT_TOKEN", "")
        self._guild_id = guild_id or os.environ.get("DISCORD_GUILD_ID", "")
        # Track tmux panes by agent_id for kill fallback
        self._panes: dict[str, object] = {}

    # ── Dispatch ──────────────────────────────────────────────────────

    def dispatch(self, agent_id: str, resume: bool = False) -> DispatchResult:
        """Launch a Claude Code session in a tmux pane for the given agent.

        Args:
            agent_id: Agent ID from config.
            resume: If True, use /gsd:resume-work instead of /gsd:new-project.

        Returns:
            DispatchResult with success status and details.
        """
        # Find agent in config
        agent_cfg = self._find_agent(agent_id)
        if agent_cfg is None:
            return DispatchResult(
                success=False,
                agent_id=agent_id,
                error=f"Agent '{agent_id}' not found in config",
            )

        # Get or create tmux session
        try:
            session = self._tmux.create_session(self._session_name)
        except Exception:
            # Session may already exist, try to reuse
            session = self._tmux.create_session(self._session_name)

        # Create pane for this agent
        pane = self._tmux.create_pane(session, window_name=agent_id)
        self._panes[agent_id] = pane

        # Build prompt path
        prompt_path = self._project_dir / "context" / "agents" / f"{agent_id}.md"

        # Build chained cd + env + claude command (Pitfall 2: single send_keys call)
        # Launch Claude in INTERACTIVE mode (no -p) so it persists across
        # multiple GSD commands. Monitor sends work commands via tmux.
        clone_dir = self._project_dir / "clones" / agent_id
        chained_cmd = (
            f"cd {clone_dir} "
            f"&& export DISCORD_BOT_TOKEN='{self._bot_token}' "
            f"&& export DISCORD_GUILD_ID='{self._guild_id}' "
            f"&& export PROJECT_NAME='{self._config.project}' "
            f"&& export AGENT_ID='{agent_id}' "
            f"&& export VCO_AGENT_ID='{agent_id}' "
            f"&& export AGENT_ROLE='{agent_cfg.role}' "
            f"&& claude --dangerously-skip-permissions "
            f"--append-system-prompt-file {prompt_path}"
        )

        self._tmux.send_command(pane, chained_cmd)

        # Auto-accept workspace trust prompt ("Yes, I trust this folder")
        # Claude shows this on first use of a directory. Send Enter after
        # a brief delay to select the default option (1. Yes).
        time.sleep(3)
        pane.send_keys("", enter=True)  # Just press Enter to confirm default
        logger.debug("Sent trust prompt acceptance for %s", agent_id)

        # Extract pane PID (shell PID; Claude will be its child)
        pane_pid = int(pane.pane_pid) if pane.pane_pid else None
        pane_id = str(getattr(pane, "pane_id", ""))

        # Update registry
        now = datetime.now(timezone.utc)
        self._registry.agents[agent_id] = AgentEntry(
            agent_id=agent_id,
            pane_id=pane_id,
            pid=pane_pid,
            session_name=self._session_name,
            status="running",
            launched_at=now,
        )
        self._save_registry()

        return DispatchResult(
            success=True,
            agent_id=agent_id,
            pane_id=pane_id,
            pid=pane_pid,
        )

    def dispatch_all(self) -> list[DispatchResult]:
        """Launch all agents from config plus a monitor pane.

        Creates a tmux session named vco-{project}, one pane per agent,
        plus a monitor pane for Phase 3.

        Returns:
            List of DispatchResult, one per agent.
        """
        # Clear stale registry BEFORE killing old session. This prevents a race
        # where the monitor reads agents.json between create_session (which kills
        # old PIDs) and _save_registry (which writes new PIDs). With stale PIDs
        # and a dead session, the monitor would fire false "agent appears dead" alerts.
        self._registry = AgentsRegistry(project=self._config.project)
        self._save_registry()

        # Create the main session
        session = self._tmux.create_session(self._session_name)

        results: list[DispatchResult] = []
        for agent_cfg in self._config.agents:
            # Create pane for agent
            pane = self._tmux.create_pane(session, window_name=agent_cfg.id)
            self._panes[agent_cfg.id] = pane

            # Build command — interactive mode (no -p), monitor sends work commands
            clone_dir = self._project_dir / "clones" / agent_cfg.id
            prompt_path = (
                self._project_dir / "context" / "agents" / f"{agent_cfg.id}.md"
            )
            chained_cmd = (
                f"cd {clone_dir} "
                f"&& export DISCORD_BOT_TOKEN='{os.environ.get('DISCORD_BOT_TOKEN', '')}' "
                f"&& export DISCORD_GUILD_ID='{os.environ.get('DISCORD_GUILD_ID', '')}' "
                f"&& export PROJECT_NAME='{self._config.project}' "
                f"&& export AGENT_ID='{agent_cfg.id}' "
                f"&& export VCO_AGENT_ID='{agent_cfg.id}' "
                f"&& export AGENT_ROLE='{agent_cfg.role}' "
                f"&& claude --dangerously-skip-permissions "
                f"--append-system-prompt-file {prompt_path}"
            )
            self._tmux.send_command(pane, chained_cmd)

            # Auto-accept workspace trust prompt (same as single dispatch)
            time.sleep(3)
            pane.send_keys("", enter=True)
            logger.debug("Sent trust prompt acceptance for %s", agent_cfg.id)

            pane_pid = int(pane.pane_pid) if pane.pane_pid else None
            pane_id = str(getattr(pane, "pane_id", ""))

            now = datetime.now(timezone.utc)
            self._registry.agents[agent_cfg.id] = AgentEntry(
                agent_id=agent_cfg.id,
                pane_id=pane_id,
                pid=pane_pid,
                session_name=self._session_name,
                status="running",
                launched_at=now,
            )

            results.append(
                DispatchResult(
                    success=True,
                    agent_id=agent_cfg.id,
                    pane_id=pane_id,
                    pid=pane_pid,
                )
            )

        self._save_registry()
        return results

    # ── Kill ──────────────────────────────────────────────────────────

    def kill(self, agent_id: str, force: bool = False) -> bool:
        """Gracefully terminate an agent's Claude Code session.

        Sends SIGTERM, waits up to 10s, then SIGKILL if still alive.
        Falls back to killing the tmux pane if signal delivery fails.
        Updates agents.json status to "stopped".

        Args:
            agent_id: Agent to kill.
            force: Skip SIGTERM, send SIGKILL immediately.

        Returns:
            True if agent was found and killed, False if not found.
        """
        if agent_id not in self._registry.agents:
            return False

        entry = self._registry.agents[agent_id]
        killed = False

        if entry.pid is not None:
            # Find child PIDs (Claude runs as child of shell)
            child_pids = _find_child_pids(entry.pid)
            for cpid in child_pids:
                if _verify_pid_is_claude(cpid):
                    killed = _kill_process(cpid, timeout=10, force=force)
                    break

        # Fallback: kill the tmux pane
        if not killed and agent_id in self._panes:
            try:
                self._tmux.kill_pane(self._panes[agent_id])
                killed = True
            except Exception:
                logger.warning("Failed to kill tmux pane for %s", agent_id)

        # Update state regardless
        entry.status = "stopped"
        self._registry.agents[agent_id] = entry
        self._save_registry()

        return True

    # ── Relaunch ──────────────────────────────────────────────────────

    def relaunch(self, agent_id: str) -> DispatchResult:
        """Kill then re-dispatch an agent with /gsd:resume-work.

        Args:
            agent_id: Agent to relaunch.

        Returns:
            DispatchResult from the new dispatch.
        """
        self.kill(agent_id)
        return self.dispatch(agent_id, resume=True)

    # ── Fix Dispatch ─────────────────────────────────────────────────

    def dispatch_fix(
        self, agent_id: str, failing_tests: list[str], error_output: str = ""
    ) -> DispatchResult:
        """Dispatch a /gsd:quick fix task to the responsible agent per D-07/INTG-05.

        Sends the failing test info as a prompt to the agent's tmux pane.
        The agent receives: /gsd:quick Fix failing tests: {test_names}. Error: {error_output}
        Owner is notified separately via #alerts (handled by caller).

        Args:
            agent_id: Agent to send the fix task to.
            failing_tests: List of failing test names/paths.
            error_output: Truncated error output from the test run.

        Returns:
            DispatchResult with success status.
        """
        agent_cfg = self._find_agent(agent_id)
        if agent_cfg is None:
            return DispatchResult(
                success=False,
                agent_id=agent_id,
                error=f"Agent '{agent_id}' not found in config",
            )

        # Check agent has a pane
        pane = self._panes.get(agent_id)
        if pane is None:
            return DispatchResult(
                success=False,
                agent_id=agent_id,
                error=f"No tmux pane found for agent '{agent_id}'",
            )

        # Build fix prompt with test names and error output
        test_list = ", ".join(failing_tests)
        prompt = f"/gsd:quick Fix these failing integration tests: {test_list}."
        if error_output:
            prompt += f" Error output: {error_output[:500]}"

        # Use tmux send_command to deliver
        try:
            self._tmux.send_command(pane, prompt)
        except Exception:
            logger.exception("Failed to send fix command to %s", agent_id)
            return DispatchResult(
                success=False,
                agent_id=agent_id,
                error=f"Failed to send command to tmux pane for '{agent_id}'",
            )

        logger.info("Dispatched fix to %s: %s", agent_id, test_list)
        return DispatchResult(
            success=True,
            agent_id=agent_id,
            pane_id=str(getattr(pane, "pane_id", "")),
        )

    # ── Work Commands ──────────────────────────────────────────────────

    def send_work_command(
        self, agent_id: str, command: str, *, wait_for_ready: bool = False
    ) -> bool:
        """Send a GSD command to an agent's Claude Code session via tmux.

        Used by monitor/bot to send phase commands like:
          /gsd:plan-phase 1 --auto
          /gsd:execute-phase 1 --auto
          /gsd:resume-work

        Args:
            agent_id: Agent to send command to.
            command: GSD command string (e.g., "/gsd:plan-phase 1 --auto").
            wait_for_ready: If True, poll pane output until Claude prompt is detected.

        Returns:
            True if command was sent, False on error.
        """
        pane = self._panes.get(agent_id)
        if pane is None:
            # Fallback: resolve from registry pane_id via TmuxManager
            entry = self._registry.agents.get(agent_id)
            if entry and entry.pane_id:
                logger.info(
                    "Resolving pane for %s from registry (pane_id=%s)",
                    agent_id, entry.pane_id,
                )
                pane = self._tmux.get_pane_by_id(entry.pane_id)
            if pane is None:
                logger.error(
                    "No tmux pane for agent %s (not in _panes or registry)", agent_id
                )
                return False

        try:
            if wait_for_ready:
                if not self._wait_for_claude_ready(pane, agent_id):
                    logger.warning("Proceeding without ready confirmation for %s", agent_id)
                # Post-ready settle: Claude Code may still be loading GSD,
                # auto-update checks, or processing startup hooks.
                logger.info("Waiting 10s post-ready settle for %s", agent_id)
                time.sleep(10)

            # Send command with retry on delivery failure
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                result = self._tmux.send_command(pane, command)
                if not result:
                    logger.error("Failed to send to %s (attempt %d): %s", agent_id, attempt, command)
                    continue

                logger.info("Sent to %s: %s (attempt %d)", agent_id, command, attempt)

                # Verify command appeared in pane
                time.sleep(2)
                try:
                    verify_output = self._tmux.get_output(pane, lines=10)
                    verify_text = "\n".join(verify_output).lower()
                    cmd_fragment = command[:30].lower()
                    if cmd_fragment in verify_text:
                        logger.info("Verified command delivery to %s", agent_id)
                        return True
                    else:
                        if attempt < max_attempts:
                            logger.debug(
                                "Command not yet visible for %s (attempt %d), retrying in 10s",
                                agent_id, attempt,
                            )
                            time.sleep(10)
                        else:
                            logger.warning(
                                "Command not detected in pane for %s after %d attempts",
                                agent_id, max_attempts,
                            )
                        continue
                except Exception:
                    logger.debug("Could not verify command delivery to %s", agent_id)
                    return True  # send_keys succeeded, assume delivered

            logger.error("All %d delivery attempts failed for %s", max_attempts, agent_id)
            return result
        except Exception:
            logger.exception("Failed to send command to %s", agent_id)
            return False

    def _wait_for_claude_ready(
        self, pane, agent_id: str, timeout: int = 120, poll_interval: float = 2,
    ) -> bool:
        """Poll pane output until Claude Code ready markers are detected.

        Returns True if ready detected, False on timeout.
        Uses Claude-specific UI markers (not generic '>' which matches too broadly).
        Post-ready settle time is 2 seconds (not 30).
        """
        pane_id = getattr(pane, "pane_id", "?")
        deadline = time.monotonic() + timeout
        poll_count = 0
        empty_count = 0
        error_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            try:
                output = self._tmux.get_output(pane, lines=30)
                text = "\n".join(output).lower()
                if not output or all(not line.strip() for line in output):
                    empty_count += 1
                    # Log every 10th empty result to avoid spam
                    if empty_count % 10 == 1:
                        logger.warning(
                            "Pane %s for %s returned empty output (empty_count=%d, poll=%d)",
                            pane_id, agent_id, empty_count, poll_count,
                        )
                else:
                    for marker in CLAUDE_READY_MARKERS:
                        if marker in text:
                            logger.info(
                                "Claude ready for %s (marker: '%s', polls=%d)",
                                agent_id, marker, poll_count,
                            )
                            time.sleep(2)  # Brief settle, NOT 30s
                            return True
                    # Log first non-empty, non-matching output for diagnostics
                    if poll_count <= 3 or poll_count % 15 == 0:
                        preview = text[:200].replace("\n", " | ")
                        logger.info(
                            "Pane %s for %s has content but no marker (poll=%d): %s",
                            pane_id, agent_id, poll_count, preview,
                        )
            except Exception:
                error_count += 1
                logger.warning(
                    "Error reading pane %s for %s (error_count=%d, poll=%d)",
                    pane_id, agent_id, error_count, poll_count,
                    exc_info=True,
                )
            time.sleep(poll_interval)
        logger.warning(
            "Timeout (%ds) waiting for Claude ready on %s "
            "(polls=%d, empty=%d, errors=%d, pane=%s)",
            timeout, agent_id, poll_count, empty_count, error_count, pane_id,
        )
        return False

    def send_work_command_all(
        self, command: str, *, wait_for_ready: bool = False
    ) -> dict[str, bool]:
        """Send the same GSD command to all agents.

        Args:
            command: GSD command to send.
            wait_for_ready: If True, wait for each agent's Claude to be ready first.

        Returns:
            Dict of agent_id -> success.
        """
        results = {}
        # Iterate all known agents from registry (not just in-memory _panes)
        agent_ids = set(self._panes.keys()) | set(self._registry.agents.keys())
        for agent_id in agent_ids:
            if agent_id == "monitor":
                continue
            results[agent_id] = self.send_work_command(
                agent_id, command, wait_for_ready=wait_for_ready
            )
        return results

    # ── Private helpers ───────────────────────────────────────────────

    def _find_agent(self, agent_id: str):
        """Find an AgentConfig by ID, or None."""
        for agent in self._config.agents:
            if agent.id == agent_id:
                return agent
        return None

    def _load_registry(self) -> AgentsRegistry:
        """Load existing agents.json or create empty registry."""
        if self._agents_json_path.exists():
            try:
                return AgentsRegistry.model_validate_json(
                    self._agents_json_path.read_text()
                )
            except Exception:
                logger.warning("Failed to load agents.json, starting fresh")
        return AgentsRegistry(project=self._config.project)

    def _save_registry(self) -> None:
        """Serialize registry and write atomically."""
        write_atomic(
            self._agents_json_path,
            self._registry.model_dump_json(indent=2),
        )


# ── Module-level helpers (mockable in tests) ─────────────────────────


def _find_child_pids(parent_pid: int) -> list[int]:
    """Scan /proc for child processes of the given PID.

    Returns list of child PIDs. On error or no children, returns empty list.
    """
    children: list[int] = []
    try:
        proc_dir = Path("/proc")
        for entry in proc_dir.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text()
                # Format: pid (comm) state ppid ...
                # The 4th field is ppid
                parts = stat.split(")")
                if len(parts) >= 2:
                    fields = parts[1].strip().split()
                    if len(fields) >= 2 and int(fields[1]) == parent_pid:
                        children.append(int(entry.name))
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return children


def _verify_pid_is_claude(pid: int) -> bool:
    """Check if a PID belongs to a claude or node process.

    Reads /proc/{pid}/cmdline to verify the process is what we expect
    before sending signals (per Pitfall 1: verify before kill).
    """
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_text()
        return "claude" in cmdline.lower() or "node" in cmdline.lower()
    except OSError:
        return False


def _kill_process(pid: int, timeout: int = 10, force: bool = False) -> bool:
    """Kill a process with SIGTERM/SIGKILL escalation.

    Args:
        pid: Process ID to kill.
        timeout: Seconds to wait after SIGTERM before escalating to SIGKILL.
        force: Skip SIGTERM, send SIGKILL immediately.

    Returns:
        True if process was successfully terminated.
    """
    try:
        if force:
            os.kill(pid, signal.SIGKILL)
            return True

        # Graceful: SIGTERM first
        os.kill(pid, signal.SIGTERM)

        # Poll for exit
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)  # Check if still alive
                time.sleep(0.5)
            except ProcessLookupError:
                return True  # Process exited

        # Still alive after timeout: escalate to SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return True  # Died between check and kill

    except ProcessLookupError:
        return True  # Already dead
    except OSError:
        return False
