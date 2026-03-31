"""Persistent Claude CLI session manager for conversation-type agents.

Manages a piped `claude -p --resume` conversation via direct subprocess.
Handles session state (resume UUID, persona injection, style reminder cycling).

Used by WorkerConversationHandler when container._conversation is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Stable UUID from a fixed seed — survives restarts.
# Bump the version string to force a new session.
_DEFAULT_SESSION_VERSION = "vco-strategist-v12"


class ConversationSession:
    """Persistent Claude CLI session via direct subprocess.

    Wraps `claude -p --resume` for conversation-type agents.
    The session_id ensures conversation continuity across worker restarts.
    """

    def __init__(
        self,
        persona: str,
        session_id: str | None = None,
        allowed_tools: str = "Bash Read Write",
        model: str = "opus",
        working_dir: Path | None = None,
        agent_id: str = "conversation",
        reinject_every: int = 10,
        style_reminder: str | None = None,
    ) -> None:
        self._persona = persona
        self._session_id = session_id or str(
            uuid.uuid5(uuid.NAMESPACE_DNS, _DEFAULT_SESSION_VERSION)
        )
        self._allowed_tools = allowed_tools
        self._model = model
        self._working_dir = working_dir or Path.cwd()
        self._agent_id = agent_id
        self._initialized = False
        self._lock = asyncio.Lock()
        self._message_count = 0
        self._reinject_every = reinject_every
        self._style_reminder = style_reminder

    async def send(self, content: str) -> str:
        """Send a message and get the response.

        First call: creates session with persona as first message.
        Subsequent calls: resume with user message.
        """
        async with self._lock:
            if self._initialized:
                self._message_count += 1
                if (
                    self._style_reminder
                    and self._message_count % self._reinject_every == 0
                ):
                    content = f"{self._style_reminder}\n\n{content}"
                return await self._exec_claude(self._resume_command(), content)

            # First call: try to resume (session may exist from prior run)
            result = await self._exec_claude(
                self._resume_command(), content, allow_failure=True
            )
            if result is not None:
                self._initialized = True
                logger.info("Resumed existing session: %s", self._session_id)
                return result

            # No existing session — create new one with persona
            logger.info("Creating new session: %s", self._session_id)
            persona_result = await self._exec_claude(
                self._create_command(), self._persona
            )
            if persona_result is None:
                return "Failed to initialize conversation session."
            logger.info("Persona loaded. Session ready.")

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
                raise RuntimeError(
                    f"Claude CLI failed (exit {process.returncode}): {stderr_text}"
                )
            result = stdout.decode().strip()
            return result if result else "I don't have a response for that."
        except asyncio.TimeoutError:
            logger.error("Session timed out after 600s")
            if allow_failure:
                return None
            return "I need more time to think about that. Could you rephrase?"
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

    def _make_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AGENT_ID"] = self._agent_id
        env["VCO_AGENT_ID"] = self._agent_id
        return env

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

    @property
    def session_id(self) -> str:
        return self._session_id
