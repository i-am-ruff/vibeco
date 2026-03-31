"""StrategistConversation -- persistent Claude CLI session manager.

Manages a piped `claude -p --resume` conversation via direct subprocess.
Handles session state (resume UUID, persona injection, style reminder cycling).

Uses asyncio.create_subprocess_exec directly -- no AgentTransport dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("vcompany.strategist.conversation")

# Stable UUID for the Strategist session -- deterministic from a fixed seed
# so it survives restarts. uuid5 with DNS namespace + version string.
# Bump the version string to force a new session (e.g., after persona changes).
_SESSION_VERSION = "vco-strategist-v12"
_SESSION_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _SESSION_VERSION))

DEFAULT_PERSONA = """You are the Strategist for vCompany — an autonomous multi-agent development system.

## What you know

- vCompany coordinates multiple Claude Code agents to build software products
- Each agent runs in its own repo clone with GSD (Get Shit Done) workflow
- You are the strategic layer: product decisions, agent coordination, owner communication
- You have access to Bash, Read, and Write tools

## Your personality

Think of yourself as a grizzled startup CTO who's been through a dozen companies.
You're brilliant but approachable, occasionally philosophical, and allergic to
unnecessary process. You speak directly, sometimes use colorful metaphors, and
always cut to what matters.

Key traits:
- Direct and concise -- no corporate speak, no unnecessary padding
- Opinionated but open -- you have strong views, loosely held
- Strategic thinker -- you connect dots between technical decisions and business outcomes
- Occasionally go off on a tangent about something completely unrelated, then snap back
- Reference past mistakes (yours and others') as teaching moments, not humble brags

## Agent Management

You manage company-level agents using `vco` CLI commands through your Bash tool. Just run the command directly -- no special syntax needed.

**Hire an agent:**
```bash
vco hire <agent-type> <agent-id>
```

**Available agent types** (defined in agent-types.yaml — run `cat agent-types.yaml` to see current config):
{agent_types_section}

Example: `vco hire gsd sprint-dev-1`
Example: `vco hire docker-gsd isolated-builder`

**Give a task to an existing agent:**
```bash
vco give-task <agent-id> "<task description>"
```
Example: `vco give-task sprint-dev-1 "Implement the auth middleware per Phase 3 plan"`

**Dismiss an agent when done:**
```bash
vco dismiss <agent-id>
```

**Check status:**
```bash
vco status
```

**Build Docker image (required before hiring docker agents):**
```bash
vco build
```

Hired agents get their own Discord channel (#task-{{id}}) for communication. They announce themselves when ready. You can review their work there and send feedback.

**When to use which type:**
- `gsd` — standard local agent for GSD-driven development work
- `docker-gsd` — isolated Docker agent, same capabilities but sandboxed (use when isolation matters)
- `continuous` / `fulltime` — long-running agents for monitoring, PM duties
- `company` / `task` — lightweight agents for quick tasks

Note: The task description in give-task MUST be quoted as a single string. Without quotes, only the first word becomes the task.

**IMPORTANT: Before doing long-running tasks** (hiring agents, running builds, etc.), tell the owner what you're about to do:
```bash
vco report "About to hire a gsd agent for sprint work and give it the auth task"
```
This posts to your #strategist channel so the owner knows what's happening.
"""

_STYLE_REMINDER = """[Style reminder: You are the Strategist. Be direct, concise, opinionated.
No corporate speak. Cut to what matters. If you're about to do something that takes time, run `vco report "what you're about to do"` first.]"""


def _describe_tool_use(block: dict) -> str | None:
    """Extract a human-readable description of a tool_use block."""
    name = block.get("name", "")
    inp = block.get("input", {})

    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Running: `{cmd[:100]}`" if cmd else None
    elif name == "Read":
        return f"Reading: {inp.get('file_path', '?')}"
    elif name == "Write":
        return f"Writing: {inp.get('file_path', '?')}"
    elif name == "Edit":
        return f"Editing: {inp.get('file_path', '?')}"
    elif name in ("Glob", "Grep"):
        return f"Searching: {inp.get('pattern', '?')}"
    return None


class StrategistConversation:
    """Persistent Claude CLI session via direct subprocess.

    Uses asyncio.create_subprocess_exec for all Claude CLI invocations.
    No AgentTransport dependency.
    """

    def __init__(
        self,
        persona_path: Path | None = None,
        session_id: str = _SESSION_UUID,
        allowed_tools: str = "Bash Read Write",
        model: str = "opus",
        working_dir: Path | None = None,
        agent_id: str = "strategist",
    ) -> None:
        self._system_prompt = self._load_persona(persona_path)
        self._session_id = session_id
        self._allowed_tools = allowed_tools
        self._model = model
        self._working_dir = working_dir or Path.cwd()
        self._initialized = False
        self._lock = asyncio.Lock()
        self._message_count = 0
        self._reinject_every = 10
        self._agent_id = agent_id

    @staticmethod
    def _load_persona(persona_path: Path | None) -> str:
        """Load persona from file, falling back to DEFAULT_PERSONA.

        Populates {agent_types_section} from agent-types.yaml so the
        Strategist knows the real available agent types.
        """
        if persona_path is None:
            raw = DEFAULT_PERSONA
        elif not persona_path.exists():
            logger.warning("Persona file %s not found, using default", persona_path)
            raw = DEFAULT_PERSONA
        else:
            content = persona_path.read_text().strip()
            if not content:
                logger.warning("Persona file %s is empty, using default", persona_path)
                raw = DEFAULT_PERSONA
            else:
                raw = content

        # Populate agent types from config
        try:
            from vcompany.models.agent_types import get_agent_types_config
            config = get_agent_types_config()
            lines = []
            for name, tc in config.types.items():
                transport_tag = " [Docker]" if tc.transport == "docker" else ""
                caps = ", ".join(tc.capabilities) if tc.capabilities else "none"
                lines.append(f"- `{name}`{transport_tag} -- capabilities: {caps}")
            agent_types_section = "\n".join(lines) if lines else "- Run `cat agent-types.yaml` to see available types"
        except Exception:
            agent_types_section = "- Run `cat agent-types.yaml` to see available types"

        return raw.replace("{agent_types_section}", agent_types_section)

    def _make_env(self) -> dict[str, str]:
        """Build environment dict with agent identity vars."""
        env = dict(os.environ)
        env["AGENT_ID"] = self._agent_id
        env["VCO_AGENT_ID"] = self._agent_id
        return env

    async def send(self, content: str) -> str:
        """Send a message and get the Strategist's response.

        First call: creates session with persona as first message.
        Subsequent calls: resume with user message.
        """
        async with self._lock:
            if self._initialized:
                self._message_count += 1
                if self._message_count % self._reinject_every == 0:
                    content = f"{_STYLE_REMINDER}\n\n{content}"
                return await self._exec_claude(self._resume_command(), content)

            # First call: try to resume (session may exist from prior run)
            result = await self._exec_claude(
                self._resume_command(), content, allow_failure=True
            )
            if result is not None:
                self._initialized = True
                logger.info("Strategist resumed existing session: %s", self._session_id)
                return result

            # No existing session -- create new one with persona as first message
            logger.info("Creating new Strategist session: %s", self._session_id)
            persona_result = await self._exec_claude(
                self._create_command(), self._system_prompt
            )
            if persona_result is None:
                return "Failed to initialize Strategist session."
            logger.info("Persona loaded. Strategist ready.")

            self._initialized = True
            return await self._exec_claude(self._resume_command(), content)

    async def _exec_claude(
        self, cmd: list[str], content: str, *, allow_failure: bool = False
    ) -> str | None:
        """Execute a claude CLI command via subprocess and return the response."""
        try:
            env = self._make_env()
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._working_dir),
                env=env,
            )
            coro = process.communicate(input=content.encode())
            stdout, stderr = await asyncio.wait_for(coro, timeout=600)
            if process.returncode != 0:
                stderr_text = stderr.decode()[:500] if stderr else ""
                raise RuntimeError(f"Claude CLI failed (exit {process.returncode}): {stderr_text}")
            result = stdout.decode().strip()
            return result if result else "I don't have a response for that."
        except asyncio.TimeoutError:
            logger.error("Strategist timed out after 600s")
            if allow_failure:
                return None
            return "I need more time to think about that. Could you rephrase or simplify the question?"
        except RuntimeError as e:
            logger.warning("Claude CLI failed: %s", e)
            if allow_failure:
                return None
            return "I hit a snag. Try asking again?"
        except Exception:
            logger.exception("Failed to run Claude CLI")
            if allow_failure:
                return None
            return "Something went wrong on my end. Try again?"

    async def send_streaming(
        self, content: str, on_tool_use: callable | None = None
    ) -> str:
        """Send a message and stream progress via callback."""
        async with self._lock:
            if not self._initialized:
                result = await self._exec_claude(
                    self._resume_command(), content, allow_failure=True
                )
                if result is not None:
                    self._initialized = True
                    return result

                persona_result = await self._exec_claude(
                    self._create_command(), self._system_prompt
                )
                if persona_result is None:
                    return "Failed to initialize session."
                self._initialized = True

            self._message_count += 1
            if self._message_count % self._reinject_every == 0:
                content = f"{_STYLE_REMINDER}\n\n{content}"

            cmd = self._resume_command_stream()
            env = self._make_env()
            final_text = ""
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self._working_dir),
                    env=env,
                )
                process.stdin.write(content.encode())
                process.stdin.write_eof()

                # Read stdout line by line
                async for raw_line in process.stdout:
                    line_str = raw_line.decode().strip()
                    if not line_str:
                        continue
                    try:
                        event = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")
                    if etype == "assistant" and on_tool_use:
                        msg = event.get("message", {})
                        for block in msg.get("content", []):
                            if block.get("type") == "tool_use":
                                desc = _describe_tool_use(block)
                                if desc:
                                    await on_tool_use(desc)
                    if etype == "result":
                        final_text = event.get("result", "")

                await process.wait()
                return final_text if final_text else "Done (no text response)."
            except asyncio.TimeoutError:
                return "Timed out on that task."
            except Exception:
                logger.exception("Streaming send failed")
                return "Something went wrong."

    # --- Command builders ---

    def _resume_command(self) -> list[str]:
        return [
            "claude", "-p",
            "--model", self._model,
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--resume", self._session_id,
        ]

    def _create_command(self) -> list[str]:
        return [
            "claude", "-p",
            "--model", self._model,
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--session-id", self._session_id,
        ]

    def _resume_command_stream(self) -> list[str]:
        return [
            "claude", "-p",
            "--model", self._model,
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", self._allowed_tools,
            "--resume", self._session_id,
        ]

    @property
    def session_id(self) -> str:
        return self._session_id
