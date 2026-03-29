# Phase 26: Docker Runtime - Research

**Researched:** 2026-03-29
**Domain:** Docker container execution, Python Docker SDK, AgentTransport implementation
**Confidence:** HIGH

## Summary

Phase 26 implements DockerTransport -- the second AgentTransport adapter -- enabling agents to run inside Docker containers with persistent session state. The core work is: (1) implementing the 8-method AgentTransport protocol using docker-py SDK for container lifecycle and exec operations, (2) building a Dockerfile that creates a universal Claude Code agent image with tweakcc patches, and (3) wiring the factory registry so `transport: "docker"` in AgentConfig routes through DockerTransport.

The docker-py SDK (v7.1.0) is the correct choice per CONTEXT.md decision D-12. It provides typed Python APIs for container lifecycle (`containers.create`, `container.start`, `container.stop`), exec operations (`container.exec_run` with `stream=True`), and inspection (`container.status`). Since docker-py is synchronous, all blocking calls must be wrapped in `asyncio.to_thread()` -- the same pattern LocalTransport already uses for libtmux calls.

**Primary recommendation:** Follow LocalTransport's structure closely -- same `_AgentSession` tracking pattern, same `asyncio.to_thread()` wrapping for blocking calls, same interactive/piped mode split. The Docker-specific additions are container lifecycle management (create-once, start/stop reuse) and exec-based command dispatch.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Base image is `node:22-slim`. Install Python 3.12, uv, git, tmux on top.
- **D-02:** Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and apply tweakcc patches at build time. Patches baked into image.
- **D-03:** One universal Docker image for all agent types. Agent differences come from config (AgentConfig), not image contents.
- **D-04:** Deterministic container naming: `vco-{project}-{agent_id}`.
- **D-05:** `docker stop` on teardown, container kept. Explicit `docker rm` for removal.
- **D-06:** Reuse existing containers: stopped -> `docker start`, running -> reuse.
- **D-07:** Bind mount daemon Unix sockets at same path: `-v /tmp/vco-daemon.sock:/tmp/vco-daemon.sock` (and signal socket).
- **D-08:** Bind mount agent work directories from host: `-v /path/to/clone:/workspace`.
- **D-09:** `~/.claude` lives inside container's writable layer. Bake default settings.json at build time.
- **D-10:** tmux runs inside Docker container. DockerTransport uses docker SDK exec into container to interact with tmux.
- **D-11:** Two-layer `is_alive()`: (1) Docker inspect for container running, (2) exec into container to check Claude Code process.
- **D-12:** Use `docker-py` SDK (`import docker`) instead of shelling out to docker CLI.

### Claude's Discretion
- Docker exec command construction for tmux send-keys inside containers
- Dockerfile layer ordering and caching strategy
- How piped mode (Strategist subprocess) maps through Docker exec
- Container network mode (host, bridge, none)
- read_file/write_file implementation (docker cp vs volume path access)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOCK-01 | DockerTransport implements AgentTransport using docker exec for both interactive (tmux inside container) and piped (claude -p) modes | docker-py `container.exec_run()` supports both fire-and-forget (detach=True) and blocking (returns stdout) modes. tmux inside container reached via exec. |
| DOCK-02 | Dockerfile exists for building a Claude Code image with tweakcc patches applied | node:22-slim base, apt-install Python 3.12/git/tmux, npm install claude-code, npx tweakcc --apply. Verified tweakcc 4.0.11 supports --apply flag. |
| DOCK-03 | Docker container receives daemon Unix socket via volume mount so vco CLI commands work from inside | Bind mount `-v /tmp/vco-daemon.sock:/tmp/vco-daemon.sock` and signal socket. docker-py volumes dict supports this directly. |
| DOCK-04 | Docker container mounts agent work directory as a volume for code access | Bind mount `-v {clone_path}:/workspace:rw`. docker-py volumes dict: `{host_path: {'bind': '/workspace', 'mode': 'rw'}}` |
| DOCK-05 | AgentConfig.docker_image field specifies which image to use when transport is "docker" | Add `docker_image: str | None = None` to AgentConfig pydantic model. Factory passes to DockerTransport via transport_deps. |
| DOCK-06 | Persistent Docker containers (docker create + start/stop) preserve ~/.claude session state across agent restarts | `containers.create()` + `container.start()`/`container.stop()`. Container writable layer persists across stop/start. `~/.claude` inside container survives. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| docker (docker-py) | 7.1.0 | Docker SDK for Python | Official Docker SDK. Typed API for container lifecycle, exec, inspect. Locked decision D-12. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tweakcc | 4.0.11 | Claude Code system prompt patches | Dockerfile build step only -- `npx tweakcc --apply` patches installed claude-code |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| docker-py (sync) | aiodocker (async-native) | aiodocker is async but less mature (0.26.0), smaller community, different API surface. docker-py is official Docker SDK. Use asyncio.to_thread() wrapping -- same pattern as LocalTransport with libtmux. Decision D-12 locks docker-py. |
| docker-py | subprocess docker CLI | Simpler but worse error handling for lifecycle operations. exec_run streaming, inspect, and container reuse are awkward with subprocess. D-12 locks docker-py. |

