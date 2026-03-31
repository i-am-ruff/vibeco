# Phase 32: Transport Channel Implementations - Research

**Researched:** 2026-03-31
**Domain:** Transport layer refactoring -- Docker and native transports using channel protocol
**Confidence:** HIGH

## Summary

Phase 32 replaces the v3.1 transport implementations (socket-mount Docker, tmux-based local) with channel-protocol-based transports. The channel protocol (NDJSON over stdin/stdout) is already defined (Phase 29) and the worker runtime (Phase 30) already consumes it. AgentHandle (Phase 31) already speaks the protocol to a subprocess. The gap is that `CompanyRoot.hire()` spawns `python -m vco_worker` directly as a local subprocess -- it does not go through a transport abstraction, and the Docker transport still uses the old v3.1 pattern (socket mounts, tmux-inside-container, `docker exec`).

The work is: (1) create a new `NativeTransport` that spawns vco-worker as a local subprocess with stdin/stdout piped (replacing the direct subprocess call in `hire()`), (2) create a new `DockerChannelTransport` that starts a Docker container running vco-worker and communicates via `docker exec` stdin/stdout piping or `docker attach`, (3) refactor `CompanyRoot.hire()` to accept a transport parameter and delegate spawning to the transport.

**Primary recommendation:** Create two new transport classes implementing a new `ChannelTransport` protocol (spawn -> returns process-like object with stdin/stdout). Keep the old `AgentTransport` protocol for backward compatibility until Phase 34 removes dead code. The new transports return a process handle that AgentHandle can attach to.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
No explicitly locked decisions -- all implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- Docker transport must NOT mount Unix sockets into containers
- Both transports must produce identical observable behavior (signals, health reports, Discord message routing)
- Phase 29 channel protocol (NDJSON framing) is the wire format
- Phase 30 vco-worker is what runs inside the transport
- Phase 31 AgentHandle + CompanyRoot.hire() spawns workers -- transports need to integrate with this

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHAN-02 | Docker transport uses transport channel instead of Unix socket mount -- vco-worker inside Docker talks through the channel, not a mounted socket | New DockerChannelTransport class that runs vco-worker inside container, pipes NDJSON via docker exec or docker attach stdin/stdout |
| CHAN-03 | Native transport uses transport channel (local socket or in-process bridge) | New NativeTransport class that spawns vco-worker as local subprocess with stdin/stdout piped -- essentially extracting the current `hire()` subprocess logic into a transport |
</phase_requirements>

## Architecture Patterns

### Current State (what exists)

```
CompanyRoot.hire()
  |-- directly spawns: asyncio.create_subprocess_exec("python", "-m", "vco_worker")
  |-- attaches process to AgentHandle
  |-- starts _channel_reader on process.stdout

Old DockerTransport (v3.1):
  |-- creates Docker container with socket mounts, tmux inside
  |-- uses docker exec for commands
  |-- NO channel protocol -- uses exec/send_keys interface

Old LocalTransport (v3.1):
  |-- uses TmuxManager for interactive, subprocess for piped
  |-- NO channel protocol -- uses exec/send_keys interface
```

### Target State (what Phase 32 builds)

```
CompanyRoot.hire(transport="native"|"docker")
  |-- calls transport.spawn(agent_id, config) -> process-like handle
  |-- attaches returned process to AgentHandle
  |-- starts _channel_reader on process.stdout (unchanged)

NativeTransport.spawn():
  |-- asyncio.create_subprocess_exec("python", "-m", "vco_worker")
  |-- returns process with stdin/stdout piped

DockerChannelTransport.spawn():
  |-- docker run/create container with vco-worker as entrypoint
  |-- pipes stdin/stdout through docker attach or docker exec
  |-- NO socket mounts, NO shared filesystem, NO tmux inside
  |-- returns process-like wrapper with stdin/stdout
```

### Recommended Project Structure

```
src/vcompany/transport/
  channel/              # Phase 29 protocol (unchanged)
    __init__.py
    messages.py
    framing.py
  protocol.py           # Old AgentTransport protocol (kept for Phase 34 compat)
  channel_transport.py  # NEW: ChannelTransport protocol + base class
  native.py             # NEW: NativeTransport (subprocess-based)
  docker_channel.py     # NEW: DockerChannelTransport (docker-based)
  local.py              # Old LocalTransport (kept for Phase 34 compat)
  docker.py             # Old DockerTransport (kept for Phase 34 compat)
  __init__.py           # Updated exports
```

### Pattern 1: ChannelTransport Protocol

**What:** A new protocol focused on spawning a worker process and returning a stdin/stdout handle. Much simpler than the old AgentTransport which had exec, send_keys, read_file, etc.

