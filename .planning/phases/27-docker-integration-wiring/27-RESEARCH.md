# Phase 27: Docker Integration Wiring - Research

**Researched:** 2026-03-30
**Domain:** Docker agent wiring, config-driven agent types, factory pattern evolution
**Confidence:** HIGH

## Summary

Phase 27 wires together all Docker infrastructure built in Phases 25-26 so Docker agents work end-to-end. The core work is: (1) making the factory smart about per-transport dependency resolution instead of passing a single global dict, (2) creating an `agent-types.yaml` config file as the single source of truth for all agent types, (3) replacing hardcoded type-string checks with config-derived capability lookups, (4) adding auto-build logic for Docker images, and (5) enabling parametric per-agent customization at container start time.

The codebase is well-positioned for this. The transport registry pattern (`_TRANSPORT_REGISTRY` in factory.py) and container registry pattern (`_REGISTRY`) already exist. DockerTransport is fully implemented. The main gaps are: docker_image never flows from AgentConfig to DockerTransport constructor, the daemon passes a single global `transport_deps` dict, several `isinstance` and string-literal type checks exist in runtime_api.py and supervisor.py, and no agent-types config file exists yet.

**Primary recommendation:** Implement in order: agent-types.yaml schema + loader first (foundation), then factory dep resolution + ChildSpec enrichment, then type-check elimination, then auto-build + vco build CLI, then parametric setup, then e2e validation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Factory is the smart resolver -- reads docker_image and per-agent fields from ChildSpec/config, merges with global transport_deps, passes to transport constructor. Daemon stays simple.
- D-02: `vco hire <type> <name>` knows nothing about transport details. All resolution from config lookup.
- D-03: Auto-build inline on first hire -- when Docker agent hired and image missing, build before creating container.
- D-04: `vco build` command exists for explicit pre-builds and rebuilds.
- D-05: Agent-types config file (separate from agents.yaml) is single source of truth for ALL agent types.
- D-06: Per-agent customization (tweakcc profile, Claude settings) applied at container start time via DockerTransport.setup().
- D-07: Customization defined at type level in agent-types config. Per-agent overrides not in scope.
- D-08: Full schema defined upfront with future-facing fields parsed but not all enforced.
- D-09: Schema includes env vars and volume overrides from day one. Resource limits and network mode deferred.
- D-10: Config file is separate from agents.yaml -- dedicated `agent-types.yaml`.
- D-11: Config-derived capabilities replace hardcoded type string checks. Capability flags on type config.
- D-12: All hardcoded type checks in runtime_api.py and supervisor.py replaced with capability checks or registry lookups.
- D-13: Container subclass registration via config -- `container_class` field maps to `_CONTAINER_REGISTRY`.
- D-14: Docker agents follow same hire-to-health path as local agents.

### Claude's Discretion
- Docker-specific health info in health tree (container ID, image version, uptime)
- Implementation details of factory dep extraction from ChildSpec/context
- ChildSpec field additions needed to carry docker_image through pipeline
- How capability checks are structured in runtime code
- Default values for agent-types config fields when omitted

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WIRE-01 | Factory resolves transport_deps per transport type | Factory pattern analysis, daemon line 208, per-transport dep mapping |
| WIRE-02 | docker_image flows from AgentConfig through ChildSpec to DockerTransport | ChildSpec lacks docker_image field; factory line 84 passes flat deps; DockerTransport.__init__ takes docker_image kwarg |
| WIRE-03 | Docker image auto-builds on first use OR vco build exists | No build logic exists; Dockerfile at docker/Dockerfile; docker-py SDK available |
| WIRE-04 | DockerTransport.setup() accepts parametric kwargs | setup() already accepts **kwargs (line 55); needs profile/settings copy logic |
| WIRE-05 | No hardcoded agent-type string checks in runtime_api.py or supervisor.py | Inventory of all type checks completed (see Architecture Patterns) |
| WIRE-06 | Full e2e: Discord hire -> Docker container -> task -> readiness signal -> health tree | Hire flow via RuntimeAPI.hire() -> CompanyRoot.hire(); signal path via vco signal; health via HealthReport |
| WIRE-07 | New agent type requires only config entry + optional subclass | Agent-types.yaml + container_class registry pattern |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| docker (docker-py) | >=7.1,<8 | Docker SDK for Python | Already a project dependency. Used by DockerTransport for container lifecycle. |
| pydantic | >=2.11,<3 | Agent-types config schema | Already used for all config models. Validates agent-types.yaml on load. |
| PyYAML | >=6.0 | agent-types.yaml parsing | Already used for agents.yaml. Same pattern: yaml.safe_load() -> Pydantic model. |
| click | >=8.1.6 | vco build CLI command | Already used for all CLI commands. |