**Installation:**
```bash
uv add docker>=7.1,<8
```

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/transport/
    protocol.py          # AgentTransport protocol (exists)
    local.py             # LocalTransport (exists)
    docker.py            # NEW: DockerTransport
docker/
    Dockerfile           # NEW: Claude Code agent image
    settings.json        # NEW: Default ~/.claude/settings.json baked into image
```

### Pattern 1: DockerTransport Session Tracking
**What:** Mirror LocalTransport's `_AgentSession` dataclass but track container_name and container_id instead of pane_id.
**When to use:** Every DockerTransport method needs to look up the container for a given agent_id.
**Example:**
```python
@dataclass
class _DockerSession:
    """Internal tracking for a Docker-backed agent session."""
    container_name: str
    working_dir: Path          # host path
    container_workdir: str     # container path (e.g., "/workspace")
    interactive: bool = True
    container_id: str | None = None  # set after create/find
```

### Pattern 2: Create-Once Container Lifecycle (DOCK-06)
**What:** `setup()` checks for existing container by name before creating. Reuse stopped or running containers.
**When to use:** Every call to `DockerTransport.setup()`.
**Example:**
```python
async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
    container_name = f"vco-{self._project}-{agent_id}"
    # Try to find existing container (including stopped)
    try:
        container = await asyncio.to_thread(
            self._client.containers.get, container_name
        )
        await asyncio.to_thread(container.reload)
        if container.status == "exited":
            await asyncio.to_thread(container.start)
    except docker.errors.NotFound:
        container = await asyncio.to_thread(
            self._client.containers.create,
            image=self._image,
            name=container_name,
            volumes={...},
            stdin_open=True,
            tty=True,
            ...
        )
        await asyncio.to_thread(container.start)
    session.container_id = container.id
```

### Pattern 3: asyncio.to_thread() for All Docker SDK Calls
**What:** docker-py is synchronous. Wrap every SDK call in `asyncio.to_thread()` to avoid blocking the event loop.
**When to use:** Every docker-py call from DockerTransport methods.
**Example:**
```python
# Same pattern LocalTransport uses for libtmux
result = await asyncio.to_thread(
    container.exec_run, ["tmux", "send-keys", "-t", pane_target, command, "Enter"]
)
```

### Pattern 4: Two-Mode Exec (Interactive vs Piped)
**What:** Interactive mode sends commands to tmux inside container. Piped mode runs subprocess inside container and captures output.
**When to use:** Matches LocalTransport's dual-mode approach.
**Example:**
```python
async def exec(self, agent_id: str, command: str | list[str], **kwargs) -> str:
    session = self._sessions[agent_id]
    container = await asyncio.to_thread(self._client.containers.get, session.container_id)

    if session.interactive:
        # Fire tmux send-keys inside container
        cmd_str = command if isinstance(command, str) else " ".join(command)
        await asyncio.to_thread(
            container.exec_run,
            ["tmux", "send-keys", "-t", "main", cmd_str, "Enter"],
            detach=True,
        )
        return ""
    else:
        # Piped: run command, capture stdout
        cmd_list = command if isinstance(command, list) else command.split()
        exit_code, output = await asyncio.to_thread(
            container.exec_run,
            cmd_list,
            workdir=session.container_workdir,
        )
        if exit_code != 0:
            raise RuntimeError(f"Command failed (exit {exit_code})")
        return output.decode() if output else ""
