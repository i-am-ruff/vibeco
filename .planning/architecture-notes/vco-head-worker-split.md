# vco-head / vco-worker Architecture (v4 Vision)

## The Split

**vco-head** (daemon side):
- Orchestration, Discord bot, health monitoring
- Agent config (agent-types.yaml), routing, channel management
- Talks to transports — never to containers directly
- Doesn't know container internals (no GsdAgent/CompanyAgent Python objects)
- Single instance per deployment

**vco-worker** (container side):
- Lightweight runtime baked into every execution environment
- CLI commands: `vco report`, `vco ask`, `vco send-file`, `vco signal`
- Container process management (start the right agent type, manage lifecycle)
- Talks to the transport's local endpoint — doesn't know what's on the other side
- One instance per agent

## Communication

```
vco-worker ←→ transport channel ←→ vco-head
(inside container)                  (daemon)
```

The transport channel is the ONLY connection between head and worker.
No mounted sockets. No shared filesystem. No direct subprocess calls.

### Transport channel by type

| Transport | Channel | Direction |
|-----------|---------|-----------|
| Docker | docker exec stdin/stdout, or mapped TCP port | bidirectional |
| Native (tmux) | local Unix socket or in-process | bidirectional |
| Network (v4) | TCP/WebSocket | bidirectional |

### Message types (head → worker)

| Message | Purpose |
|---------|---------|
| `start` | Bootstrap agent container of given type with config blob |
| `give-task` | Send task text to the running agent |
| `message` | Deliver Discord message (from MentionRouter) |
| `stop` | Graceful shutdown |
| `health-check` | Request health report |

### Message types (worker → head)

| Message | Purpose |
|---------|---------|
| `signal ready` | Agent container is alive and ready |
| `signal idle` | Agent finished processing, waiting for input |
| `report` | Post status message to agent's Discord channel |
| `ask` | Post question to Discord, block until reply |
| `send-file` | Send file to Discord channel |
| `health-report` | Respond to health check with status |

## Bootstrapping

1. User runs `vco hire gsd sprint-dev-1`
2. **vco-head** reads agent-types.yaml, resolves transport + config
3. **vco-head** tells transport: "start agent type=gsd, id=sprint-dev-1, config={...}"
4. **Transport** creates execution environment (Docker container, tmux session, remote process)
5. Inside the environment, **vco-worker** starts with the config blob
6. **vco-worker** reads config, starts the right agent process (claude in tmux, claude -p piped, or Python event handler)
7. **vco-worker** signals readiness: `signal ready` through transport channel
8. **vco-head** receives ready signal, announces in Discord

## Agent container types (run inside vco-worker)

| Type | What runs inside | How it communicates |
|------|-----------------|-------------------|
| session | Interactive Claude Code in tmux | vco hooks (SessionStart, Stop) + vco report/ask |
| conversation | Piped `claude -p --resume` | vco-worker manages the session, sends/receives per message |
| transient | Python event handler | vco-worker runs the handler loop, forwards messages |

The agent type determines what process vco-worker starts. The transport doesn't care — it just forwards messages.

## What changes from current architecture

| Current (v3.1) | Future (v4) |
|----------------|-------------|
| Container is Python object in daemon | Container is process inside transport |
| Daemon instantiates GsdAgent, CompanyAgent | Daemon only has transport handle + agent_id |
| StrategistConversation calls transport.exec() from daemon side | vco-worker manages conversation inside container |
| Docker mounts daemon Unix socket directly | Transport channel replaces socket mount |
| Handler extracted but still runs daemon-side | Handler runs inside vco-worker |
| State (review gates, conversation, checkpoints) on daemon Python objects | State lives inside container filesystem, survives transport restarts |
| Duplicating transport = shared daemon state | Duplicating transport = fully independent agent |

## Migration path

1. **v3.1 (current)**: Containers are daemon-side Python objects. Transport runs subprocesses. Docker mounts socket. Works single-machine.
2. **v3.2**: Extract vco-worker as a package. Head-worker message protocol defined. Docker containers run vco-worker instead of mounting socket. Native transport unchanged.
3. **v4.0**: Network transport. vco-worker on remote machines. Head communicates over TCP/WebSocket. Full distribution.

## Key constraint

vco-worker must be installable on any execution environment — Docker image, remote server, local machine. It should be a small Python package with minimal dependencies (no discord.py, no bot code, no orchestration). Just the CLI commands + transport channel client + agent process management.
