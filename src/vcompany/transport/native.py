"""NativeTransport — local subprocess implementation of ChannelTransport.

Spawns vco-worker as a local Python subprocess with stdin/stdout piped
for NDJSON channel protocol communication. Used when agents run directly
on the host machine without containerization.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logger = logging.getLogger("vcompany.transport.native")


class NativeTransport:
    """Spawn vco-worker as a local subprocess.

    The simplest ChannelTransport implementation: runs vco-worker using
    the current Python interpreter as a child process with piped I/O.
    """

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> asyncio.subprocess.Process:
        """Spawn vco-worker as a local subprocess.

        Uses sys.executable to ensure the same Python interpreter is used.
        Merges the current environment with any additional env vars provided.
        """
        cmd = [sys.executable, "-m", "vco_worker"]

        # Build merged environment
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        merged_env["VCO_AGENT_ID"] = agent_id

        logger.info("Spawning vco-worker for agent %s (cwd=%s)", agent_id, working_dir)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=merged_env,
        )

        self._processes[agent_id] = process
        logger.info(
            "Worker spawned for agent %s (pid=%d)", agent_id, process.pid or -1
        )
        return process

    async def terminate(self, agent_id: str) -> None:
        """Terminate the local subprocess for an agent.

        Sends SIGTERM first, waits up to 5 seconds, then SIGKILL.
        """
        process = self._processes.pop(agent_id, None)
        if process is None:
            logger.warning("No process found for agent %s", agent_id)
            return

        logger.info("Terminating worker for agent %s", agent_id)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(
                "Worker for agent %s did not exit after SIGTERM, sending SIGKILL",
                agent_id,
            )
            process.kill()

    @property
    def transport_type(self) -> str:
        """Return 'native' transport type."""
        return "native"