```

### Pattern 5: Streaming Exec for Strategist (exec_streaming)
**What:** Use `container.exec_run(stream=True)` to yield output lines for piped mode.
**When to use:** StrategistConversation streaming tool-use progress through DockerTransport.
**Example:**
```python
async def exec_streaming(self, agent_id: str, command: list[str], **kwargs):
    session = self._sessions[agent_id]
    if session.interactive:
        return
    container = await asyncio.to_thread(self._client.containers.get, session.container_id)
    # exec_run with stream=True returns a generator
    _, output_gen = await asyncio.to_thread(
        container.exec_run, command, stream=True, workdir=session.container_workdir,
    )
    # Iterate generator in thread
    for chunk in output_gen:
        yield chunk.decode()
```

**Note:** Streaming with `asyncio.to_thread()` is tricky because the generator is synchronous. The implementation will need to iterate the sync generator in a thread and yield chunks back to async code. Consider using a queue-based bridge or `run_in_executor` with a blocking `next()` call.

### Pattern 6: Volume-Based read_file/write_file
**What:** Since work directories are bind-mounted, read_file/write_file can access files directly on the host filesystem -- no need for docker cp.
**When to use:** For files inside the bind-mounted work directory.
**Caveat:** Files outside the mount (e.g., inside `~/.claude` in the container) would need `docker cp`. But per DOCK-04, agent work dirs are mounted, so most file operations go through the host path.
**Example:**
```python
async def read_file(self, agent_id: str, path: Path) -> str:
    # If path is within the mounted work directory, read from host
    session = self._sessions[agent_id]
    host_path = self._resolve_host_path(session, path)
    return await asyncio.to_thread(host_path.read_text)

async def write_file(self, agent_id: str, path: Path, content: str) -> None:
    session = self._sessions[agent_id]
    host_path = self._resolve_host_path(session, path)
    await asyncio.to_thread(host_path.write_text, content)
