# Phase 26: Docker Runtime - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 26-docker-runtime
**Areas discussed:** Dockerfile strategy, Container lifecycle, Volume mounts & socket, Docker exec mapping

---

## Dockerfile Strategy

### Base Image

| Option | Description | Selected |
|--------|-------------|----------|
| Node 22 LTS slim | Start from node:22-slim, add Python 3.12, uv, git, tmux. ~150MB base. | ✓ |
| Ubuntu 24.04 | Start from ubuntu:24.04, add Node 22, Python 3.12, uv, git, tmux. ~250MB base. | |
| Multi-stage build | Builder stage installs/patches, runtime stage copies result. Smaller but more complex. | |

**User's choice:** Node 22 LTS slim
**Notes:** Claude Code runs on Node so this is the natural base.

### Tweakcc Patches

| Option | Description | Selected |
|--------|-------------|----------|
| Install + patch at build time | npm install Claude Code, then run tweakcc patch script. Deterministic. | ✓ |
| Mount tweakcc as volume | Install at build, mount patches at runtime. More flexible but less deterministic. | |
| COPY tweakcc into image | COPY directory, run patch at build. Rebuild to update. | |

**User's choice:** Install + patch at build time
**Notes:** Patches baked into image for determinism.

### Image Scope

| Option | Description | Selected |
|--------|-------------|----------|
| One universal image | Single image, agent differences from config. | ✓ |
| Per-agent-type images | Separate Dockerfiles per agent type. | |

**User's choice:** One universal image
**Notes:** Simpler to build and maintain.

---

## Container Lifecycle

### Container Naming

| Option | Description | Selected |
|--------|-------------|----------|
| vco-{project}-{agent_id} | Deterministic naming, easy to find with docker ps. | ✓ |
| Random with label tracking | Docker-assigned names, find via label queries. | |

**User's choice:** vco-{project}-{agent_id}

### Cleanup Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Stop but keep | docker stop on teardown, keep for inspection. Explicit rm to remove. | ✓ |
| Auto-remove on teardown | docker stop + rm. Clean but loses session state. | |
| Stop + TTL cleanup | docker stop, background task removes after N hours. | |

**User's choice:** Stop but keep
**Notes:** Preserves ~/.claude session state per DOCK-06.

### Container Reuse on Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Start existing container | docker start stopped container. Preserves state (DOCK-06). | ✓ |
| Remove and recreate | docker rm + docker create. Clean slate, loses state. | |
| Fail if exists | Error out, require explicit cleanup. | |

**User's choice:** Start existing container
**Notes:** User asked for clarification on when setup() is called. Explained it runs on every AgentContainer.start() — hire, restart, daemon recovery. Reuse is the expected path.

---

## Volume Mounts & Socket

### Socket Mount

| Option | Description | Selected |
|--------|-------------|----------|
| Bind mount same path | -v /tmp/vco-daemon.sock:/tmp/vco-daemon.sock. Zero config changes. | ✓ |
| Mount to well-known dir | -v to /var/run/vco/. Requires env var override. | |
| TCP instead of socket | Daemon listens on TCP port. Changes signal architecture. | |

**User's choice:** Bind mount same path
**Notes:** User initially asked about HTTP transport — clarified that NetworkTransport is v4 scope. Unix sockets confirmed sufficient for v3.1.

### Work Directories

| Option | Description | Selected |
|--------|-------------|----------|
| Bind mount from host | -v /path/to/clone:/workspace. Immediate visibility both sides. | ✓ |
| Docker volume per agent | Named volumes. More isolated but different clone management. | |
| Clone inside container | Container does git clone. Slower, needs credentials. | |

**User's choice:** Bind mount from host

### ~/.claude Persistence

| Option | Description | Selected |
|--------|-------------|----------|
| Named volume for ~/.claude | Survives container recreation. | |
| Lives inside container | In writable layer. Persists across stop/start. | ✓ |
| Bind mount from host | Visible on host. Risk of path conflicts. | |

**User's choice:** Lives inside container
**Notes:** User questioned why persistence was needed at all. Agreed session history is disposable since agents start fresh tasks. But chose to keep ~/.claude inside the container (not ephemeral, not volume) so each container can have its own setup-time modifications. Persists across stop/start (DOCK-06), lost on docker rm which is acceptable.

---

## Docker Exec Mapping

### Interactive Mode

| Option | Description | Selected |
|--------|-------------|----------|
| tmux inside container | Container runs tmux server. Docker exec interacts with tmux. | ✓ |
| docker exec as terminal | Skip tmux, run Claude Code directly. Loses send-keys capability. | |
| You decide | Claude picks best approach. | |

**User's choice:** tmux inside container

### Health Check

| Option | Description | Selected |
|--------|-------------|----------|
| docker inspect state | Check container running state. Fast, reliable. | |
| docker exec ping | Confirm container can execute commands. More thorough. | |
| Combination | docker inspect + exec to check Claude Code process alive. | ✓ |

**User's choice:** Combination of docker inspect and exec-based process check
**Notes:** Two-layer check: (1) container running, (2) Claude Code process alive inside. Matches LocalTransport's approach.

### Docker API

| Option | Description | Selected |
|--------|-------------|----------|
| docker CLI via subprocess | asyncio.create_subprocess_exec('docker', ...). No new dependency. | |
| docker-py SDK | import docker. Typed API, better error handling. New dependency. | ✓ |
| You decide | Claude picks based on conventions. | |

**User's choice:** docker-py SDK
**Notes:** Exception to the subprocess-over-library convention used for git. Docker operations are more complex (lifecycle, inspect, exec with streaming) so the typed SDK adds more value.

---

## Claude's Discretion

- Docker exec command construction for tmux send-keys inside containers
- Dockerfile layer ordering and caching strategy
- How piped mode (Strategist subprocess) maps through Docker exec
- Container network mode (host, bridge, none)
- read_file/write_file implementation (docker cp vs volume path access)

## Deferred Ideas

None — discussion stayed within phase scope.