**When to use:** All new transport implementations.

**Example:**
```python
from __future__ import annotations
import asyncio
from typing import Protocol, runtime_checkable

@runtime_checkable
class ChannelTransport(Protocol):
    """Transport that spawns a vco-worker and returns a process handle.

    The ONLY interface between head and worker is the channel protocol
    (NDJSON over stdin/stdout of the returned process).
    """

    async def spawn(
        self,
        agent_id: str,
        *,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> asyncio.subprocess.Process:
        """Spawn a vco-worker process. Returns process with stdin/stdout piped.

        The caller (CompanyRoot.hire) sends StartMessage via stdin and reads
        WorkerMessages from stdout. The transport is responsible for:
        - Creating the execution environment (local process or Docker container)
        - Ensuring vco-worker is available in that environment
        - Piping stdin/stdout back to the caller
        """
        ...

    async def terminate(self, agent_id: str) -> None:
        """Force-terminate the execution environment for an agent."""
        ...

    @property
    def transport_type(self) -> str:
        """Return transport type identifier ('native' or 'docker')."""
        ...
```

### Pattern 2: Docker stdin/stdout Piping

**What:** Docker containers running vco-worker with stdin/stdout as the channel.

**Key insight:** `docker run -i` (interactive without tty) gives us stdin pipe. Combined with the fact that vco-worker already writes to stdout and reads from stdin, the Docker transport just needs to pipe through `docker run -i` or `docker attach`.

**Two approaches:**

1. **`docker run -i` (recommended):** Start container with `docker run -i --rm vco-agent:latest python -m vco_worker`. The subprocess IS the docker client piping stdin/stdout. Simple, clean.

2. **`docker exec -i`:** Create container first (like current DockerTransport), then `docker exec -i container_name python -m vco_worker`. More complex, but allows container reuse.

