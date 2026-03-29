# Phase 21: CLI Commands - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Users can manage agents entirely from the terminal using vco CLI commands that talk to the daemon via socket API. Covers CLI-01 (vco hire), CLI-02 (vco give-task), CLI-03 (vco dismiss), CLI-04 (vco status), CLI-05 (vco health), CLI-06 (vco new-project composite command).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — CLI plumbing phase. Key patterns:
- All CLI commands use DaemonClient (Phase 18) to talk to daemon over socket
- Daemon needs new socket method handlers that call RuntimeAPI methods
- CLI commands are Click commands registered in cli/main.py
- Output formatting via Rich (existing dependency)
- Error handling: connect failure → "daemon not running, run vco up first"

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/daemon/client.py` — DaemonClient with sync socket communication
- `src/vcompany/daemon/server.py` — SocketServer with register_method()
- `src/vcompany/daemon/runtime_api.py` — RuntimeAPI with hire(), give_task(), dismiss(), status(), health_tree(), new_project()
- `src/vcompany/daemon/protocol.py` — Request/Response NDJSON models
- `src/vcompany/cli/main.py` — Click CLI group with existing commands
- `src/vcompany/cli/up_cmd.py`, `src/vcompany/cli/down_cmd.py` — existing CLI patterns

### Established Patterns
- CLI commands are Click functions in separate files, registered via cli.add_command()
- DaemonClient connects to Unix socket, sends NDJSON Request, receives Response
- SocketServer dispatches methods to registered async handlers
- Rich console for formatted output (tables, status indicators)

### Integration Points
- Each CLI command needs: socket method registration in Daemon + Click command + DaemonClient call
- RuntimeAPI already has the business logic methods — CLI just wraps them
- Socket server's register_method() in daemon._register_socket_endpoints()

</code_context>

<specifics>
## Specific Ideas

No specific requirements — CLI plumbing phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — CLI plumbing phase with clear scope.

</deferred>
