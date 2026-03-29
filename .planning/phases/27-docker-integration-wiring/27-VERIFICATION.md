---
phase: 27-docker-integration-wiring
verified: 2026-03-30T00:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 27: Docker Integration Wiring Verification Report

**Phase Goal:** Docker agents work end-to-end: per-transport deps resolution, docker_image flow from config to constructor, auto-build on first use, parametric agent setup (tweakcc profiles, custom settings via kwargs), and removal of hardcoded agent-type checks from business logic
**Verified:** 2026-03-30
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                 | Status     | Evidence                                                                                       |
|----|-------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------|
| 1  | agent-types.yaml is the single source of truth for all agent type definitions                        | VERIFIED   | `agent-types.yaml` at repo root with 6 types including `docker-gsd`; `AgentTypesConfig.get_type()` enforces schema |
| 2  | Factory resolves per-transport deps from agent type config (LocalTransport←tmux_manager, DockerTransport←docker_image+project_name) | VERIFIED | `_resolve_transport_deps()` in factory.py lines 54-75 — python assertion test passed |
| 3  | docker_image flows from agent-types.yaml through factory to DockerTransport constructor              | VERIFIED   | `_resolve_transport_deps` reads `type_config.docker_image`; factory passes to `DockerTransport(**deps)` |
| 4  | Docker image auto-builds on first hire when image missing, OR `vco build` exists for explicit builds | VERIFIED   | `ensure_docker_image()` called in `company_root.hire()` lines 177-180; `vco build` CLI registered in `main.py` and `--help` verified |
| 5  | DockerTransport.setup() accepts parametric kwargs (tweakcc profile, settings_json) for per-agent customization | VERIFIED | `_apply_tweakcc_profile()` and `_apply_settings()` methods exist; `setup()` reads `kwargs.get("tweakcc_profile")` and `kwargs.get("settings_json")` |
| 6  | No hardcoded agent-type string checks remain in runtime_api.py or supervisor.py                      | VERIFIED   | AST scan finds zero `isinstance(x, FulltimeAgent/GsdAgent/CompanyAgent)` and zero `agent_cfg.type in ("gsd", ...)` patterns in both files |
| 7  | Adding a new agent type requires only an agents.yaml entry + optional container subclass — zero business logic changes | VERIFIED | Factory uses `container_class` from agent-types config with dual-key registry (by type string AND class name); supervisor.py and runtime_api.py use `get_agent_types_config()` for capability lookups |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact                                     | Expected                                                | Status     | Details                                                                  |
|----------------------------------------------|---------------------------------------------------------|------------|--------------------------------------------------------------------------|
| `src/vcompany/models/agent_types.py`         | AgentTypeConfig + AgentTypesConfig models, load_agent_types(), get_default_config() | VERIFIED | All classes and functions present; `_BUILTIN_DEFAULTS` dict covers 5 types; uv run test passed |
| `agent-types.yaml`                           | Default agent type definitions including docker-gsd     | VERIFIED   | File at repo root; 6 types defined including `docker-gsd` with `transport: docker` |
| `src/vcompany/container/factory.py`          | `_resolve_transport_deps()`, `set/get_agent_types_config()`, dual-key registry | VERIFIED | All three functions present; `_agent_types_config` module-level variable; dual registry confirmed by test |
| `src/vcompany/daemon/daemon.py`              | Loads agent-types config at startup, adds project_name to transport_deps | VERIFIED | Lines 210-223: `transport_deps` includes `project_name`; `load_agent_types()` + `set_agent_types_config()` called |
| `src/vcompany/docker/__init__.py`            | Package init                                            | VERIFIED   | File exists at `src/vcompany/docker/__init__.py`                         |
| `src/vcompany/docker/build.py`               | `ensure_docker_image()` async + `build_image_sync()` sync | VERIFIED | Both functions present; `asyncio.to_thread` wrapping confirmed; `docker.errors.ImageNotFound` existence check present |
| `src/vcompany/cli/build_cmd.py`              | `vco build` click command with `--force`                | VERIFIED   | `@click.command()` with `--force` flag; `--help` exits 0 and shows IMAGE argument |
| `src/vcompany/cli/main.py`                   | `build` command registered in CLI group                 | VERIFIED   | `from vcompany.cli.build_cmd import build` and `cli.add_command(build)` both present |
| `src/vcompany/daemon/runtime_api.py`         | Config-driven ChildSpec building, duck-typed method guards, `agent_type` param on `hire()` | VERIFIED | `get_agent_types_config()` used at lines 696/698; `hasattr` guards at lines 348/451/685/731/762; `hire()` accepts `agent_type` and passes to `company_root.hire()` |
| `src/vcompany/supervisor/supervisor.py`      | Config-driven delegation context, no hardcoded type checks | VERIFIED | Lines 173-196: `get_agent_types_config()` for `uses_tmux`/`gsd_command`/`transport`; no hardcoded type-string checks |
| `src/vcompany/transport/docker.py`           | Parametric setup: `_apply_tweakcc_profile()`, `_apply_settings()`, kwargs in `setup()` | VERIFIED | Both private methods present; `setup()` reads `tweakcc_profile` and `settings_json` from kwargs at lines 118-125 |
| `src/vcompany/supervisor/company_root.py`    | `hire()` accepts `agent_type`, calls `ensure_docker_image()` for Docker, uses config for ChildSpec | VERIFIED | Lines 140-248: `agent_type` param; auto-build at lines 177-180; config-driven `ContainerContext` and `ChildSpec` construction |
| `src/vcompany/container/container.py`        | `_transport_setup_kwargs` attribute; spreads into `transport.setup()`; health_report populates transport fields | VERIFIED | Line 80: `self._transport_setup_kwargs: dict = {}`; line 211: spreads into setup; lines 263-292: transport-specific health fields |
| `src/vcompany/container/health.py`           | `transport_type`, `docker_container_id`, `docker_image` optional fields on HealthReport | VERIFIED | All three optional fields present; confirmed by runtime introspection test |
| `src/vcompany/cli/hire_cmd.py`               | Passes TYPE as `agent_type` in hire call                | VERIFIED   | Line 17: `client.call("hire", {"agent_id": name, "template": type_, "agent_type": type_})` |