**Recommended: Use `subprocess` to run `docker run -i`** -- this avoids docker-py SDK complexity for streaming stdin/stdout (docker-py's attach API is awkward for bidirectional streaming). The `asyncio.create_subprocess_exec` approach gives us native async stdin/stdout streams that work identically to the native transport.

```python
class DockerChannelTransport:
    async def spawn(self, agent_id: str, *, env=None, working_dir=None):
        container_name = f"vco-{agent_id}"
        cmd = [
            "docker", "run",
            "-i",                    # stdin open, no tty
            "--rm",                  # auto-remove on exit
            "--name", container_name,
            "--network", "none",     # isolated
        ]
        # Pass env vars
        if env:
            for k, v in env.items():
                cmd.extend(["-e", f"{k}={v}"])
        # Mount working dir if provided
        if working_dir:
            cmd.extend(["-v", f"{working_dir}:/workspace", "-w", "/workspace"])

        cmd.extend([self._image, "python", "-m", "vco_worker"])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return process
```

### Pattern 3: NativeTransport (extracted from hire())

**What:** The subprocess spawning that currently lives in `CompanyRoot.hire()` moved into a transport class.

```python
class NativeTransport:
    async def spawn(self, agent_id: str, *, env=None, working_dir=None):
        import sys
        worker_cmd = [sys.executable, "-m", "vco_worker"]
        process = await asyncio.create_subprocess_exec(
            *worker_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return process
```

### Pattern 4: CompanyRoot.hire() Refactored

**What:** `hire()` delegates subprocess creation to the transport instead of hardcoding it.

```python
async def hire(self, agent_id, template="generic", agent_type=None,
               channel_id=None, transport_name="native"):
    # ... existing artifact setup ...

    # Get transport
    transport = self._get_transport(transport_name)

    # Spawn worker through transport
    process = await transport.spawn(
        agent_id,
        env={"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")},
        working_dir=str(working_dir),
    )
    handle._process = process

    # Rest unchanged: send StartMessage, start channel reader
```

### Anti-Patterns to Avoid

- **Mounting sockets into Docker containers:** This violates the core v4 principle. The channel protocol IS the boundary. No daemon socket, no signal socket.
- **Using docker-py SDK for stdin/stdout streaming:** docker-py's `attach()` returns a socket object that doesn't integrate well with asyncio. Use `subprocess` + `docker run -i` instead.
- **Running tmux inside Docker containers:** vco-worker handles its own lifecycle. Tmux inside Docker was a v3.1 pattern for interactive agents; the channel protocol replaces it.
- **Sharing filesystem between head and worker:** Working directory mounting is acceptable for now (agent needs a workspace), but no state files should be shared. The channel is the only communication path.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker stdin/stdout piping | Custom socket-based docker attach wrapper | `asyncio.create_subprocess_exec("docker", "run", "-i", ...)` | Gives identical Process interface to native transport; avoids docker-py streaming complexity |
| NDJSON framing | Custom protocol | Phase 29 `encode()`/`decode_worker()`/`decode_head()` | Already exists and tested |
| Worker lifecycle | Custom container management | Phase 30 `vco-worker` package | Already handles StartMessage, health reporting, etc. |
| Process-to-AgentHandle wiring | Custom wiring logic | Phase 31 `AgentHandle.attach_process()` + `_channel_reader()` | Already exists in CompanyRoot |

**Key insight:** The heavy lifting is already done in Phases 29-31. This phase is primarily about creating two thin transport wrappers and refactoring `hire()` to use them.

## Common Pitfalls

### Pitfall 1: Docker TTY Corruption

**What goes wrong:** Using `docker run -it` (with TTY) corrupts NDJSON output with terminal escape sequences.
**Why it happens:** TTY mode adds carriage returns, wraps lines, and injects control sequences into stdout.
**How to avoid:** Use `docker run -i` (stdin open) WITHOUT `-t` (no TTY). The worker writes to stdout.buffer directly -- no TTY needed.
**Warning signs:** JSON parse errors on worker messages, `\r\n` line endings, escape sequences in output.

### Pitfall 2: Docker Container Cleanup

**What goes wrong:** Orphaned containers pile up when workers crash or daemon restarts.
**Why it happens:** `docker run` without `--rm` leaves stopped containers. With `--rm`, crash leaves no trace for debugging.
**How to avoid:** Use `--rm` for normal operation. Track container names in AgentHandle so `terminate()` can `docker kill` explicitly. Consider adding a cleanup sweep on daemon start.
**Warning signs:** `docker ps -a` shows many stopped vco-* containers.

### Pitfall 3: Docker Image Missing vco-worker

**What goes wrong:** `python -m vco_worker` fails inside the Docker container because vco-worker package is not installed.
**Why it happens:** Current Dockerfile installs the main `vcompany` package but not the separate `vco-worker` package.
**How to avoid:** Update Dockerfile to also install vco-worker. Or: copy the worker package into the image and install it.
**Warning signs:** `ModuleNotFoundError: No module named 'vco_worker'` in container stderr.

### Pitfall 4: Stderr Handling Differences

**What goes wrong:** Worker logs (written to stderr) behave differently between native and Docker.
**Why it happens:** Native transport gets stderr as a separate pipe. Docker `run -i` intermixes or drops stderr depending on flags.
**How to avoid:** Always capture stderr separately. For Docker, the subprocess stderr IS docker's stderr passthrough. Log it consistently.
**Warning signs:** Missing worker logs in Docker mode, or logs appearing in stdout corrupting the channel.

### Pitfall 5: Working Directory Semantics

**What goes wrong:** Native transport uses host filesystem directly. Docker transport needs volume mount.
**Why it happens:** Different execution environments have different filesystem contexts.
**How to avoid:** Pass working_dir to transport.spawn(). NativeTransport sets cwd; DockerChannelTransport adds `-v working_dir:/workspace`.
**Warning signs:** FileNotFoundError in worker, wrong paths in agent artifacts.

## Code Examples

### Dockerfile Update for vco-worker

The current Dockerfile needs to include vco-worker. Add after the vcompany install:

```dockerfile
# Install vco-worker package (Phase 30)
COPY packages/vco-worker/ /opt/vco-worker/
RUN cd /opt/vco-worker && uv pip install --system -e .
```

### Docker Process Wrapper (if needed)

If `docker run -i` process returncode behavior differs from native subprocess, a thin wrapper normalizes it:

```python
class DockerProcess:
    """Wrapper to make docker run -i subprocess look like a native process."""

    def __init__(self, process: asyncio.subprocess.Process, container_name: str):
        self._process = process
        self._container_name = container_name

    @property
    def stdin(self):
        return self._process.stdin

    @property
    def stdout(self):
        return self._process.stdout

    @property
    def returncode(self):
        return self._process.returncode

    def terminate(self):
        # docker kill is more reliable than terminating the docker client process
        import subprocess
        subprocess.run(["docker", "kill", self._container_name],
                       capture_output=True)
        self._process.terminate()

    def kill(self):
        import subprocess
        subprocess.run(["docker", "kill", self._container_name],
                       capture_output=True)
        self._process.kill()

    async def wait(self):
        return await self._process.wait()
```

### Integration Test Pattern

Both transports should produce identical behavior. Test with:

```python
async def test_transport_behavioral_equivalence(transport):
    """Both native and docker transport pass this same test."""
    process = await transport.spawn("test-agent")

    # Send StartMessage
    start = StartMessage(agent_id="test-agent", config={"handler_type": "session"})
    process.stdin.write(encode(start))
    await process.stdin.drain()

    # Read "ready" signal
    line = await process.stdout.readline()
    msg = decode_worker(line)
    assert isinstance(msg, SignalMessage)
    assert msg.signal == "ready"

    # Send HealthCheck
    process.stdin.write(encode(HealthCheckMessage()))
    await process.stdin.drain()

    line = await process.stdout.readline()
    msg = decode_worker(line)
    assert isinstance(msg, HealthReportMessage)

    # Send Stop
    process.stdin.write(encode(StopMessage()))
    await process.stdin.drain()

    line = await process.stdout.readline()
    msg = decode_worker(line)
    assert isinstance(msg, SignalMessage)
    assert msg.signal == "stopped"
```

## State of the Art

| Old Approach (v3.1) | New Approach (v4/Phase 32) | Impact |
|----------------------|---------------------------|--------|
| AgentTransport with exec/send_keys/read_file | ChannelTransport with spawn/terminate | 90% simpler protocol -- transport only creates execution env |
| Socket mount into Docker | NDJSON over stdin/stdout piped through docker run | No host-container coupling beyond volume mount for workspace |
| Tmux inside Docker for interactive agents | vco-worker manages its own agent process | Container is self-managing, head doesn't know internals |
| docker-py SDK for all Docker ops | subprocess `docker run -i` for spawning, docker-py optional for management | Better asyncio integration for the critical stdin/stdout path |

## Open Questions

1. **Container reuse across dismiss/hire cycles**
   - What we know: v3.1 DockerTransport reused containers (stop, not remove). Phase 32 uses `docker run --rm`.
   - What's unclear: Should Docker transport support container reuse for faster re-hire?
   - Recommendation: Use `--rm` for now. Container reuse is a Phase 33 concern (AUTO-03: container survives daemon restart).

2. **Working directory mount for Docker**
   - What we know: Agents need a working directory for tasks. Native transport uses host fs directly.
   - What's unclear: Should Docker transport mount the working dir, or should files go through channel protocol?
   - Recommendation: Mount working dir as volume for now (`-v host_dir:/workspace`). The SendFile channel message exists for cross-environment file transfer, but workspace mounting is simpler and sufficient for single-machine v4.

3. **vco-worker installation in Docker image**
   - What we know: Current Dockerfile doesn't include vco-worker package.
   - What's unclear: Should we update the existing Dockerfile or create a new one?
   - Recommendation: Update existing Dockerfile to add vco-worker install step. One universal image principle (D-03) still applies.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker | DockerChannelTransport | Yes | 28.2.2 | -- |
| Python 3.12 | NativeTransport / vco-worker | Yes | 3.12.3 | -- |
| vco-worker package | Both transports | Yes (in packages/) | 0.1.0 | -- |
| docker-py SDK | Legacy DockerTransport (kept) | Yes (in deps) | -- | Not needed for new transport |

**Missing dependencies with no fallback:** None.

## Project Constraints (from CLAUDE.md)

- Use `subprocess` for Docker commands, not docker-py SDK for stdin/stdout streaming (aligns with CLAUDE.md: "subprocess over GitPython" pattern applies to Docker too)
- Use `asyncio.create_subprocess_exec` in async contexts
- No database -- routing state stays in YAML/JSON files
- Pydantic v2 for all models
- Python 3.12+
- Avoid GitPython, requests, poetry, argparse, celery, SQLAlchemy, Flask/FastAPI
- docker-py is acceptable for management operations (list, inspect, remove) but subprocess `docker run` is cleaner for the spawn path

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/vcompany/transport/channel/` -- Phase 29 channel protocol
- Codebase inspection: `packages/vco-worker/src/vco_worker/main.py` -- Phase 30 worker entry point
- Codebase inspection: `src/vcompany/daemon/agent_handle.py` -- Phase 31 AgentHandle
- Codebase inspection: `src/vcompany/supervisor/company_root.py` -- Phase 31 CompanyRoot.hire()
- Codebase inspection: `src/vcompany/transport/docker.py` -- v3.1 DockerTransport (being replaced)
- Codebase inspection: `src/vcompany/transport/local.py` -- v3.1 LocalTransport (being replaced)
- Codebase inspection: `docker/Dockerfile` -- current agent image

### Secondary (MEDIUM confidence)
- Docker CLI documentation -- `docker run -i` stdin/stdout behavior is well-documented standard behavior

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all components already exist, this is integration work
- Architecture: HIGH - pattern is clear from existing code (extract subprocess into transport, add Docker variant)
- Pitfalls: HIGH - Docker stdin/stdout behavior and TTY corruption are well-known issues

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- internal refactoring, no external dependencies changing)
