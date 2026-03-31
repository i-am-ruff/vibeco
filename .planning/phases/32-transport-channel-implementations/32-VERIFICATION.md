---
phase: 32-transport-channel-implementations
verified: 2026-03-31T18:00:00Z
status: human_needed
score: 11/11 must-haves verified
re_verification: true
  previous_status: gaps_found
  previous_score: 9/11
  gaps_closed:
    - "Transport __init__.py exports new classes alongside old ones -- try/except ImportError guard added around DockerTransport import; module now importable regardless of docker SDK presence (and docker SDK IS installed, so DockerTransport loads fully)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run hire(transport_name='docker') end-to-end against a live Docker daemon"
    expected: "DockerChannelTransport.spawn() launches 'docker run -i --rm --network none vco-agent:latest python -m vco_worker', process stdin/stdout are piped, StartMessage is sent successfully"
    why_human: "Requires Docker daemon and built vco-agent:latest image. Cannot verify without running services."
  - test: "Run hire(transport_name='native') end-to-end with vco-worker installed"
    expected: "NativeTransport.spawn() launches 'python -m vco_worker', process responds to StartMessage, channel_reader task picks up WorkerMessages"
    why_human: "Requires vco_worker module installed in the same virtualenv. Cannot verify full round-trip without package install in test env."
---

# Phase 32: Transport Channel Implementations Verification Report

**Phase Goal:** Both Docker and native transports use the channel protocol end-to-end -- no socket mounts, no shared filesystem between head and worker
**Verified:** 2026-03-31T18:00:00Z
**Status:** human_needed — all automated checks pass, 2 live-service tests remain
**Re-verification:** Yes — after gap closure (try/except ImportError fix on transport/__init__.py)

## Re-Verification Summary

**Previous status:** gaps_found (9/11 truths verified, 1 gap)
**Gap closed:** `src/vcompany/transport/__init__.py` line 4 now wraps `from vcompany.transport.docker import DockerTransport` in a `try/except ImportError` block. The module is importable cleanly. The docker SDK IS installed in this environment (DockerTransport resolves to the real class), so the guard also handles environments where it is absent.

