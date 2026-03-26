"""Persistent Strategist conversation manager.

Uses the Claude Code CLI with --session-id for persistent conversation sessions.
Claude CLI manages its own context window, so no manual token tracking needed.

Per Pitfall 7: Graceful fallback when persona file is missing.
Per Pitfall 8: asyncio.Lock prevents concurrent message interleaving.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PERSONA = (
    "You are a strategic advisor and PM for a software development project. "
    "You provide thoughtful, direct guidance on architecture, prioritization, "
    "and team coordination. You communicate like a trusted colleague, not an AI assistant."
)


class StrategistConversation:
    """Manages a persistent Claude CLI conversation via --session-id/--resume.

    The conversation is maintained across calls using a stable session ID.
    Claude CLI handles context management internally, so no manual token
    tracking or Knowledge Transfer is needed.
    """

    def __init__(
        self,
        persona_path: Path | None = None,
        model: str = "opus",
    ) -> None:
        self._model = model
        self._system_prompt = self._load_persona(persona_path)
        self._session_id = str(uuid.uuid4())
        self._first_send = True
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

    async def send(self, content: str, role: str = "user") -> AsyncGenerator[str, None]:
        """Send a message and stream the assistant's response.

        Acquires the conversation lock to prevent concurrent interleaving
        (Pitfall 8). Uses Claude CLI with --resume for conversation persistence.

        On first call, uses --session-id with --system-prompt to start a new
        session. On subsequent calls, uses --resume to continue the conversation.

        Args:
            content: The message content to send.
            role: The message role (default "user").

        Yields:
            Text chunks from the streaming response.
        """
        async with self._lock:
            cmd = self._build_command()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Send content via stdin
            proc.stdin.write(content.encode())
            await proc.stdin.drain()
            proc.stdin.close()

            # Read all stdout
            stdout, _ = await proc.communicate()

            if proc.returncode != 0:
                logger.error("Claude CLI exited with code %d", proc.returncode)
                yield "Strategist encountered an error. Please try again."
                return

            # Parse JSON output: {"type":"result","result":"answer text",...}
            try:
                data = json.loads(stdout.decode())
                result_text = data.get("result", "")
            except (json.JSONDecodeError, UnicodeDecodeError):
                result_text = stdout.decode().strip()

            if self._first_send:
                self._first_send = False

            if result_text:
                yield result_text

    def _build_command(self) -> list[str]:
        """Build the claude CLI command for this send call."""
        cmd = [
            "claude",
            "-p",
            "--output-format", "json",
            "--model", self._model,
            "--tools", "",
        ]

        if self._first_send:
            cmd.extend(["--session-id", self._session_id])
            cmd.extend(["--system-prompt", self._system_prompt])
        else:
            cmd.extend(["--resume", self._session_id])

        return cmd

    @property
    def session_id(self) -> str:
        """Return the stable session ID for this conversation."""
        return self._session_id
