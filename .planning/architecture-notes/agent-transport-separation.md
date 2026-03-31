# Agent Container vs Transport — Architecture

## Two orthogonal dimensions

### Agent Containers (HOW it thinks)

The agent's execution model — how it processes messages and produces responses.

| Container Type | Description | Example |
|---|---|---|
| **tmux session handler** | Interactive Claude Code session in tmux. Messages sent via send_keys, output read from pane. Long-running, stateful. | GSD agents, task agents |
| **resume-conversation handler** | Piped `claude -p --resume` subprocess. Request-response pattern. Session persists across calls via resume ID. | Strategist |
| **memory-based transient handler** | No Claude session. Python logic processes structured messages (prefix matching, state machine). | PM (FulltimeAgent) |

### Transports (WHERE it runs)

The execution environment — isolated from what the agent does.

| Transport | Description | Status |
|---|---|---|
| **Native (local)** | tmux on the host machine. Direct filesystem access. | v1 — working |
| **Docker** | Isolated container. Workspace mounted, daemon socket mounted. | v3.1 — wired |
| **Network** | Agent on a remote machine. Communication over network protocol. | v4 — future |

## The matrix

Any container type can run on any transport:

|  | Native | Docker | Network |
|---|---|---|---|
| tmux session | GSD agent on host | GSD agent in container | GSD agent on remote server |
| resume-conversation | Strategist on host | Strategist in container | Strategist on remote server |
| memory-based | PM on host | PM in container | PM on remote server |

The transport doesn't know what kind of agent it's running. The agent container doesn't know where it's running.

## Communication flow

```
Discord → MentionRouterCog → container.receive_discord_message()
    → container processes (via its handler type)
    → container._send_discord(channel_id, response)
    → comm_port.send_message() → CommunicationPort → Discord

Agents inside transport (Claude Code):
    → vco report/ask/send-file → daemon socket → CommunicationPort → Discord
```

## Key rule

Transport methods (`setup`, `exec`, `teardown`, `is_alive`) are agent-agnostic.
Container methods (`receive_discord_message`, `give_task`) are transport-agnostic.
Neither layer reaches into the other's concerns.