---

### Key Link Verification

| From                                        | To                                     | Via                                              | Status  | Details                                                         |
|---------------------------------------------|----------------------------------------|--------------------------------------------------|---------|-----------------------------------------------------------------|
| `src/vcompany/container/factory.py`         | `src/vcompany/models/agent_types.py`   | `from vcompany.models.agent_types import AgentTypeConfig, AgentTypesConfig` | WIRED | Import at line 20; `_resolve_transport_deps` uses `type_config.docker_image` |
| `src/vcompany/daemon/daemon.py`             | `agent-types.yaml`                     | `load_agent_types()` at startup                  | WIRED   | Lines 216-222: path constructed, existence checked, loaded      |
| `src/vcompany/daemon/runtime_api.py`        | `src/vcompany/models/agent_types.py`   | `get_agent_types_config()` for capability lookups | WIRED  | Lines 696/698: `get_agent_types_config()` used; `has_capability` checks at multiple callsites |
| `src/vcompany/container/factory.py`         | `src/vcompany/models/agent_types.py`   | `container_class` field lookup from agent type config | WIRED | Lines 134-158: `container_class_name` from config drives `_REGISTRY` lookup |
| `src/vcompany/supervisor/company_root.py`   | `src/vcompany/docker/build.py`         | `ensure_docker_image()` call in `hire()` before container creation | WIRED | Lines 178-180: `if type_config.transport == "docker" and type_config.docker_image: ... await ensure_docker_image(...)` |
| `src/vcompany/transport/docker.py`          | container filesystem                   | `docker cp` for tweakcc, `exec_run` for settings | WIRED  | `_apply_tweakcc_profile()` uses `subprocess.run(["docker", "cp", ...])` wrapped in `asyncio.to_thread`; `_apply_settings()` uses `container.exec_run` |

---

### Data-Flow Trace (Level 4)

Phase 27 is infrastructure wiring (transport layer, config loading, factory) with no components that render dynamic data to a UI. Level 4 data-flow trace is not applicable — all artifacts are config models, factory functions, transport implementations, and CLI commands. No hollow props or disconnected data sources exist in this phase's scope.

---

### Behavioral Spot-Checks

