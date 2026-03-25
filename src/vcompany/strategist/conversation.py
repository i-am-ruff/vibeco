"""Persistent Strategist conversation manager.

Manages a long-running Claude API conversation with token tracking
and automatic Knowledge Transfer handoff when approaching context limits.

Per D-10: Strategist runs as a persistent Claude API conversation
    (messages array accumulating over time). Opus model with 1M context.
Per D-12: Context limit handoff at ~800K tokens with KT document.
Per Pitfall 2: Rough estimate between real API token counts.
Per Pitfall 7: Graceful fallback when persona file is missing.
Per Pitfall 8: asyncio.Lock prevents concurrent message interleaving.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

from vcompany.strategist.knowledge_transfer import generate_knowledge_transfer

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

DEFAULT_PERSONA = (
    "You are a strategic advisor and PM for a software development project. "
    "You provide thoughtful, direct guidance on architecture, prioritization, "
    "and team coordination. You communicate like a trusted colleague, not an AI assistant."
)

TOKEN_LIMIT = 800_000
"""Trigger Knowledge Transfer when token count reaches this threshold (D-12)."""

TOKEN_CHECK_THRESHOLD = 700_000
"""Only call count_tokens API when rough estimate exceeds this (Pitfall 2)."""

ROUGH_CHARS_PER_TOKEN = 4
"""Approximate characters per token for rough estimation (Pitfall 2)."""

TOKEN_CHECK_INTERVAL = 10
"""Check tokens via API every N messages when rough estimate is high (Pitfall 2)."""


class StrategistConversation:
    """Manages a persistent Claude API conversation with KT handoff.

    The conversation accumulates messages over time. When approaching
    the token limit, it auto-generates a Knowledge Transfer document
    and resets the conversation with the KT as foundation.
    """

    def __init__(
        self,
        client: AsyncAnthropic,
        persona_path: Path | None = None,
        model: str = "claude-opus-4-6",
    ) -> None:
        self._client = client
        self._model = model
        self._system_prompt = self._load_persona(persona_path)
        self._messages: list[dict] = []
        self._total_tokens: int = 0
        self._message_count_since_check: int = 0
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
        (Pitfall 8). Appends the user message, checks tokens, streams
        the response, and appends the assistant reply.

        Args:
            content: The message content to send.
            role: The message role (default "user").

        Yields:
            Text chunks from the streaming response.
        """
        async with self._lock:
            self._messages.append({"role": role, "content": content})
            self._message_count_since_check += 1

            await self._maybe_check_tokens()

            if self._total_tokens >= TOKEN_LIMIT:
                await self._perform_knowledge_transfer()

            full_text = ""
            async with self._client.messages.stream(
                model=self._model,
                system=self._system_prompt,
                messages=self._messages,
                max_tokens=8192,
            ) as stream:
                async for text in stream.text_stream:
                    full_text += text
                    yield text

            self._messages.append({"role": "assistant", "content": full_text})

    async def _maybe_check_tokens(self) -> None:
        """Check token count using rough estimate, then API if needed.

        Per Pitfall 2: Use rough char/4 estimate first. Only call the
        count_tokens API when the rough estimate exceeds TOKEN_CHECK_THRESHOLD.
        Also respects TOKEN_CHECK_INTERVAL to avoid excessive API calls.
        """
        # Rough estimate: total chars / ROUGH_CHARS_PER_TOKEN
        total_chars = sum(len(m["content"]) for m in self._messages)
        rough_tokens = total_chars // ROUGH_CHARS_PER_TOKEN

        if rough_tokens < TOKEN_CHECK_THRESHOLD:
            return  # Far from limit, skip API call

        # Rough estimate is above threshold -- check if we should call the API.
        # Always call if we haven't gotten a real count yet (_total_tokens == 0)
        # or if the rough estimate is above TOKEN_LIMIT (urgent).
        # Otherwise, respect the interval to avoid excessive API calls.
        if (
            self._message_count_since_check < TOKEN_CHECK_INTERVAL
            and self._total_tokens > 0
            and rough_tokens < TOKEN_LIMIT
        ):
            return

        result = await self._client.messages.count_tokens(
            model=self._model,
            system=self._system_prompt,
            messages=self._messages,
        )
        self._total_tokens = result.input_tokens
        self._message_count_since_check = 0

    async def _perform_knowledge_transfer(self) -> None:
        """Generate a KT document and reset the conversation.

        Per D-12: Self-generates a Knowledge Transfer document capturing
        decisions, personality calibration, project state, and open threads.
        Fresh session starts with the KT document as foundation.
        """
        logger.info(
            "Performing Knowledge Transfer at %d tokens", self._total_tokens
        )
        kt_doc = generate_knowledge_transfer(
            self._messages, self._system_prompt, self._total_tokens
        )
        self._messages = [
            {
                "role": "user",
                "content": (
                    "[KNOWLEDGE TRANSFER]\n\n"
                    f"{kt_doc}\n\n"
                    "Please acknowledge you have received this knowledge transfer "
                    "and are ready to continue."
                ),
            }
        ]
        self._total_tokens = 0
        self._message_count_since_check = 0
        logger.info("Knowledge Transfer complete, conversation reset")

    @property
    def messages(self) -> list[dict]:
        """Return a copy of the messages list."""
        return list(self._messages)

    @property
    def token_count(self) -> int:
        """Return the current tracked token count."""
        return self._total_tokens
