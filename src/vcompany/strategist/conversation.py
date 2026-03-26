"""Persistent Strategist conversation manager.

Uses Claude Code CLI with -p --resume for persistent conversation.
Each send() call continues the same session, preserving full history.
Output format is text-only (no tool call noise in Discord).

Per Pitfall 8: asyncio.Lock prevents concurrent message interleaving.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Session name for the Strategist — stable across restarts
_SESSION_NAME = "vco-strategist"

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
        session_name: str = _SESSION_NAME,
    ) -> None:
        self._system_prompt = self._load_persona(persona_path)
        self._session_name = session_name
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
        Uses -p --resume for conversation persistence. First call uses
        --system-prompt to initialize the session.

        Args:
            content: The message to send.

        Returns:
            The Strategist's text response.
        """
        async with self._lock:
            cmd = self._build_command()

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=content.encode()),
                    timeout=300,  # 5 min max per response
                )
            except asyncio.TimeoutError:
                logger.error("Strategist timed out after 300s")
                return "I need more time to think about that. Could you rephrase or simplify the question?"
            except Exception:
                logger.exception("Failed to run Claude CLI")
                return "Something went wrong on my end. Try again?"

            if proc.returncode != 0:
                logger.error(
                    "Claude CLI exited with code %d: %s",
                    proc.returncode,
                    stderr.decode()[:500],
                )
                return "I hit a snag. Try asking again?"

            response = stdout.decode().strip()

            if not self._initialized:
                self._initialized = True
                logger.info("Strategist session initialized: %s", self._session_name)

            return response if response else "I don't have a response for that."

    def _build_command(self) -> list[str]:
        """Build the claude CLI command."""
        cmd = [
            "claude",
            "-p",
            "--output-format", "text",
        ]

        if not self._initialized:
            # First call: create session with system prompt
            cmd.extend(["--session-id", self._session_name])
            cmd.extend(["--system-prompt", self._system_prompt])
        else:
            # Subsequent calls: resume existing session
            cmd.extend(["--resume", self._session_name])

        return cmd

    @property
    def session_name(self) -> str:
        """Return the session name."""
        return self._session_name
