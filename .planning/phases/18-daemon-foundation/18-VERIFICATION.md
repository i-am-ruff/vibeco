---
phase: 18-daemon-foundation
verified: 2026-03-29T03:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 18: Daemon Foundation Verification Report

**Phase Goal:** User can start and stop a runtime daemon that listens on a Unix socket, with safe single-instance enforcement and graceful shutdown
**Verified:** 2026-03-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | NDJSON request model validates method, params, and id fields | VERIFIED | `Request(BaseModel)` in protocol.py; ValidationError raised on missing fields (tests pass) |
| 2  | NDJSON response model includes result with request id | VERIFIED | `Response(BaseModel)` with `id: str, result: dict`; `to_line()` produces valid NDJSON |
| 3  | Error responses carry code, message, and request id | VERIFIED | `ErrorResponse(BaseModel)` with `ErrorData(code, message)` and `id: str | None` |
| 4  | Hello handshake includes protocol version field | VERIFIED | `HelloParams(version: int)` / `HelloResult(version, daemon_version)` with `PROTOCOL_VERSION = 1` |
| 5  | Socket and PID paths are defined as constants | VERIFIED | `VCO_SOCKET_PATH` and `VCO_PID_PATH` in shared/paths.py with env var overrides |
| 6  | Daemon creates PID file on start and removes on clean exit | VERIFIED | `_write_pid_file()` on start, `_cleanup_pid_file()` in finally block; test_pid_lifecycle passes |
| 7  | Daemon refuses to start if another instance is running (PID probe) | VERIFIED | `_check_already_running()` calls `os.kill(old_pid, 0)` and raises `SystemExit`; test_already_running_refuses passes |
| 8  | Daemon cleans up stale PID and socket files from crashed instance | VERIFIED | `ProcessLookupError` branch unlinks both pid and socket files; test_stale_pid_cleanup passes |
| 9  | Daemon handles SIGTERM/SIGINT by setting shutdown event then cleaning up | VERIFIED | `loop.add_signal_handler(signal.SIGTERM, self._signal_shutdown)`; handler sets asyncio.Event only; test_signal_shutdown passes |
| 10 | Unix socket server accepts connections and handles NDJSON requests | VERIFIED | `asyncio.start_unix_server` with per-connection `_handle_client`; test_socket_accepts passes |
| 11 | hello handshake validates protocol version; ping returns pong; subscribe registers client | VERIFIED | `_handle_hello`, `_handle_ping`, `_handle_subscribe` builtins; 9 socket tests all pass |
| 12 | vco up creates a Daemon and calls daemon.run() instead of bot.run() | VERIFIED | up_cmd.py line 129-133: `Daemon(bot=..., bot_token=...)` then `daemon.run()`; no `bot_instance.run(` present |
| 13 | vco down reads PID file and sends SIGTERM to the daemon process | VERIFIED | down_cmd.py: `os.kill(pid, signal.SIGTERM)` after reading `VCO_PID_PATH`; test_down_sends_sigterm passes |
| 14 | A synchronous socket client exists for CLI commands to talk to the daemon | VERIFIED | `DaemonClient` in daemon/client.py with `connect()`, `call()`, `close()`, and context manager |

**Score:** 14/14 truths verified

---

## Required Artifacts

