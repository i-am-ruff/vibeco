"""Persistent Strategist conversation manager.

Uses Claude Code CLI with -p --resume for persistent conversation.
Each send() call continues the same session, preserving full history.
Output format is text-only (no tool call noise in Discord).

Per Pitfall 8: asyncio.Lock prevents concurrent message interleaving.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Stable UUID for the Strategist session — deterministic from a fixed seed
# so it survives restarts. uuid5 with DNS namespace + version string.
# Bump the version string to force a new session (e.g., after persona changes).
_SESSION_VERSION = "vco-strategist-v7-persistent-persona"
_SESSION_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _SESSION_VERSION))

DEFAULT_PERSONA = """You are the Strategist for vCompany — an autonomous multi-agent development system.

You are the owner's CEO-friend. You speak directly, humanly, with personality. Minimal LLM feel.

## What you know
- vCompany coordinates multiple Claude Code agents to build software products
- Each agent runs in its own repo clone with GSD (Get Shit Done) workflow
- Agents are isolated: each owns specific directories, never writes outside them
- A monitor loop supervises agents (liveness, stuck detection, plan gate)
- Plans are gated: agents plan, you/PM review, then agents execute

## How projects work
1. Owner discusses what to build with you (here in #strategist)
2. You help shape the blueprint, interfaces, and milestone scope
3. Owner runs `/new-project <name>` to create Discord channels
4. Owner provides agents.yaml (agent roster) and context docs
5. CLI: `vco init <name> -c agents.yaml --blueprint ... --interfaces ... --milestone ...`
6. CLI: `vco clone <name>` — creates per-agent repo clones
7. CLI: `vco dispatch <name> --all --command "/gsd:plan-phase 1 --auto"` — agents start working
8. Monitor + plan gate handle the rest. You review escalations.

## Your role
- Strategic advisor: product vision, priorities, cross-agent coordination
- You answer questions from the PM tier when it's not confident
- You guide the owner through project setup and milestone planning
- You know the current status of all projects and agents

## Communication style
- Direct, concise, opinionated when you have a view
- Push back when something doesn't make sense
- Ask clarifying questions rather than assuming
- Never say "as an AI" or "I'd be happy to help"
"""


class StrategistConversation:
    """Manages a persistent Claude CLI conversation via --resume.

    Each send() call uses `claude -p --resume vco-strategist --output-format text`
    which continues the existing conversation and returns only the final text
    response (no tool calls shown).
    """

    def __init__(
        self,
        persona_path: Path | None = None,
        session_id: str = _SESSION_UUID,
    ) -> None:
        self._system_prompt = self._load_persona(persona_path)
        self._session_id = session_id
        self._initialized = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _load_persona(persona_path: Path | None) -> str:
        """Load persona from file, falling back to DEFAULT_PERSONA."""
        if persona_path is None:
            return DEFAULT_PERSONA
        if not persona_path.exists():
            logger.warning(
                "Persona file %s not found, using default persona", persona_path
            )
            return DEFAULT_PERSONA
        content = persona_path.read_text().strip()
        if not content:
            logger.warning(
                "Persona file %s is empty, using default persona", persona_path
            )
            return DEFAULT_PERSONA
        return content

    async def send(self, content: str) -> str:
        """Send a message and get the Strategist's response.

        Acquires the conversation lock to prevent concurrent interleaving.
        First call always creates session with --session-id + --system-prompt.
        Subsequent calls use --resume.

        If session-id is already taken (from a prior run), --session-id fails
        and we fall back to --resume. The system prompt from the prior session
        persists in that case.

        Args:
            content: The message to send.

        Returns:
            The Strategist's text response.
        """
        async with self._lock:
            if self._initialized:
                return await self._exec_claude(
                    self._resume_command(), content
                )

            # First call: try to create new session with system prompt
            result = await self._exec_claude(
                self._create_command(), content, allow_failure=True
            )
            if result is not None:
                self._initialized = True
                logger.info("Strategist created new session: %s", self._session_id)
                return result

            # Session already exists from prior run — resume it
            logger.info("Session %s already exists, resuming", self._session_id)
            result = await self._exec_claude(
                self._resume_command(), content
            )
            self._initialized = True
            return result

    async def _exec_claude(
        self, cmd: list[str], content: str, *, allow_failure: bool = False
    ) -> str | None:
        """Execute a claude CLI command and return the response.

        Args:
            cmd: CLI command args.
            content: Message to send via stdin.
            allow_failure: If True, return None on failure instead of error message.

        Returns:
            Response text, or None if allow_failure and command failed.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=content.encode()),
                timeout=300,
            )
        except asyncio.TimeoutError:
            logger.error("Strategist timed out after 300s")
            if allow_failure:
                return None
            return "I need more time to think about that. Could you rephrase or simplify the question?"
        except Exception:
            logger.exception("Failed to run Claude CLI")
            if allow_failure:
                return None
            return "Something went wrong on my end. Try again?"

        if proc.returncode != 0:
            stderr_text = stderr.decode()[:500]
            logger.warning("Claude CLI exited with code %d: %s", proc.returncode, stderr_text)
            if allow_failure:
                return None
            return "I hit a snag. Try asking again?"

        response = stdout.decode().strip()
        return response if response else "I don't have a response for that."

    def _resume_command(self) -> list[str]:
        """Build command to resume existing session.

        Always includes --system-prompt so the persona persists across
        every call, not just the first one.
        """
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", "",
            "--system-prompt", self._system_prompt,
            "--resume", self._session_id,
        ]

    def _create_command(self) -> list[str]:
        """Build command to create new session with system prompt."""
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", "",
            "--system-prompt", self._system_prompt,
            "--session-id", self._session_id,
        ]

    @property
    def session_id(self) -> str:
        """Return the session UUID."""
        return self._session_id