**Regression check:** All 9 previously passing items re-confirmed. No regressions detected.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | NativeTransport.spawn() returns asyncio.subprocess.Process with stdin/stdout piped running vco-worker | VERIFIED | native.py line 41: `cmd = [sys.executable, "-m", "vco_worker"]`; line 51-58: `asyncio.create_subprocess_exec(*cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, ...)` |
| 2 | DockerChannelTransport.spawn() wraps 'docker run -i' with stdin/stdout piped | VERIFIED | docker_channel.py lines 53-57: `["docker", "run", "-i", "--rm", "--name", container_name, "--network", "none"]`; line 79-84: `asyncio.create_subprocess_exec(*cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)` |
| 3 | Both transports implement the same ChannelTransport protocol | VERIFIED | `isinstance(NativeTransport(), ChannelTransport)` = True; `isinstance(DockerChannelTransport(), ChannelTransport)` = True (confirmed via .venv/bin/python3 spot-check) |
| 4 | DockerChannelTransport does NOT mount Unix sockets into containers | VERIFIED | No matches for "socket", ".sock", "VCO_SOCKET_PATH" in docker_channel.py. Doc comment on line 8 explicitly states "No socket mounts, no daemon socket, no signal socket". |
| 5 | DockerChannelTransport uses -i without -t (no TTY corruption) | VERIFIED | cmd list contains `"-i"` (line 54); no `"-t"` anywhere in docker_channel.py. |
| 6 | CompanyRoot.hire() accepts transport_name parameter and delegates to transport | VERIFIED | hire() signature at line 188-195: `transport_name: str = "native"`. Lines 297-303: `transport = self._get_transport(transport_name); process = await transport.spawn(...)`. Confirmed via `inspect.signature` spot-check. |
| 7 | hire(transport_name='native') spawns via NativeTransport.spawn() | VERIFIED | _get_transport() lines 174-175: `if transport_name == "native": self._transports[transport_name] = NativeTransport()`. |
| 8 | hire(transport_name='docker') spawns via DockerChannelTransport.spawn() | VERIFIED | _get_transport() lines 176-177: `elif transport_name == "docker": self._transports[transport_name] = DockerChannelTransport()`. |
| 9 | Docker image includes vco-worker package | VERIFIED | Dockerfile lines 30-31: `COPY packages/vco-worker/ /opt/vco-worker/` + `RUN cd /opt/vco-worker && uv pip install --system -e .`. CMD at line 43: `["python", "-m", "vco_worker"]`. sleep infinity removed. |
| 10 | Both transport paths produce identical AgentHandle behavior | VERIFIED | Both paths assign `handle._process = process`, call `handle.send(StartMessage(...))`, then `asyncio.create_task(self._channel_reader(handle))`. _channel_reader reads from `handle._process.stdout` uniformly. |
| 11 | Transport __init__.py exports new classes alongside old ones | VERIFIED | __init__.py now guards DockerTransport import with try/except ImportError (line 4-7). `from vcompany.transport import ChannelTransport, NativeTransport, DockerChannelTransport` imports cleanly. Confirmed via .venv/bin/python3 spot-check. |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/transport/channel_transport.py` | ChannelTransport Protocol definition | VERIFIED | 63 lines. `@runtime_checkable class ChannelTransport(Protocol)` with `spawn`, `terminate`, `transport_type`. Substantive and wired. |
| `src/vcompany/transport/native.py` | NativeTransport implementation | VERIFIED | 91 lines. `_processes` dict, `spawn()` with env merge and `VCO_AGENT_ID`, `terminate()` with SIGTERM+SIGKILL fallback, `transport_type = "native"`. Imported by company_root.py. |
| `src/vcompany/transport/docker_channel.py` | DockerChannelTransport implementation | VERIFIED | 119 lines. `_containers` + `_processes` dicts, `spawn()` builds docker run command (no -t, no socket mount), `terminate()` uses `docker kill`, `transport_type = "docker"`. Imported by company_root.py. |
| `src/vcompany/supervisor/company_root.py` | Transport-aware hire() method | VERIFIED | hire() has `transport_name: str = "native"` param. `_get_transport()` at lines 156-180. `transport.spawn()` called at lines 297-303. No hardcoded `sys.executable + vco_worker`. |
| `src/vcompany/transport/__init__.py` | Updated exports including ChannelTransport, NativeTransport, DockerChannelTransport | VERIFIED | try/except ImportError guard added (lines 4-7). All new classes exported. Module importable cleanly. |
| `docker/Dockerfile` | Docker image with vco-worker installed | VERIFIED | COPY + uv pip install vco-worker at lines 30-31. CMD set to `["python", "-m", "vco_worker"]` at line 43. `sleep infinity` removed. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `native.py` | `vco_worker` | `create_subprocess_exec(sys.executable, "-m", "vco_worker")` | WIRED | Line 41: `cmd = [sys.executable, "-m", "vco_worker"]`. Line 51: `asyncio.create_subprocess_exec(*cmd, ...)`. |
| `docker_channel.py` | `docker run -i` | `create_subprocess_exec("docker", "run", "-i", ...)` | WIRED | Lines 53-57: cmd starts `["docker", "run", "-i", "--rm", "--name", ...]`. Line 79: `asyncio.create_subprocess_exec(*cmd, ...)`. |
| `company_root.py` | `native.py` | import + instantiation in `_get_transport()` | WIRED | Line 37: `from vcompany.transport.native import NativeTransport`. Line 175: `NativeTransport()` instantiated in `_get_transport()`. |
| `company_root.py` | `docker_channel.py` | import + instantiation in `_get_transport()` | WIRED | Line 36: `from vcompany.transport.docker_channel import DockerChannelTransport`. Line 177: `DockerChannelTransport()` instantiated. |
| `docker/Dockerfile` | `packages/vco-worker/` | COPY + uv pip install | WIRED | Line 30: `COPY packages/vco-worker/ /opt/vco-worker/`. Line 31: `RUN cd /opt/vco-worker && uv pip install --system -e .`. |

### Data-Flow Trace (Level 4)

Not applicable. These are transport and infrastructure files, not UI components rendering dynamic data. All data flows are subprocess stdin/stdout I/O channels verified at Level 3.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `from vcompany.transport import ChannelTransport, NativeTransport, DockerChannelTransport` | `.venv/bin/python3 -c "from vcompany.transport import ..."` | OK: all imports succeed | PASS |
| NativeTransport protocol compliance | `isinstance(NativeTransport(), ChannelTransport)` | True | PASS |
| DockerChannelTransport protocol compliance | `isinstance(DockerChannelTransport(), ChannelTransport)` | True | PASS |
| transport_type values | `t.transport_type` on each | "native", "docker" | PASS |
| hire() signature has transport_name param | `inspect.signature(CompanyRoot.hire)` | `transport_name: str = 'native'` present | PASS |
| No hardcoded subprocess path in hire() | grep `sys.executable.*vco_worker` in company_root.py | no matches | PASS |
| No -t flag in docker command | grep `"-t"` in docker_channel.py | no matches | PASS |
| No socket mounts in docker command | grep `socket\|\.sock\|VCO_SOCKET_PATH` in docker_channel.py | no matches (doc comment says "no socket mounts") | PASS |
| Docker image CMD is vco_worker | grep `CMD.*vco_worker` in Dockerfile | match at line 43 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| CHAN-02 | 32-01-PLAN.md, 32-02-PLAN.md | Docker transport uses transport channel instead of Unix socket mount -- vco-worker inside Docker talks through the channel, not a mounted socket | SATISFIED | DockerChannelTransport uses `docker run -i` with stdin/stdout PIPE. Zero socket mount patterns in docker_channel.py. Dockerfile installs vco-worker and sets CMD to `python -m vco_worker`. CompanyRoot.hire(transport_name='docker') delegates to DockerChannelTransport.spawn(). |
| CHAN-03 | 32-01-PLAN.md, 32-02-PLAN.md | Native transport uses transport channel (local socket or in-process bridge) | SATISFIED | NativeTransport uses `asyncio.create_subprocess_exec` with stdin/stdout PIPE, communicating via NDJSON channel protocol. CompanyRoot.hire(transport_name='native') delegates to NativeTransport.spawn(). No Unix socket or shared filesystem involved. |

No orphaned requirements. CHAN-02 and CHAN-03 are the only IDs declared across both plan files and both are accounted for.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/vcompany/transport/__init__.py` | 16 | `"DockerTransport"` in `__all__` but value may be `None` if docker SDK absent | Info | If docker SDK is absent, `from vcompany.transport import DockerTransport` succeeds but yields `None`. Callers must check before using. In this environment docker SDK is installed so value is the real class. No blocker. |