| Artifact | Provided | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/daemon/protocol.py` | NDJSON Pydantic models | VERIFIED | 93 lines; exports Request, Response, ErrorResponse, ErrorData, Event, HelloParams, HelloResult, ErrorCode, PROTOCOL_VERSION; all use BaseModel with to_line()/from_line() |
| `src/vcompany/shared/paths.py` | VCO_SOCKET_PATH, VCO_PID_PATH | VERIFIED | 17 lines; both constants present with env var overrides |
| `src/vcompany/daemon/__init__.py` | Package init | VERIFIED | Empty init file exists |
| `src/vcompany/daemon/server.py` | SocketServer class | VERIFIED | 198 lines (min 60); exports SocketServer with start, stop, broadcast_event, register_method, hello/ping/subscribe handlers |
| `src/vcompany/daemon/daemon.py` | Daemon class | VERIFIED | 129 lines (min 80); exports Daemon with run(), _run(), _signal_shutdown(), _check_already_running(), _write_pid_file(), _shutdown() |
| `src/vcompany/daemon/client.py` | DaemonClient (sync) | VERIFIED | 75 lines; exports DaemonClient with connect(), call(), close(), __enter__/__exit__ |
| `src/vcompany/cli/down_cmd.py` | vco down command | VERIFIED | 65 lines; exports `down` Click command with SIGTERM, PID poll, stale PID handling |
| `src/vcompany/cli/up_cmd.py` | Refactored vco up | VERIFIED | Daemon(bot=..., bot_token=...) + daemon.run(); old bot_instance.run() pattern absent (grep count = 0) |
| `src/vcompany/cli/main.py` | CLI group with down | VERIFIED | `from vcompany.cli.down_cmd import down` + `cli.add_command(down)` at line 14, 35 |
| `tests/test_daemon_protocol.py` | Protocol unit tests | VERIFIED | 22 tests, all pass |
| `tests/test_daemon.py` | Daemon lifecycle tests | VERIFIED | 6 tests: PID lifecycle, stale cleanup, SIGTERM, bot co-start, shutdown order; all pass |
| `tests/test_daemon_socket.py` | Socket server tests | VERIFIED | 9 tests: connection, handshake, wrong version, hello-first enforcement, roundtrip, method-not-found, parse-error, subscription, permissions; all pass |
| `tests/test_down_cmd.py` | vco down tests | VERIFIED | 4 tests: no PID file, stale PID, real SIGTERM, invalid PID; all pass |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| daemon/server.py | daemon/protocol.py | `from vcompany.daemon.protocol import` | WIRED | Line 16-26: imports all protocol types |
| daemon/daemon.py | daemon/server.py | `from vcompany.daemon.server import SocketServer` | WIRED | Line 15: import confirmed; used at line 57 (`self._server = SocketServer(...)`) |
| daemon/daemon.py | shared/paths.py | `from vcompany.shared.paths import VCO_PID_PATH, VCO_SOCKET_PATH` | WIRED | Line 16: both constants imported and used as defaults in `__init__` |
| daemon/daemon.py | bot.start() | `asyncio.create_task(self._bot.start(self._bot_token))` | WIRED | Line 63: bot.start() called in task; test_bot_costart verifies token passed correctly |
| cli/up_cmd.py | daemon/daemon.py | Creates `Daemon(...)` and calls `daemon.run()` | WIRED | Lines 127-133: lazy import + Daemon construction + blocking run() call |
| cli/down_cmd.py | shared/paths.py | `from vcompany.shared.paths import VCO_PID_PATH` | WIRED | Line 15: used at line 22, 27, 31 |
| cli/main.py | cli/down_cmd.py | `cli.add_command(down)` | WIRED | Lines 14, 35: import and registration confirmed; `vco down` appears in CLI command list |
| daemon/client.py | daemon/protocol.py | `from vcompany.daemon.protocol import PROTOCOL_VERSION, Request` | WIRED | Line 13: used in connect() hello handshake |

---

## Data-Flow Trace (Level 4)

Not applicable. Phase 18 artifacts are runtime infrastructure (daemon lifecycle, socket server, CLI commands) — they do not render dynamic data from a data store. There are no UI components, dashboards, or data-fetching pipelines to trace.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Protocol models import and work | `python3 -c "import sys; sys.path.insert(0,'src'); from vcompany.daemon.protocol import Request, PROTOCOL_VERSION; print(PROTOCOL_VERSION)"` | `1` | PASS |
| Path constants correct | `python3 -c "... from vcompany.shared.paths import VCO_SOCKET_PATH, VCO_PID_PATH; print(VCO_SOCKET_PATH, VCO_PID_PATH)"` | `/tmp/vco-daemon.sock /tmp/vco-daemon.pid` | PASS |
| All module imports succeed | All six phase 18 modules imported cleanly | No import errors | PASS |
| CLI `down` command registered | `from vcompany.cli.main import cli; list(cli.commands.keys())` | `['bot', 'clone', ..., 'up', 'down']` | PASS |
| up_cmd uses daemon.run() not bot.run() | `grep -c "bot_instance.run" up_cmd.py` | `0` | PASS |
| Full test suite | `python3 -m pytest tests/test_daemon*.py tests/test_down_cmd.py -v` | `41 passed in 0.51s` | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SOCK-02 | 18-01 | NDJSON protocol for request-response (one JSON object per line) | SATISFIED | `Request.to_line()` / `Response.to_line()` produce NDJSON; `from_line()` parses; 22 tests pass |
| SOCK-03 | 18-01 | Request framing includes method, params, and request ID | SATISFIED | `Request(id, method, params)` fields with Pydantic validation |
| SOCK-04 | 18-01 | Error responses include error code, message, and request ID | SATISFIED | `ErrorResponse(id, error=ErrorData(code, message))`; `ErrorCode` IntEnum with JSON-RPC 2.0 codes |
| SOCK-06 | 18-01 | Protocol version field in handshake for forward compatibility | SATISFIED | `PROTOCOL_VERSION = 1`; `HelloParams(version)` validated in `_handle_hello`; wrong version returns error |
| DAEMON-01 | 18-02 | `vco up` starts runtime daemon as foreground process | PARTIALLY SATISFIED | Daemon starts, creates PID file, runs in foreground. CompanyRoot/supervision tree integration deferred to Phase 20 per ROADMAP explicit scope boundary. Phase 18 success criteria do not include CompanyRoot. |
| DAEMON-02 | 18-02 | Daemon creates PID file on start and removes on clean exit | SATISFIED | `_write_pid_file()` on start; `_cleanup_pid_file()` in finally block; test_pid_lifecycle passes |
| DAEMON-03 | 18-02 | Daemon handles SIGTERM/SIGINT for graceful shutdown | PARTIALLY SATISFIED | SIGTERM/SIGINT handling and clean shutdown implemented. "Stops containers" deferred to Phase 20 when CompanyRoot is integrated. Shutdown order (server.stop() then bot.close()) verified by test_shutdown_order. |
| DAEMON-04 | 18-02 | Daemon cleans up stale socket file on start (PID probe before unlink) | SATISFIED | `os.kill(old_pid, 0)` probe; `ProcessLookupError` triggers unlink of both pid and socket; test_stale_pid_cleanup passes |
| DAEMON-06 | 18-02 | `vco up` starts Discord bot alongside daemon in same event loop | SATISFIED | `asyncio.create_task(self._bot.start(self._bot_token))` in daemon._run(); bot shares event loop; test_bot_costart verifies token passed |
| SOCK-01 | 18-02 | Daemon listens on Unix socket with asyncio.start_unix_server | SATISFIED | `asyncio.start_unix_server(self._handle_client, path=...)` in SocketServer.start(); socket permissions 0o600; test_socket_accepts passes |
| SOCK-05 | 18-02 | Event subscription -- clients can subscribe to daemon events | SATISFIED | `subscribe` method registers client for event_type set; `broadcast_event()` delivers to subscribers; test_event_subscription passes |
| DAEMON-05 | 18-03 | `vco down` sends graceful shutdown signal to running daemon | SATISFIED | `os.kill(pid, signal.SIGTERM)` with PID from VCO_PID_PATH; polls for exit; stale PID handling; test_down_sends_sigterm passes |

**Requirement notes:**

DAEMON-01 and DAEMON-03 are marked partially satisfied because the requirement text mentions "CompanyRoot and supervision tree" / "stops containers" — functionality that the ROADMAP explicitly scopes to Phase 20. The Phase 18 success criteria (which are the authoritative contract for this phase) make no mention of CompanyRoot. The daemon infrastructure is fully implemented; CompanyRoot integration is a Phase 20 task.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| cli/up_cmd.py | 83 | Comment: `# First window: monitor (placeholder until project loads)` | Info | Pre-existing comment describing the tmux monitor pane, not a code stub. The tmux window is created with a real echo command. No impact on phase 18 goal. |
| daemon/server.py | 134, 136 | `pass` in exception handlers | Info | `asyncio.TimeoutError` and `ConnectionResetError`/`BrokenPipeError` are silently swallowed during client disconnect — intentional connection teardown behavior, not stubs. |