```

### Anti-Patterns to Avoid
- **Shelling out to docker CLI:** Decision D-12 explicitly chose docker-py SDK. No `subprocess.run(["docker", ...])`.
- **Creating new containers on every setup():** Violates DOCK-06. Always check for existing container first.
- **Async docker library (aiodocker):** Locked to docker-py. Wrapping in asyncio.to_thread() is the established project pattern.
- **Running tmux on the host for Docker agents:** tmux runs INSIDE the container (D-10). DockerTransport execs into container to manage tmux.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Container lifecycle management | Custom start/stop/inspect logic | docker-py Container methods | Handles edge cases (restart policies, OOM, etc.) |
| Exec into running container | Raw socket/API calls | `container.exec_run()` | Handles stream multiplexing, exit codes, encoding |
| Container name lookup | Custom naming/tracking DB | `containers.get(name)` + docker labels | Docker daemon is the source of truth |
| tweakcc patching | Custom file patching | `npx tweakcc --apply` | tweakcc handles version detection, conflict resolution |

**Key insight:** docker-py abstracts the Docker Engine API. The Transport layer should be a thin bridge between AgentTransport protocol and docker-py SDK calls -- not a Docker reimplementation.

## Common Pitfalls

### Pitfall 1: Blocking the Event Loop with docker-py
**What goes wrong:** docker-py is synchronous. Calling `container.exec_run()` directly from async code blocks the entire event loop, freezing Discord bot and monitor.
**Why it happens:** docker-py predates asyncio adoption. No native async support.
**How to avoid:** Wrap EVERY docker-py call in `asyncio.to_thread()`. This is the same pattern LocalTransport uses for libtmux.
**Warning signs:** Bot becomes unresponsive during agent operations, monitor loop stalls.

### Pitfall 2: Streaming exec_run with asyncio
**What goes wrong:** `container.exec_run(stream=True)` returns a synchronous generator. You cannot directly `async for` over it.
**Why it happens:** docker-py generators block on `next()` waiting for Docker output.
**How to avoid:** Use a thread-based bridge: run a thread that calls `next()` on the generator and puts chunks into an `asyncio.Queue`, then `async for` from the queue. Or iterate the entire generator in a thread and collect output.
**Warning signs:** TypeError about iterating sync generator in async context.

### Pitfall 3: Container Name Collisions
**What goes wrong:** Two projects with same agent IDs create containers with same names.
**Why it happens:** Naming pattern `vco-{project}-{agent_id}` requires project name to be unique.
**How to avoid:** Use the project name from AgentConfig/ProjectConfig. Validate uniqueness at config load time.
**Warning signs:** `docker.errors.Conflict` on container create.

### Pitfall 4: Socket Permission Issues in Container
**What goes wrong:** `vco signal` fails inside container because the mounted socket file has restrictive permissions (0o600 set by daemon).
**Why it happens:** Container runs as different UID than host daemon.
**How to avoid:** Either (a) run container as same UID as host user (`user` param in containers.create), or (b) relax socket permissions to 0o666, or (c) match UIDs in Dockerfile with `useradd`.
**Warning signs:** "Permission denied" when agent tries to POST to signal socket inside container.

### Pitfall 5: stale container.status After Operations
**What goes wrong:** Container object's `.status` property shows old state after start/stop.
**Why it happens:** docker-py caches container attributes. Must call `container.reload()` to refresh.
**How to avoid:** Always call `container.reload()` before checking `container.status`.
**Warning signs:** Container shows "created" when it's actually "running".

### Pitfall 6: tmux Inside Container Setup
**What goes wrong:** tmux session doesn't exist inside container. exec_run to send-keys fails.
**Why it happens:** Container starts but tmux server isn't running yet.
**How to avoid:** In `setup()`, after starting the container, exec into it to start tmux: `tmux new-session -d -s main`. Then all subsequent send-keys target session "main".
**Warning signs:** "no server running on /tmp/tmux-*/default" error from exec_run.

### Pitfall 7: Environment Variables Not Passed to exec_run
**What goes wrong:** Claude Code inside container can't find ANTHROPIC_API_KEY, DISCORD_BOT_TOKEN, etc.
**Why it happens:** `container.exec_run()` doesn't inherit container environment by default.
**How to avoid:** Pass `environment` parameter to `exec_run()`, or set env vars at container creation time via `environment` parameter in `containers.create()`. Prefer creation-time for secrets (set once, available to all execs).
**Warning signs:** Claude Code exits immediately with auth errors.

### Pitfall 8: Volume Mount Path Mapping
**What goes wrong:** Code tries to read `/home/developer/vco-projects/proj/clones/agent-1/file.py` inside container, but the path inside container is `/workspace/file.py`.
**Why it happens:** Host paths don't exist inside container. Need path translation.
**How to avoid:** DockerTransport must translate between host paths and container paths for read_file/write_file and for any path references in commands.
**Warning signs:** FileNotFoundError inside container for paths that exist on host.

## Code Examples

### Docker Container Creation with Volumes and Sockets
```python
# Source: docker-py docs + CONTEXT.md decisions
container = client.containers.create(
    image="vco-agent:latest",
    name=f"vco-{project}-{agent_id}",
    volumes={
        str(clone_path): {"bind": "/workspace", "mode": "rw"},
        "/tmp/vco-daemon.sock": {"bind": "/tmp/vco-daemon.sock", "mode": "rw"},
        "/tmp/vco-signal.sock": {"bind": "/tmp/vco-signal.sock", "mode": "rw"},
    },
    environment={
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "DISCORD_BOT_TOKEN": os.environ.get("DISCORD_BOT_TOKEN", ""),
        "DISCORD_GUILD_ID": os.environ.get("DISCORD_GUILD_ID", ""),
        "PROJECT_NAME": project,
        "AGENT_ID": agent_id,
        "VCO_AGENT_ID": agent_id,
    },
    stdin_open=True,
    tty=True,
    network_mode="none",  # Only needs socket access, no network
    working_dir="/workspace",
)
```

### Dockerfile Structure
```dockerfile
# Source: CONTEXT.md decisions D-01, D-02
FROM node:22-slim

# System deps: Python 3.12, git, tmux, curl (for uv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip \
    git tmux curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# Apply tweakcc patches (baked into image per D-02)
RUN npx tweakcc --apply

# Default Claude settings
COPY settings.json /root/.claude/settings.json

# Working directory is mounted at runtime
WORKDIR /workspace

# Keep container alive (tmux or shell entrypoint)
CMD ["sleep", "infinity"]
```

### is_alive Two-Layer Check (D-11)
```python
def is_alive(self, agent_id: str) -> bool:
    session = self._sessions.get(agent_id)
    if session is None:
        return False
    try:
        container = self._client.containers.get(session.container_id)
        container.reload()
        # Layer 1: Container running?
        if container.status != "running":
            return False
        # Layer 2: Claude Code process alive inside container?
        exit_code, _ = container.exec_run(
            ["tmux", "has-session", "-t", "main"],
        )
        return exit_code == 0
    except docker.errors.NotFound:
        return False