### No New Dependencies
This phase requires zero new packages. All work uses existing stack: docker-py for image builds, Pydantic for config schema, PyYAML for config loading, click for CLI.

## Architecture Patterns

### Agent-Types Config File (`agent-types.yaml`)

Per D-05/D-08/D-10, this is a separate file from agents.yaml. Location should be alongside agents.yaml (project root or config directory).

```yaml
# agent-types.yaml -- single source of truth for all agent types
agent_types:
  gsd:
    transport: local
    container_class: GsdAgent          # maps to _CONTAINER_REGISTRY key
    capabilities:
      - gsd_driven
      - uses_tmux
    gsd_command: "/gsd:discuss-phase 1"
    tweakcc_profile: null
    settings_json: null
    env: {}
    volumes: {}

  continuous:
    transport: local
    container_class: ContinuousAgent
    capabilities:
      - uses_tmux
    gsd_command: null
    tweakcc_profile: null
    settings_json: null
    env: {}
    volumes: {}

  fulltime:
    transport: local
    container_class: FulltimeAgent
    capabilities:
      - event_driven
      - reviews_plans
    gsd_command: null
    tweakcc_profile: null
    settings_json: null
    env: {}
    volumes: {}

  company:
    transport: local
    container_class: CompanyAgent
    capabilities:
      - event_driven
    gsd_command: null
    tweakcc_profile: null
    settings_json: null
    env: {}
    volumes: {}

  task:
    transport: local
    container_class: TaskAgent
    capabilities:
      - uses_tmux
    gsd_command: null
    tweakcc_profile: null
    settings_json: null
    env: {}
    volumes: {}

  docker-gsd:
    transport: docker
    docker_image: "vco-agent:latest"
    container_class: GsdAgent
    capabilities:
      - gsd_driven
      - uses_tmux
    gsd_command: "/gsd:discuss-phase 1"
    tweakcc_profile: "default"
    settings_json: null
    env:
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
    volumes: {}
```

### Pydantic Schema for Agent Type Config

```python
class AgentTypeConfig(BaseModel):
    """Schema for a single agent type definition."""
    transport: str = "local"
    docker_image: str | None = None
    container_class: str = "AgentContainer"  # key in _CONTAINER_REGISTRY
    capabilities: list[str] = []
    gsd_command: str | None = None
    tweakcc_profile: str | None = None
    settings_json: str | None = None  # path or inline content
    env: dict[str, str] = {}
    volumes: dict[str, str] = {}  # host:container path pairs

class AgentTypesConfig(BaseModel):
    """Top-level agent-types.yaml schema."""
    agent_types: dict[str, AgentTypeConfig]

    def get_type(self, type_name: str) -> AgentTypeConfig:
        if type_name not in self.agent_types:
            raise KeyError(f"Unknown agent type: {type_name!r}")
        return self.agent_types[type_name]

    def has_capability(self, type_name: str, capability: str) -> bool:
        return capability in self.get_type(type_name).capabilities
```

### Factory Smart Resolution Pattern (D-01)

Current factory (line 78-84):
```python
# CURRENT: single global deps passed to all transports
transport_cls = _TRANSPORT_REGISTRY.get(transport_name)
deps = transport_deps or {}
transport = transport_cls(**deps)
```

Target pattern:
```python
# NEW: factory resolves per-transport deps from spec + global context
def _resolve_transport_deps(
    spec: ChildSpec,
    global_deps: dict,
    agent_type_config: AgentTypeConfig | None = None,
) -> dict:
    transport_name = spec.transport
    if transport_name == "local":
        return {"tmux_manager": global_deps.get("tmux_manager")}
    elif transport_name == "docker":
        return {
            "docker_image": agent_type_config.docker_image if agent_type_config else spec.docker_image,
            "project_name": spec.context.project_id or "",
        }
    return {}
```