No blocker or warning-level anti-patterns found.

---

## Behavioral Spot-Checks (Step 7b)

Step 7b: SKIPPED for live server start (requires running daemon against Discord). All 41 unit tests serve as the behavioral verification layer. Tests cover: protocol model validation, daemon lifecycle (PID, signals, stale cleanup, shutdown order), socket server (accept, handshake, roundtrip, subscriptions, permissions), and CLI commands (vco down with all edge cases).

---

## Human Verification Required

### 1. Bot Starts Alongside Daemon on Real Discord

**Test:** Run `vco up` with a real `.env` containing `DISCORD_BOT_TOKEN`. Verify the bot comes online in Discord and responds to commands while the daemon's Unix socket is accepting connections.
**Expected:** Bot appears online; `socat - UNIX-CONNECT:/tmp/vco-daemon.sock` connects and responds to a hello request; PID file exists at `/tmp/vco-daemon.pid`.
**Why human:** Requires real Discord credentials and live network connection; cannot test in automated context.

### 2. End-to-End vco up / vco down Lifecycle

**Test:** Run `vco up` in one terminal, then `vco down` in another. Verify daemon shuts down cleanly.
**Expected:** `vco down` reports "Sent SIGTERM to daemon" then "Daemon stopped." PID file removed. Bot goes offline.
**Why human:** Full lifecycle requires real Discord bot token; can't run bot without credentials.

### 3. Stale Socket Recovery on Real Crash

**Test:** Start `vco up`, then kill the daemon with `kill -9 <pid>`. Run `vco up` again.
**Expected:** Second `vco up` detects stale PID file, removes it along with the stale socket file, and starts fresh without error.
**Why human:** The automated test covers this case programmatically, but a live test with real filesystem state confirms no edge cases are missed.

---

## Gaps Summary

No gaps. All 14 must-haves are verified. All 41 tests pass. All key links are wired. All required artifacts exist and are substantive.

DAEMON-01 and DAEMON-03 are partially satisfied relative to their requirement text (CompanyRoot/containers deferred), but this partial satisfaction is the intended scope for Phase 18 — confirmed by the ROADMAP success criteria and the research document's explicit "CompanyRoot not coupled to bot yet" note. The phase goal ("start and stop a runtime daemon with Unix socket, single-instance enforcement, graceful shutdown") is fully achieved.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
