"""Persistent Strategist conversation manager.

Uses Claude Code CLI with -p --resume for persistent conversation.
Each send() call continues the same session, preserving full history.
Output format is text-only (no tool call noise in Discord).

Per Pitfall 8: asyncio.Lock prevents concurrent message interleaving.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Stable UUID for the Strategist session — deterministic from a fixed seed
# so it survives restarts. uuid5 with DNS namespace + version string.
# Bump the version string to force a new session (e.g., after persona changes).
_SESSION_VERSION = "vco-strategist-v4"
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


def _describe_tool_use(block: dict) -> str | None:
    """Convert a tool_use block into a short human-readable description."""
    name = block.get("name", "")
    inp = block.get("input", {})
    if name == "Read":
        path = inp.get("file_path", "")
        short = path.split("/")[-1] if "/" in path else path
        return f"reading {short}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"running: {cmd[:80]}"
    if name in ("Write", "Edit"):
        path = inp.get("file_path", "")
        short = path.split("/")[-1] if "/" in path else path
        return f"editing {short}"
    if name == "Glob":
        return f"searching: {inp.get('pattern', '')}"
    if name == "Grep":
        return f"grep: {inp.get('pattern', '')}"
    if name:
        return f"using {name}"
    return None


_STYLE_REMINDER = (
    "[REMINDER ON YOUR PERSONA: "
    "You are drifting. Write like a real human on discord, not an AI. "
    "No separated paragraphs for each thought - let it flow like one message. "
    "No numbered lists, no bullet points, no bold, no headers. "
    "No 'Great question!', no 'Let me break this down', no 'Here are the key areas'. "
    "Mix capitalization naturally. Swear casually. Be funny, sarcastic, direct. "
    "When you have two options to present, just say them inline like 'i can either fix it properly or hack it for now, your call'. "
    "NOT as a formatted list. One flowing block of text like you'd actually type in discord. "
    "END OF REMINDER.]"
)


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
        allowed_tools: str = "Bash Read Write",
    ) -> None:
        self._system_prompt = self._load_persona(persona_path)
        self._session_id = session_id
        self._allowed_tools = allowed_tools
        self._initialized = False
        self._lock = asyncio.Lock()
        self._message_count = 0
        self._reinject_every = 10  # re-inject style reminder every N messages

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

        First call: creates session and sends persona as the first message
        (not as --system-prompt). This bakes the persona into conversation
        history where it persists across all future --resume calls and
        benefits from prompt caching automatically.

        Subsequent calls: resume with just the user message.

        Args:
            content: The message to send.

        Returns:
            The Strategist's text response.
        """
        async with self._lock:
            if self._initialized:
                self._message_count += 1
                # Re-inject style reminder periodically to fight persona drift
                if self._message_count % self._reinject_every == 0:
                    content = f"{_STYLE_REMINDER}\n\n{content}"
                return await self._exec_claude(
                    self._resume_command(), content
                )

            # First call: try to resume (session may exist from prior run)
            result = await self._exec_claude(
                self._resume_command(), content, allow_failure=True
            )
            if result is not None:
                self._initialized = True
                logger.info("Strategist resumed existing session: %s", self._session_id)
                return result

            # No existing session — create new one with persona as first message
            logger.info("Creating new Strategist session: %s", self._session_id)
            persona_result = await self._exec_claude(
                self._create_command(), self._system_prompt
            )
            if persona_result is None:
                return "Failed to initialize Strategist session."
            logger.info("Persona loaded. Strategist ready.")

            # Now send the actual user message
            self._initialized = True
            return await self._exec_claude(
                self._resume_command(), content
            )

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
                timeout=600,
            )
        except asyncio.TimeoutError:
            logger.error("Strategist timed out after 600s")
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

    async def send_streaming(
        self, content: str, on_tool_use: callable | None = None
    ) -> str:
        """Send a message and stream progress via callback.

        Like send(), but uses stream-json to report tool usage in real-time.
        Calls on_tool_use(description: str) for each tool action detected.

        Args:
            content: The message to send.
            on_tool_use: Async callback called with a human-readable description
                        of each tool action (e.g., "Reading src/foo.py").

        Returns:
            The final text response.
        """
        async with self._lock:
            if not self._initialized:
                # Initialize session first (non-streaming, just setup)
                result = await self._exec_claude(
                    self._resume_command_text(), content, allow_failure=True
                )
                if result is not None:
                    self._initialized = True
                    return result

                persona_result = await self._exec_claude(
                    self._create_command_text(), self._system_prompt
                )
                if persona_result is None:
                    return "Failed to initialize session."
                self._initialized = True

            # Re-inject style reminder periodically
            self._message_count += 1
            if self._message_count % self._reinject_every == 0:
                content = f"{_STYLE_REMINDER}\n\n{content}"

            # Stream the actual response
            cmd = self._resume_command_stream()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                proc.stdin.write(content.encode())
                await proc.stdin.drain()
                proc.stdin.close()

                final_text = ""
                async for line in proc.stdout:
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")

                    # Tool use events
                    if etype == "assistant" and on_tool_use:
                        msg = event.get("message", {})
                        for block in msg.get("content", []):
                            if block.get("type") == "tool_use":
                                desc = _describe_tool_use(block)
                                if desc:
                                    await on_tool_use(desc)

                    # Final result
                    if etype == "result":
                        final_text = event.get("result", "")

                await proc.wait()
                return final_text if final_text else "Done (no text response)."

            except asyncio.TimeoutError:
                return "Timed out on that task."
            except Exception:
                logger.exception("Streaming send failed")
                return "Something went wrong."

    def _resume_command_text(self) -> list[str]:
        """Resume command with text output (for init/simple sends)."""
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--resume", self._session_id,
        ]

    def _create_command_text(self) -> list[str]:
        """Create command with text output (for init)."""
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--session-id", self._session_id,
        ]

    def _resume_command_stream(self) -> list[str]:
        """Resume command with stream-json output (for streaming progress)."""
        return [
            "claude", "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", self._allowed_tools,
            "--resume", self._session_id,
        ]

    def _resume_command(self) -> list[str]:
        """Build command to resume existing session."""
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--resume", self._session_id,
        ]

    def _create_command(self) -> list[str]:
        """Build command to create a new session.

        No --system-prompt here. The persona is sent as the first USER
        message instead, which bakes it into conversation history where
        it persists across all --resume calls and benefits from prompt
        caching automatically.
        """
        return [
            "claude", "-p",
            "--output-format", "text",
            "--allowedTools", self._allowed_tools,
            "--session-id", self._session_id,
        ]

    @property
    def session_id(self) -> str:
        """Return the session UUID."""
        return self._session_id