No blockers or warnings found.

### Human Verification Required

#### 1. Docker end-to-end channel flow

**Test:** With Docker daemon running and `vco-agent:latest` image built from the updated Dockerfile, call `hire(agent_id="test-01", transport_name="docker")` on a CompanyRoot instance.
**Expected:** Container `vco-test-01` starts via `docker run -i --rm --network none vco-agent:latest python -m vco_worker`. StartMessage is sent through stdin. A WorkerMessage response appears on stdout within 5 seconds. `_channel_reader` task processes it.
**Why human:** Requires a live Docker daemon and a built image. Cannot verify without running services.

#### 2. Native end-to-end channel flow

**Test:** With `vco_worker` installed (`uv pip install -e packages/vco-worker` in the project venv), call `hire(agent_id="test-01", transport_name="native")` on a CompanyRoot instance.
**Expected:** `python -m vco_worker` subprocess starts with `VCO_AGENT_ID=test-01`. StartMessage is sent through stdin. `_channel_reader` task receives a WorkerMessage response.
**Why human:** Requires `vco_worker` to be runnable as a module entry point in the active virtualenv. Full round-trip cannot be verified without that install.

### Gaps Summary

No gaps remain. The single gap from initial verification (broken `__init__.py` import) has been resolved by adding a `try/except ImportError` guard around the `DockerTransport` import. The module is now importable in all environments.

The phase goal is fully achieved at the implementation level: both NativeTransport and DockerChannelTransport use the channel protocol (stdin/stdout NDJSON) with no socket mounts and no shared filesystem. CompanyRoot.hire() delegates subprocess creation to the appropriate transport via `_get_transport()`. The Dockerfile runs vco-worker as the container entrypoint.

---

_Verified: 2026-03-31T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