Key insight: the factory extracts what each transport constructor needs. The daemon continues to provide global deps (tmux_manager). The factory also reads agent-type-specific fields (docker_image) from the agent type config or ChildSpec.

### ChildSpec Enrichment

ChildSpec needs additional fields to carry docker_image and transport through the pipeline:

```python
class ChildSpec(BaseModel):
    child_id: str
    agent_type: str
    context: ContainerContext
    restart_policy: RestartPolicy = RestartPolicy.PERMANENT
    max_restarts: int = 3
    restart_window_seconds: int = 600
    transport: str = "local"
    docker_image: str | None = None  # NEW: flows from AgentConfig
```

Alternatively (and preferably per D-01): the factory looks up the agent type config directly rather than threading docker_image through ChildSpec. This keeps ChildSpec lean and makes the agent-types.yaml the single source of truth.

### Hardcoded Type Check Inventory

**Files requiring changes (runtime_api.py):**

| Line | Current Code | Replacement |
|------|-------------|-------------|
| 710 | `gsd_command="/gsd:discuss-phase 1" if agent_cfg.type == "gsd" else None` | Look up `gsd_command` from agent-types config |
| 711 | `uses_tmux=agent_cfg.type in ("gsd", "continuous")` | Look up `"uses_tmux" in capabilities` from agent-types config |
| 344, 725, 756 | `isinstance(child, FulltimeAgent)` | Check capability (e.g., `"reviews_plans"` or `"event_driven"`) or use duck typing |
| 449, 605, 636 | `isinstance(container, GsdAgent)` | Check capability (e.g., `"gsd_driven"`) or duck typing (hasattr check for resolve_review) |
| 689 | `isinstance(strategist_container, CompanyAgent)` | Duck typing: `hasattr(container, 'initialize_conversation')` |

**Files requiring changes (supervisor.py):**

| Line | Current Code | Replacement |
|------|-------------|-------------|
| 177 | `uses_tmux=request.agent_type in ("gsd", "continuous", "task")` | Look up capabilities from agent-types config |

**Nuance on isinstance checks:** Some isinstance checks (lines 449, 605, 636) guard access to GsdAgent-specific methods like `resolve_review()`. These should use duck typing (`hasattr(container, 'resolve_review')`) rather than capability flags, since they're checking for method availability, not behavioral capability.

### Container Class Registry Enhancement

Current factory has two registries:
- `_REGISTRY`: agent_type string -> container class (for `register_agent_type()`)
- `_TRANSPORT_REGISTRY`: transport name -> transport class

D-13 says agent-types.yaml has `container_class: GsdAgent` that maps to the registry. The existing `_REGISTRY` and `register_defaults()` pattern already does this. The enhancement is: factory reads `container_class` from agent-types config instead of relying on `agent_type` string directly.

```python
# Current: cls = _REGISTRY.get(spec.agent_type, AgentContainer)
# New: cls = _REGISTRY.get(agent_type_config.container_class, AgentContainer)
```

### Auto-Build Pattern (D-03, D-04)

```python
async def ensure_image_exists(image_name: str, dockerfile_dir: Path) -> None:
    """Build Docker image if it doesn't exist locally."""
    client = docker.from_env()
    try:
        client.images.get(image_name)
        logger.info("Image %s found locally", image_name)
    except docker.errors.ImageNotFound:
        logger.info("Image %s not found, building...", image_name)
        client.images.build(
            path=str(dockerfile_dir),
            tag=image_name,
            rm=True,
        )
        logger.info("Built image %s", image_name)
```

Call site: in factory's `create_container()` or in CompanyRoot.hire(), before creating the transport. The Dockerfile lives at `docker/Dockerfile`.

### Parametric Setup Pattern (D-06)

DockerTransport.setup() already accepts `**kwargs`. Add logic to copy tweakcc profile and settings into container after start:

```python
async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
    # ... existing container creation/start logic ...

    # NEW: parametric customization
    tweakcc_profile = kwargs.get("tweakcc_profile")
    settings_json = kwargs.get("settings_json")

    if tweakcc_profile:
        # Copy profile into container's ~/.claude/ via docker cp or exec
        await self._apply_tweakcc_profile(container, tweakcc_profile)

    if settings_json:
        # Copy/write settings.json into container
        await self._apply_settings(container, settings_json)
```

### Anti-Patterns to Avoid
- **Threading config through every layer:** Don't add docker_image to ChildSpec AND ContainerContext AND AgentConfig. The agent-types.yaml is the single source -- factory reads it directly.
- **Transport-aware daemon:** Don't make the daemon know about Docker. It stays simple: provides global deps, factory resolves per-transport.
- **Capability explosion:** Don't create a capability for every method. Use capabilities for behavioral categories (gsd_driven, event_driven, uses_tmux). Use duck typing (hasattr) for method-level checks.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker image build | Custom subprocess docker build | `docker.images.build()` from docker-py | Already a dependency; handles build context, streaming output, error handling |
| Docker image existence check | `subprocess.run(["docker", "images", ...])` | `docker.images.get(name)` catching `ImageNotFound` | Type-safe, no output parsing |
| YAML config with validation | Manual dict parsing | Pydantic model + PyYAML `safe_load()` | Same pattern as existing agents.yaml; validation on construction |

## Common Pitfalls

### Pitfall 1: Circular Import from Agent-Types Config
**What goes wrong:** Loading agent-types.yaml requires importing container classes for the registry, which may import back into config.
**Why it happens:** The container_class field in config needs to resolve to actual Python classes.
**How to avoid:** Keep the registry as string-to-class mapping populated by `register_defaults()`. Config stores string names only. Factory resolves string to class at creation time, not at config load time.
**Warning signs:** ImportError during startup.

### Pitfall 2: Docker Build Blocks Event Loop
**What goes wrong:** `docker.images.build()` is synchronous and can take minutes. If called from async context, it blocks the event loop.
**Why it happens:** docker-py SDK is synchronous.
**How to avoid:** Wrap in `asyncio.to_thread()` -- same pattern DockerTransport already uses for all docker-py calls.
**Warning signs:** Daemon becomes unresponsive during first Docker agent hire.

### Pitfall 3: isinstance Checks Needed for Subclass Methods
**What goes wrong:** Replacing all isinstance checks with capability flags breaks access to subclass-specific methods.
**Why it happens:** `container.resolve_review()` only exists on GsdAgent. Capability flag says "gsd_driven" but doesn't guarantee the method exists.
**How to avoid:** Use `hasattr(container, 'method_name')` for method-access guards. Use capability flags for behavioral routing (which agents get gsd_command, which use tmux). These are two different concerns.
**Warning signs:** AttributeError at runtime when calling subclass method on base class.

### Pitfall 4: Agent-Types Config Not Found
**What goes wrong:** Config file path is wrong or file doesn't exist, causing startup failure.
**Why it happens:** Separate file from agents.yaml means a new file to manage.
**How to avoid:** Provide sensible defaults in code (matching current hardcoded behavior). If agent-types.yaml is missing, fall back to built-in defaults. Log a warning but don't crash.
**Warning signs:** KeyError on agent type lookup.

### Pitfall 5: Breaking Existing Local Agent Flow
**What goes wrong:** Refactoring factory for Docker support breaks the working local transport path.
**Why it happens:** Factory changes affect ALL agent creation, not just Docker.
**How to avoid:** Ensure the default path (transport="local", no agent-types config) works identically to current behavior. Test local agent creation first after each factory change.
**Warning signs:** Local agents fail to start after factory refactor.

## Code Examples

### Loading Agent-Types Config

```python
# src/vcompany/models/agent_types.py
from pathlib import Path
import yaml
from pydantic import BaseModel

class AgentTypeConfig(BaseModel):
    transport: str = "local"
    docker_image: str | None = None
    container_class: str = "AgentContainer"
    capabilities: list[str] = []
    gsd_command: str | None = None
    tweakcc_profile: str | None = None
    settings_json: str | None = None
    env: dict[str, str] = {}
    volumes: dict[str, str] = {}

class AgentTypesConfig(BaseModel):
    agent_types: dict[str, AgentTypeConfig]

def load_agent_types(config_path: Path) -> AgentTypesConfig:
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return AgentTypesConfig(**(raw or {}))
```