```

### Sync-to-Async Streaming Bridge
```python
async def _stream_from_sync_generator(self, gen):
    """Bridge sync docker-py generator to async iterator."""
    loop = asyncio.get_event_loop()
    while True:
        chunk = await loop.run_in_executor(None, next, gen, None)
        if chunk is None:
            break
        yield chunk.decode() if isinstance(chunk, bytes) else chunk
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| docker-py 6.x | docker-py 7.1.0 | 2024 | API stable, minor improvements. No breaking changes from 6.x. |
| GitPython for git in containers | subprocess git calls | Project convention | subprocess preferred per CLAUDE.md |
| tweakcc manual patching | `npx tweakcc --apply` | tweakcc 3.x+ | Non-interactive apply flag for CI/Docker builds |

## Open Questions

1. **tweakcc config file location**
   - What we know: tweakcc reads from `~/.tweakcc/config.json`. No config exists on current host.
   - What's unclear: Does the project need a custom tweakcc config, or is `--apply` with defaults sufficient? What specific patches does the project use?
   - Recommendation: Start with default `npx tweakcc --apply` (no config). Add specific config later if needed. The Dockerfile can COPY a config.json to `/root/.tweakcc/config.json` if customizations are needed.

2. **Container network mode**
   - What we know: Containers only need Unix socket access (bind-mounted), no TCP networking.
   - What's unclear: Whether `network_mode="none"` causes issues with npm/pip inside container during builds (build-time networking is separate from runtime).
   - Recommendation: Use `network_mode="none"` for runtime containers. Build-time networking is handled by default Docker build behavior.

3. **UID mapping for socket access**
   - What we know: Daemon creates sockets with 0o600 permissions. Container default user is root.
   - What's unclear: Whether running container as root causes other issues. Whether host daemon runs as root or user.
   - Recommendation: Run container as root initially (simplest). The mounted sockets owned by host user should be accessible to root in the container. If not, adjust socket permissions.

4. **is_alive() synchronous requirement**
   - What we know: Protocol defines `is_alive()` as sync (`def`, not `async def`). docker-py calls are blocking.
   - What's unclear: Whether the blocking docker-py calls in is_alive() are fast enough to not matter, or need thread wrapping.
   - Recommendation: docker inspect and exec are fast (<100ms). Acceptable as synchronous calls since LocalTransport.is_alive() also calls synchronous libtmux methods. Keep sync to match protocol.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Container runtime | Yes | 28.2.2 | -- (blocking) |
| Node.js | Claude Code in image | Yes | 22 LTS | -- |
| Python 3.12 | Agent runtime in image | Yes | 3.12 | -- |
| npm/npx | tweakcc, claude-code install | Yes | (bundled with node) | -- |
| docker-py (pip) | DockerTransport | No | -- | Install: `uv add docker>=7.1,<8` |
| tweakcc (npm) | Dockerfile build | Available via npx | 4.0.11 | -- |

**Missing dependencies with no fallback:**
- None -- Docker Engine is available, docker-py just needs installation.

**Missing dependencies with fallback:**
- docker-py SDK not installed yet -- add to project dependencies.

## Sources

### Primary (HIGH confidence)
- [Docker SDK for Python 7.1.0 - Containers](https://docker-py.readthedocs.io/en/stable/containers.html) - create, start, stop, exec_run, status, reload APIs
- [Docker SDK for Python 7.1.0 - Multiplexed Streams](https://docker-py.readthedocs.io/en/stable/user_guides/multiplex.html) - streaming exec output handling
- [tweakcc GitHub](https://github.com/Piebald-AI/tweakcc) - --apply flag, config.json location, patch mechanism
- [tweakcc npm](https://www.npmjs.com/package/tweakcc) - version 4.0.11 confirmed

### Secondary (MEDIUM confidence)
- [Docker SDK for Python - Low-level API](https://docker-py.readthedocs.io/en/stable/api.html) - exec_create, exec_start for advanced streaming
- docker-py PyPI: version 7.1.0 confirmed as latest

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - docker-py 7.1.0 is official Docker SDK, version verified on PyPI, API verified from docs
- Architecture: HIGH - patterns directly follow LocalTransport established in Phase 25, Docker APIs verified
- Pitfalls: HIGH - common Docker+asyncio issues well-documented, socket permission issues from direct project knowledge

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (docker-py is stable, slow-moving)