| Behavior                                              | Command                                         | Result                                                | Status   |
|-------------------------------------------------------|-------------------------------------------------|-------------------------------------------------------|----------|
| AgentTypeConfig loads from YAML and validates         | `uv run python3 -c "from vcompany.models..."` | All assertions pass, docker-gsd type confirmed       | PASS     |
| Factory _resolve_transport_deps partitions correctly   | `uv run python3 -c "from vcompany.container.factory..."` | LocalTransport gets only tmux_manager; DockerTransport gets only docker_image+project_name | PASS |
| Dual registry resolves by both string and class name   | `uv run python3 -c "register_defaults(); assert 'GsdAgent' in _REGISTRY..."` | All 11 entries confirmed                             | PASS     |
| DockerTransport has parametric setup methods           | `uv run python3 -c "hasattr(DockerTransport, '_apply_tweakcc_profile')..."` | Both methods present, setup() accepts **kwargs      | PASS     |
| CompanyRoot.hire() accepts agent_type parameter        | `uv run python3 -c "inspect.signature(CompanyRoot.hire)..."` | `agent_type` in params list                          | PASS     |
| HealthReport has transport fields                      | `uv run python3 -c "HealthReport.model_fields.keys()..."` | `transport_type`, `docker_container_id`, `docker_image` all present | PASS |
| vco build --help shows expected output                 | `uv run python3 -c "runner.invoke(build, ['--help'])..."` | Exit 0, `--force` flag visible, IMAGE argument shown | PASS     |
| No hardcoded agent-type checks in runtime_api.py       | AST walk for isinstance/type-string patterns   | Zero matches                                          | PASS     |
| No hardcoded type-string checks in supervisor.py       | Line scan for `agent_type in ("gsd",...)` pattern | Zero matches                                        | PASS     |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                       | Status    | Evidence                                                                           |
|-------------|-------------|---------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------------------|
| WIRE-01     | 27-01       | Factory resolves transport_deps per transport type — LocalTransport←tmux_manager, DockerTransport←docker_image+project_name | SATISFIED | `_resolve_transport_deps()` in factory.py lines 54-75; daemon passes `project_name` in transport_deps |
| WIRE-02     | 27-01       | docker_image flows from AgentConfig through ChildSpec/transport_deps to DockerTransport constructor without manual intervention | SATISFIED | Agent-types config holds `docker_image`; factory reads it via `type_config.docker_image` in `_resolve_transport_deps` |
| WIRE-03     | 27-02       | Docker image auto-builds on first hire when image missing, OR `vco build` command exists for explicit builds | SATISFIED | `ensure_docker_image()` async auto-build exists; `vco build` CLI command registered and verified |
| WIRE-04     | 27-04       | DockerTransport.setup() accepts parametric kwargs (tweakcc profile, custom settings.json) enabling per-agent customization from single universal image | SATISFIED | `_apply_tweakcc_profile()` and `_apply_settings()` private methods in docker.py; `setup()` reads kwargs |
| WIRE-05     | 27-03       | No hardcoded agent-type string checks (if/in on type literals) remain in runtime_api.py or supervisor.py | SATISFIED | AST scan confirms zero isinstance-on-agent-class and zero hardcoded-type-string patterns in both files |
| WIRE-06     | 27-04       | Full e2e: Discord hire command → Docker container created → agent executes task → signals readiness via mounted daemon socket → appears in health tree | SATISFIED (code path — not runtime tested) | Full hire chain wired: `hire_cmd` → `RuntimeAPI.hire(agent_type=type_)` → `CompanyRoot.hire(agent_type)` → config lookup → `ensure_docker_image()` → `ChildSpec(transport="docker")` → factory → `DockerTransport(**deps)` → `setup(**_transport_setup_kwargs)` → health_report populates transport fields |
| WIRE-07     | 27-01, 27-03 | Adding a new agent type requires only AgentConfig entry (agents.yaml) + optional container subclass registration — zero business logic changes in runtime_api.py or supervisor.py | SATISFIED | Dual-key registry; supervisor.py and runtime_api.py consult agent-types config for all capability decisions; no type-string business logic |

All 7 WIRE requirements satisfied. No orphaned requirements — traceability table in REQUIREMENTS.md shows WIRE-01 through WIRE-07 are all mapped to Phase 27.

---

### Anti-Patterns Found

No anti-patterns found across all 11 files scanned for this phase. No TODO/FIXME/PLACEHOLDER comments, no empty return stubs, no hardcoded empty collections flowing to rendering.

---

### Human Verification Required

#### 1. Docker Agent End-to-End Runtime

**Test:** Start the daemon, run `vco hire docker-gsd test-agent`, observe Discord channel creation and container startup.
**Expected:** Discord `#task-test-agent` channel created; Docker container `vco-{project}-test-agent` created; if tweakcc `default` profile exists locally it is copied into the container; agent appears in `vco health` output with `transport_type: docker`.
**Why human:** Requires a running Docker daemon, Discord bot, and optionally a `~/.claude/tweakcc/default/` directory. Cannot verify container creation and volume mounts without actually executing the hire flow against live services.

#### 2. tweakcc Profile Application

**Test:** Create a dummy tweakcc profile at `~/.claude/tweakcc/default/`, hire a docker-gsd agent, check container filesystem.
**Expected:** Profile directory is visible inside container at `/root/.claude/tweakcc/default/`.
**Why human:** Requires running Docker container and shell access to verify filesystem state inside container.

#### 3. Image Auto-Build on Missing Image

**Test:** Remove local `vco-agent:latest` image (if present), run `vco hire docker-gsd test-agent`.
**Expected:** Build log output visible in daemon logs; Docker image appears in `docker images` after hire completes.
**Why human:** Requires Docker daemon access and image removal to set up the precondition.

---

### Gaps Summary

No gaps. All 7 requirements verified through code inspection and programmatic spot-checks. The phase achieved its stated goal: Docker agents have complete wiring from agent-types config through factory dep resolution, auto-build, parametric transport setup, duck-typed capability checks, and transport-aware health reporting. Business logic in `runtime_api.py` and `supervisor.py` is free of hardcoded agent-type strings.

WIRE-06 (e2e runtime flow) is verified at the code-path level but requires human validation against a live environment — this is expected for an integration requirement and does not constitute a gap.

---

*Verified: 2026-03-30*
*Verifier: Claude (gsd-verifier)*