### Factory Per-Transport Dep Resolution

```python
def _resolve_transport_deps(
    transport_name: str,
    global_deps: dict,
    type_config: AgentTypeConfig | None,
) -> dict:
    if transport_name == "local":
        return {k: v for k, v in global_deps.items() if k == "tmux_manager"}
    if transport_name == "docker":
        image = type_config.docker_image if type_config else "vco-agent:latest"
        project = global_deps.get("project_name", "")
        return {"docker_image": image, "project_name": project}
    return {}
```

### Capability Check Replacement

```python
# BEFORE (runtime_api.py line 710-711):
gsd_command="/gsd:discuss-phase 1" if agent_cfg.type == "gsd" else None,
uses_tmux=agent_cfg.type in ("gsd", "continuous"),

# AFTER:
type_config = agent_types.get_type(agent_cfg.type)
gsd_command=type_config.gsd_command,
uses_tmux="uses_tmux" in type_config.capabilities,
```

### Duck Typing for Method Guards

```python
# BEFORE (runtime_api.py line 449):
if not isinstance(container, GsdAgent):
    return False
return container.resolve_review(decision)

# AFTER:
if not hasattr(container, 'resolve_review'):
    return False
return container.resolve_review(decision)
```

### Auto-Build in Factory

```python
import asyncio
import docker
import docker.errors

async def ensure_docker_image(image: str, build_dir: Path) -> None:
    client = docker.from_env()
    try:
        await asyncio.to_thread(client.images.get, image)
    except docker.errors.ImageNotFound:
        logger.info("Building Docker image %s from %s", image, build_dir)
        await asyncio.to_thread(
            client.images.build, path=str(build_dir), tag=image, rm=True
        )
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | DockerTransport, auto-build | Yes | 28.2.2 | -- |
| docker-py (Python) | Docker SDK calls | In pyproject.toml (>=7.1,<8) | Not yet installed in env | `uv sync` |
| tmux | LocalTransport (existing) | Yes | 3.4 (Ubuntu 24.04) | -- |
| Node.js 22 | Claude Code inside containers | Yes (base image) | 22 LTS | -- |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** docker-py may need `uv sync` to install into the active venv.

## Open Questions

1. **Agent-types.yaml location**
   - What we know: Separate from agents.yaml per D-10. Should live where the daemon can find it.
   - What's unclear: Project-level or repo-level? Does each project have its own agent-types.yaml or is it global?
   - Recommendation: Global file at repo root (alongside pyproject.toml). Agent types are system-wide, not project-specific. Projects reference types by name in agents.yaml.

2. **How factory gets agent-types config**
   - What we know: Factory currently receives transport_deps dict. Needs access to AgentTypesConfig.
   - What's unclear: Thread through as parameter, or make it a module-level singleton?
   - Recommendation: Pass via transport_deps dict as a special key (e.g., `"agent_types_config": config`), or add it as a parameter to create_container(). The daemon loads it at startup and passes it through. Module singleton is also viable since agent types don't change at runtime.

3. **FulltimeAgent isinstance checks (lines 344, 725, 756)**
   - What we know: These find the PM container to wire backlog and mention routing.
   - What's unclear: What capability or duck-typing check replaces them?
   - Recommendation: Use `hasattr(child, 'some_pm_specific_attr')` or check capability `"reviews_plans"`. The PM is "the FulltimeAgent in the project" -- could also look up by agent_type from config.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: factory.py, runtime_api.py, supervisor.py, docker.py, container.py, child_spec.py, config.py, company_root.py
- CONTEXT.md decisions D-01 through D-14
- REQUIREMENTS.md WIRE-01 through WIRE-07

### Secondary (MEDIUM confidence)
- docker-py SDK documentation (build, images.get, ImageNotFound exception patterns)
- Pydantic v2 model patterns (already used extensively in codebase)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns already in codebase
- Architecture: HIGH -- decisions are locked and specific, codebase is well-understood
- Pitfalls: HIGH -- derived from actual code analysis, known patterns

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable -- internal architecture, no external API dependencies)
