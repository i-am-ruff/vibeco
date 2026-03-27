# Phase 1: Foundation and Configuration - Research

**Researched:** 2026-03-25
**Domain:** Python CLI scaffolding, Pydantic config validation, git/tmux wrapper abstractions, atomic file operations, project structure generation
**Confidence:** HIGH

## Summary

Phase 1 is a greenfield foundation phase. No source code exists yet -- no `src/`, no `pyproject.toml`, no `tests/`. The phase must bootstrap the entire Python project using `uv` (which is NOT currently installed -- must be installed first), define Pydantic models for `agents.yaml` parsing, create the `vco init` and `vco clone` CLI commands via click, build thin git and tmux wrapper modules, implement an atomic file write utility, and deploy per-agent artifacts (hooks config, GSD config, CLAUDE.md, vco command files) into each clone.

The technology choices are fully locked by the CONTEXT.md decisions and STACK.md research. Python 3.12, click for CLI, Pydantic for validation, subprocess for git, libtmux for tmux, PyYAML for YAML parsing, Jinja2 for templates. The project structure follows the architecture defined in `VCO-ARCHITECTURE.md` and `ARCHITECTURE.md` research documents.

**Primary recommendation:** Build bottom-up: (1) uv project init + pyproject.toml, (2) Pydantic config models with validation, (3) shared utilities (atomic write, git ops, file ops), (4) tmux wrapper, (5) `vco init` command, (6) `vco clone` command with artifact deployment, (7) tests throughout.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Flat subcommand structure using click groups: `vco init`, `vco clone`, `vco dispatch`, etc. No nested subcommand groups.
- **D-02:** Follow click conventions: `--flag` for options, positional args for required inputs (e.g., `vco init myproject`).
- **D-03:** Entry point defined in pyproject.toml `[project.scripts]` section.
- **D-04:** Strict validation -- invalid agents.yaml rejected with clear Pydantic validation errors before any filesystem changes.
- **D-05:** Pydantic models for: AgentConfig (id, role, owns, consumes, gsd_mode, system_prompt), ProjectConfig (project, repo, agents, shared_readonly).
- **D-06:** Directory ownership validation: non-overlapping owned directories enforced at parse time.
- **D-07:** Per-clone deployment includes: .claude/settings.json (AskUserQuestion hook), .planning/config.json (GSD config), CLAUDE.md (cross-agent awareness), .claude/commands/vco/checkin.md, .claude/commands/vco/standup.md.
- **D-08:** Agent system prompt generated from template with: agent ID, role, owned directories, rules, milestone scope. Stored in context/agents/{id}.md.
- **D-09:** Template-based generation -- Jinja2 or string.Template for all templated files.
- **D-10:** Follow VCO-ARCHITECTURE.md directory structure exactly (projects/{project-name}/clones/, context/, agents.yaml).
- **D-11:** Context docs (blueprint, interfaces, milestone scope) are provided by the user as input files. `vco init` copies them into the context/ directory.
- **D-12:** Git wrapper: thin module using subprocess.run() for clone, checkout, branch, merge, log, push, status. Standardized error handling and logging.
- **D-13:** tmux wrapper: abstraction over libtmux with create_session(), create_pane(), send_command(), is_alive(), get_output(), kill_pane(). If libtmux breaks, only this module changes.
- **D-14:** Atomic file write utility: write_atomic(path, content) -- writes to {path}.tmp then os.rename(). Used for all coordination files.

### Claude's Discretion
- Internal module organization (how to split vco into packages/modules)
- Specific Pydantic model field types and validators beyond what's specified
- Error message formatting and verbosity levels
- Test structure and fixtures

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | Pydantic models to parse and validate agents.yaml | Standard Stack (pydantic 2.x), Architecture Patterns (model design), Code Examples (validation patterns) |
| FOUND-02 | `vco init` creates project directory structure | Architecture Patterns (project layout from VCO-ARCHITECTURE.md), Code Examples (click command + pathlib) |
| FOUND-03 | `vco clone` creates per-agent repo clones with deployed artifacts | Architecture Patterns (clone artifacts), Code Examples (git clone + artifact deployment) |
| FOUND-04 | Git operations wrapper with error handling and logging | Standard Stack (subprocess), Don't Hand-Roll (git abstraction), Code Examples (git wrapper) |
| FOUND-05 | tmux wrapper abstracts libtmux behind stable interface | Standard Stack (libtmux 0.55.x), Don't Hand-Roll (tmux abstraction), Common Pitfalls (zombie detection) |
| FOUND-06 | All coordination file writes use atomic pattern | Code Examples (write_atomic), Common Pitfalls (partial write races) |
| FOUND-07 | Project uses uv for package management with pyproject.toml | Environment Availability (uv not installed), Standard Stack (uv setup) |
| COORD-04 | Agent system prompt template generates --append-system-prompt content | Architecture Patterns (template rendering), Code Examples (Jinja2 agent prompt) |
| COORD-05 | CLAUDE.md generated per clone with cross-agent awareness rules | Architecture Patterns (CLAUDE.md content from VCO-ARCHITECTURE.md) |
| COORD-06 | /vco:checkin.md and /vco:standup.md deployed to each clone | Architecture Patterns (command file deployment) |
| COORD-07 | .claude/settings.json with AskUserQuestion hook config deployed | Architecture Patterns (hook config deployment) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Project-agnostic**: No hardcoded assumptions about what agents build
- **Agent isolation**: Agents never share working directories, never write outside owned paths
- **Discord-first**: All human interaction through Discord (not relevant to Phase 1 directly)
- **GSD compatibility**: Agents run standard GSD pipelines
- **Single machine**: All agents run on one machine for v1
- **uv for package management**: Use uv instead of pip + venv
- **subprocess for git**: Never use GitPython
- **Avoid**: GitPython, nextcord/disnake, requests, poetry, argparse, celery/dramatiq, SQLAlchemy, Flask/FastAPI

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.3 | Runtime | Installed on system. 3.12 has performance improvements and better error messages. |
| click | 8.1.6+ (target 8.2.x) | CLI framework | Decorator-based command groups. Already system-installed at 8.1.6; uv will manage the project version. |
| pydantic | 2.11.x | Config validation | Type-safe agents.yaml parsing with validation-on-construction. Must be v2, not v1. |
| PyYAML | 6.0.x | YAML parsing | Standard YAML parser. Always use `yaml.safe_load()`. System has 6.0.1. |
| libtmux | 0.55.x | tmux management | Python API over tmux. Pre-1.0, pin tightly. Wrap in abstraction layer. |
| Jinja2 | 3.1.x | Template rendering | For agent system prompts, CLAUDE.md, GSD config. Already system-installed at 3.1.2. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Rich | 14.x | Terminal output | Status tables, colored error messages for CLI. System has 13.7.1; uv manages version. |
| pathlib (stdlib) | N/A | Path manipulation | All file path operations. Type-safe, avoids string concatenation. |
| subprocess (stdlib) | N/A | Git operations | All git commands go through the git wrapper. Use `subprocess.run()` with `capture_output=True`, `text=True`, `check=True`. |
| os (stdlib) | N/A | Atomic rename | `os.rename()` for atomic file writes. |
| tempfile (stdlib) | N/A | Temp file creation | Alternative for atomic writes -- `tempfile.NamedTemporaryFile` in same directory as target. |
| shutil (stdlib) | N/A | File/dir copy | Copying context docs into project structure during `vco init`. |

### Development
| Tool | Version | Purpose |
|------|---------|---------|
| uv | latest (0.9.x) | Package management, venv, project init. NOT currently installed -- Wave 0 must install it. |
| pytest | latest | Test runner. Install via uv as dev dependency. |
| ruff | latest | Linting + formatting. Single tool replaces flake8 + black + isort. |

**Installation (Wave 0 bootstrap):**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
cd /home/developer/vcompany
uv init --name vcompany --python 3.12

# Core dependencies
uv add click pydantic pyyaml libtmux jinja2 rich

# Dev dependencies
uv add --dev pytest ruff
```

**pyproject.toml entry point:**
```toml
[project.scripts]
vco = "vcompany.cli.main:cli"
```

## Architecture Patterns

### Recommended Project Structure
```
vcompany/
├── src/
│   └── vcompany/              # Package root (src layout)
│       ├── __init__.py
│       ├── cli/               # Click CLI commands
│       │   ├── __init__.py
│       │   ├── main.py        # Click group entry point
│       │   ├── init_cmd.py    # vco init
│       │   └── clone_cmd.py   # vco clone
│       ├── models/            # Pydantic config models
│       │   ├── __init__.py
│       │   └── config.py      # AgentConfig, ProjectConfig
│       ├── git/               # Git wrapper
│       │   ├── __init__.py
│       │   └── ops.py         # clone, checkout, branch, etc.
│       ├── tmux/              # tmux wrapper
│       │   ├── __init__.py
│       │   └── session.py     # create_session, create_pane, etc.
│       ├── templates/         # Jinja2 templates
│       │   ├── agent_prompt.md.j2
│       │   ├── claude_md.md.j2
│       │   ├── settings.json.j2
│       │   └── gsd_config.json.j2
│       └── shared/            # Cross-cutting utilities
│           ├── __init__.py
│           ├── file_ops.py    # write_atomic, copy helpers
│           └── logging.py     # Structured logging setup
├── commands/                  # Command templates deployed to clones
│   └── vco/
│       ├── checkin.md
│       └── standup.md
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py         # Pydantic model validation
│   ├── test_git_ops.py        # Git wrapper
│   ├── test_tmux.py           # tmux wrapper
│   ├── test_file_ops.py       # Atomic write
│   ├── test_init_cmd.py       # vco init command
│   └── test_clone_cmd.py      # vco clone command
├── pyproject.toml
└── README.md
```

**Note on src layout:** Use `src/vcompany/` (src layout) for proper package isolation. This prevents accidental imports from the working directory. uv supports this natively.

### Pattern 1: Pydantic Config Validation with Custom Validators
**What:** Define Pydantic models for agents.yaml with field-level and model-level validators. Reject invalid configs before any filesystem operations.
**When to use:** Always -- config parsing is the first operation in both `vco init` and `vco clone`.
**Example:**
```python
# Source: Pydantic v2 documentation + VCO-ARCHITECTURE.md schema
from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

class AgentConfig(BaseModel):
    id: str
    role: str
    owns: list[str]
    consumes: str
    gsd_mode: Literal["full", "quick"]
    system_prompt: str

    @field_validator("id")
    @classmethod
    def id_must_be_uppercase_alphanumeric(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Agent ID must be alphanumeric (with - or _): {v}")
        return v

    @field_validator("owns")
    @classmethod
    def owns_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Agent must own at least one directory")
        return v

class ProjectConfig(BaseModel):
    project: str
    repo: str
    agents: list[AgentConfig]
    shared_readonly: list[str] = []

    @model_validator(mode="after")
    def validate_no_overlapping_ownership(self) -> "ProjectConfig":
        all_dirs: list[str] = []
        for agent in self.agents:
            for d in agent.owns:
                normalized = d.rstrip("/") + "/"
                for existing in all_dirs:
                    if normalized.startswith(existing) or existing.startswith(normalized):
                        raise ValueError(
                            f"Overlapping directory ownership: '{d}' conflicts with '{existing.rstrip('/')}'"
                        )
                all_dirs.append(normalized)
        return self
```

### Pattern 2: Click CLI with Lazy Command Loading
**What:** Define a click group with one file per subcommand. Register commands in main.py.
**When to use:** Standard pattern for multi-command CLIs.
**Example:**
```python
# src/vcompany/cli/main.py
import click

@click.group()
@click.version_option()
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass

# Import and register commands
from vcompany.cli.init_cmd import init
from vcompany.cli.clone_cmd import clone
cli.add_command(init)
cli.add_command(clone)

# src/vcompany/cli/init_cmd.py
import click
from pathlib import Path

@click.command()
@click.argument("project_name")
@click.option("--config", "-c", type=click.Path(exists=True), required=True,
              help="Path to agents.yaml")
@click.option("--blueprint", type=click.Path(exists=True),
              help="Path to PROJECT-BLUEPRINT.md")
@click.option("--interfaces", type=click.Path(exists=True),
              help="Path to INTERFACES.md")
@click.option("--milestone", type=click.Path(exists=True),
              help="Path to MILESTONE-SCOPE.md")
def init(project_name: str, config: str, blueprint: str,
         interfaces: str, milestone: str):
    """Initialize a new vCompany project."""
    # 1. Parse and validate agents.yaml (fails early if invalid)
    # 2. Create directory structure
    # 3. Copy context documents
    # 4. Generate agent system prompts
    pass
```

### Pattern 3: Git Wrapper with Structured Results
**What:** Thin wrapper around `subprocess.run()` calls to git CLI. Returns structured results, standardizes error handling.
**When to use:** All git operations throughout the project.
**Example:**
```python
# src/vcompany/git/ops.py
import subprocess
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class GitResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int

def _run_git(*args: str, cwd: Path | None = None,
             timeout: int = 60) -> GitResult:
    """Run a git command and return structured result."""
    cmd = ["git"] + list(args)
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout
        )
        return GitResult(
            success=result.returncode == 0,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        logger.error("git %s timed out after %ds", " ".join(args), timeout)
        return GitResult(success=False, stdout="", stderr="Timeout", returncode=-1)

def clone(repo_url: str, target: Path, branch: str | None = None) -> GitResult:
    args = ["clone", repo_url, str(target)]
    if branch:
        args.extend(["-b", branch])
    return _run_git(*args)

def checkout_new_branch(branch_name: str, cwd: Path) -> GitResult:
    return _run_git("checkout", "-b", branch_name, cwd=cwd)

def status(cwd: Path) -> GitResult:
    return _run_git("status", "--porcelain", cwd=cwd)
```

### Pattern 4: Atomic File Write
**What:** Write to temp file then rename. Prevents partial reads from monitor or other processes.
**When to use:** All coordination files (PROJECT-STATUS.md, config files, deployed artifacts).
**Example:**
```python
# src/vcompany/shared/file_ops.py
import os
import tempfile
from pathlib import Path

def write_atomic(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to path atomically using tmp-then-rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create temp file in same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.rename(tmp_path, path)  # Atomic on same filesystem
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### Pattern 5: tmux Wrapper Abstraction
**What:** Thin wrapper over libtmux that isolates the pre-1.0 API behind a stable interface.
**When to use:** All tmux session and pane operations.
**Example:**
```python
# src/vcompany/tmux/session.py
import libtmux
import logging

logger = logging.getLogger(__name__)

class TmuxManager:
    """Wrapper around libtmux that provides a stable interface."""

    def __init__(self):
        self._server = libtmux.Server()

    def create_session(self, name: str) -> libtmux.Session:
        """Create a new tmux session. Kills existing session with same name."""
        self.kill_session(name)
        session = self._server.new_session(session_name=name, detach=True)
        logger.info("Created tmux session: %s", name)
        return session

    def kill_session(self, name: str) -> bool:
        """Kill a tmux session by name. Returns True if killed."""
        try:
            session = self._server.sessions.get(session_name=name)
            if session:
                session.kill()
                logger.info("Killed tmux session: %s", name)
                return True
        except Exception:
            pass
        return False

    def create_pane(self, session: libtmux.Session,
                    window_name: str | None = None) -> libtmux.Pane:
        """Create a new pane in the session."""
        if window_name:
            window = session.new_window(window_name=window_name)
        else:
            window = session.active_window
        return window.active_pane

    def send_command(self, pane: libtmux.Pane, command: str) -> None:
        """Send a command to a tmux pane."""
        pane.send_keys(command)

    def is_alive(self, pane: libtmux.Pane) -> bool:
        """Check if the pane's process is still running."""
        try:
            # Check pane PID exists
            pane_pid = pane.pane_pid
            if pane_pid:
                import os
                os.kill(int(pane_pid), 0)  # Signal 0 = check existence
                return True
        except (ProcessLookupError, OSError, TypeError, ValueError):
            pass
        return False

    def get_output(self, pane: libtmux.Pane, lines: int = 50) -> list[str]:
        """Capture recent output from a pane."""
        return pane.capture_pane()

    def kill_pane(self, pane: libtmux.Pane) -> None:
        """Kill a specific pane."""
        pane.kill()
```

### Anti-Patterns to Avoid
- **Using `check=True` in git subprocess calls:** Raises CalledProcessError which is hard to handle gracefully. Use the GitResult pattern above to check `.success` instead.
- **String concatenation for paths:** Always use `pathlib.Path` / operator. Never `os.path.join()` or f-strings for paths.
- **Hardcoding project base dir:** Use `~/vcompany/projects/` as the base from config or a constant, not scattered string literals.
- **Importing from vcompany inside hook scripts:** Hook scripts run in agent clone context. They must be self-contained.
- **Using `yaml.load()` instead of `yaml.safe_load()`:** Security risk. Always `safe_load()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom parser | PyYAML `yaml.safe_load()` | Edge cases in YAML spec are vast |
| Config validation | Manual dict checking | Pydantic v2 models | Type coercion, error messages, nested validation |
| Template rendering | f-string templates | Jinja2 | Conditional blocks, loops, filters, escaping |
| CLI argument parsing | argparse or custom | click | Groups, help gen, type conversion, error handling |
| tmux management | Raw `subprocess.run(["tmux", ...])` | libtmux (wrapped) | Structured API, session/pane objects, less shell escaping |
| Atomic file writes | Manual open/write/close | `write_atomic()` utility (see pattern above) | Edge cases: disk full, permissions, same-filesystem requirement for rename |
| Path manipulation | String concatenation | `pathlib.Path` | OS-aware separators, `.parent`, `.name`, `/` operator |

**Key insight:** This phase establishes foundational patterns. Every shortcut here becomes technical debt that all 6 subsequent phases inherit. Get the abstractions right.

## Common Pitfalls

### Pitfall 1: uv Not Installed
**What goes wrong:** FOUND-07 requires uv for package management, but uv is NOT currently installed on this system.
**Why it happens:** uv is not available via pip on this system (pip install failed). It requires the standalone installer.
**How to avoid:** First task in Wave 0 must install uv via `curl -LsSf https://astral.sh/uv/install.sh | sh`. Verify with `uv --version` before proceeding.
**Warning signs:** `command -v uv` returns nothing.

### Pitfall 2: libtmux API Instability
**What goes wrong:** libtmux is pre-1.0 (0.55.x). API methods change between minor versions. Direct use throughout the codebase creates upgrade pain.
**Why it happens:** Pre-1.0 library = no stability guarantees.
**How to avoid:** All libtmux calls go through `src/vcompany/tmux/session.py`. Pin to exact minor version in pyproject.toml (`libtmux>=0.55.0,<0.56`). Never import libtmux outside the tmux module.
**Warning signs:** Import errors or attribute errors after `uv sync`.

### Pitfall 3: os.rename Fails Across Filesystems
**What goes wrong:** `os.rename()` is only atomic within the same filesystem. If the temp file and target are on different filesystems (e.g., /tmp vs project dir), it fails with `OSError`.
**Why it happens:** `tempfile.mkstemp()` defaults to system temp directory, which may be a different filesystem.
**How to avoid:** Always create the temp file in `path.parent` (same directory as the target). The `write_atomic()` pattern above does this correctly with `dir=path.parent`.
**Warning signs:** `OSError: Invalid cross-device link` errors.

### Pitfall 4: Overlapping Directory Ownership Not Caught
**What goes wrong:** Two agents both own `src/shared/` and `src/shared/types/`. The nested ownership creates ambiguity about who can write where.
**Why it happens:** Naive uniqueness check (just `set(all_dirs)`) misses prefix overlaps.
**How to avoid:** The Pydantic model validator must check for prefix relationships, not just exact matches. Normalize all paths to end with `/` and check `startswith()` in both directions.
**Warning signs:** Two agents modifying files in the same directory tree at runtime.

### Pitfall 5: Git Clone into Existing Directory
**What goes wrong:** `vco clone` is run twice. Second run fails because the clone directory already exists.
**Why it happens:** `git clone` refuses to clone into a non-empty directory.
**How to avoid:** Check if clone directory exists before cloning. Offer `--force` flag to delete and re-clone. Log a clear error message otherwise.
**Warning signs:** `fatal: destination path already exists and is not an empty directory`.

### Pitfall 6: Template Rendering Fails Silently with Missing Variables
**What goes wrong:** Jinja2 template references `{{ MILESTONE_NAME }}` but the variable is not passed to the template context. Jinja2's default behavior is to render it as empty string (with `undefined=Undefined`).
**Why it happens:** Template variables come from agents.yaml and context files. If a field is optional or missing, the template silently drops it.
**How to avoid:** Use `jinja2.StrictUndefined` in the Jinja2 Environment. This raises an error on any undefined variable rather than silently producing empty output.
**Warning signs:** Generated files with blank sections or missing agent IDs.

### Pitfall 7: Branch Name Conflicts
**What goes wrong:** Two agents with similar IDs (e.g., "BACKEND" and "BACKEND-API") produce branch names that collide or confuse.
**Why it happens:** Branch names are derived from agent IDs. If the naming convention isn't strict, collisions happen.
**How to avoid:** Branch name format should be `agent/{agent-id}` with the agent ID validated as unique and normalized (lowercase, hyphens only).
**Warning signs:** `git checkout -b` failing with "branch already exists".

## Code Examples

### Loading and Validating agents.yaml
```python
# Source: Pydantic v2 docs + PyYAML docs
import yaml
from pathlib import Path
from vcompany.models.config import ProjectConfig

def load_config(config_path: Path) -> ProjectConfig:
    """Load and validate agents.yaml. Raises ValidationError on invalid config."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return ProjectConfig(**raw)  # Pydantic validates on construction
```

### Creating Project Directory Structure (vco init)
```python
# Source: VCO-ARCHITECTURE.md directory layout
from pathlib import Path
import shutil

def create_project_structure(
    base_dir: Path,
    project_name: str,
    config: "ProjectConfig",
    blueprint: Path | None = None,
    interfaces: Path | None = None,
    milestone: Path | None = None,
) -> Path:
    """Create the full project directory structure."""
    project_dir = base_dir / "projects" / project_name
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    # Create directories
    (project_dir / "clones").mkdir(parents=True)
    context_dir = project_dir / "context"
    context_dir.mkdir()
    (context_dir / "agents").mkdir()

    # Copy context documents
    if blueprint:
        shutil.copy2(blueprint, context_dir / "PROJECT-BLUEPRINT.md")
    if interfaces:
        shutil.copy2(interfaces, context_dir / "INTERFACES.md")
    if milestone:
        shutil.copy2(milestone, context_dir / "MILESTONE-SCOPE.md")

    # Copy agents.yaml to project root
    # (already validated by this point)
    shutil.copy2(config_path, project_dir / "agents.yaml")

    # Generate agent system prompts
    for agent in config.agents:
        _render_agent_prompt(agent, config, context_dir / "agents" / f"{agent.id}.md")

    return project_dir
```

### Deploying Per-Clone Artifacts (vco clone)
```python
# Source: CONTEXT.md D-07, VCO-ARCHITECTURE.md
from pathlib import Path
from vcompany.shared.file_ops import write_atomic

def deploy_clone_artifacts(
    clone_dir: Path,
    agent: "AgentConfig",
    config: "ProjectConfig",
    templates: "jinja2.Environment",
) -> None:
    """Deploy all required artifacts to an agent's clone."""
    # 1. .claude/settings.json (AskUserQuestion hook config)
    claude_dir = clone_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_content = templates.get_template("settings.json.j2").render(
        agent_id=agent.id
    )
    write_atomic(claude_dir / "settings.json", settings_content)

    # 2. .planning/config.json (GSD config)
    planning_dir = clone_dir / ".planning"
    planning_dir.mkdir(exist_ok=True)
    gsd_config = templates.get_template("gsd_config.json.j2").render(
        agent=agent, project=config
    )
    write_atomic(planning_dir / "config.json", gsd_config)

    # 3. CLAUDE.md (cross-agent awareness)
    claude_md = templates.get_template("claude_md.md.j2").render(
        agent=agent, project=config
    )
    write_atomic(clone_dir / "CLAUDE.md", claude_md)

    # 4. .claude/commands/vco/checkin.md and standup.md
    commands_dir = claude_dir / "commands" / "vco"
    commands_dir.mkdir(parents=True, exist_ok=True)
    # Copy from vcompany's commands/ directory
    for cmd_file in ["checkin.md", "standup.md"]:
        source = Path(__file__).parent.parent.parent.parent / "commands" / "vco" / cmd_file
        shutil.copy2(source, commands_dir / cmd_file)
```

### Jinja2 Template Setup with StrictUndefined
```python
# Source: Jinja2 docs
import jinja2
from pathlib import Path

def create_template_env() -> jinja2.Environment:
    """Create Jinja2 environment with strict undefined checking."""
    template_dir = Path(__file__).parent.parent / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pip + venv + requirements.txt | uv (single tool) | 2024-2025 | 10-100x faster installs, lockfile support, replaces 3+ tools |
| Pydantic v1 | Pydantic v2 | 2023 | Different API (model_validator vs root_validator, field_validator vs validator). Must use v2 syntax. |
| GitPython library | subprocess + git CLI | Ongoing | GitPython in maintenance mode. subprocess is lighter and more reliable. |
| poetry for project management | uv | 2025-2026 | uv handles everything poetry does, much faster |

**Deprecated/outdated:**
- Pydantic v1 syntax (`@validator`, `@root_validator`, `class Config:`) -- must use v2 syntax (`@field_validator`, `@model_validator`, `model_config`)
- `setup.py` / `setup.cfg` -- use `pyproject.toml` exclusively
- `pip install -e .` -- use `uv pip install -e .` or `uv sync`

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| Git | FOUND-04, FOUND-03 | Yes | 2.43.0 | -- |
| tmux | FOUND-05 | Yes | 3.4 | -- |
| Node.js | GSD/Claude Code | Yes | 22.22.1 | -- |
| GitHub CLI (gh) | Git operations | Yes | 2.88.1 | -- |
| uv | FOUND-07 | **No** | -- | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pip | Fallback package mgr | Yes | 24.0 | -- |
| Jinja2 | Template rendering | Yes (system) | 3.1.2 | -- |
| click | CLI framework | Yes (system) | 8.1.6 | uv will manage project version |
| PyYAML | Config parsing | Yes (system) | 6.0.1 | uv will manage project version |
| pydantic | Config validation | **No** | -- | Install via uv |
| libtmux | tmux wrapper | **No** | -- | Install via uv |
| Rich | Terminal output | Yes (system) | 13.7.1 | uv will manage project version |
| pytest | Testing | **No** | -- | Install via uv as dev dep |
| ruff | Lint + format | **No** | -- | Install via uv as dev dep |

**Missing dependencies with no fallback:**
- **uv** -- must be installed first before any other setup. This is the blocking dependency.

**Missing dependencies with fallback:**
- pydantic, libtmux, pytest, ruff -- all installable via uv once uv is available.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (latest, installed via uv) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section (Wave 0) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Pydantic parses valid agents.yaml, rejects invalid | unit | `uv run pytest tests/test_config.py -x` | Wave 0 |
| FOUND-02 | `vco init` creates correct directory structure | integration | `uv run pytest tests/test_init_cmd.py -x` | Wave 0 |
| FOUND-03 | `vco clone` creates isolated clones with artifacts | integration | `uv run pytest tests/test_clone_cmd.py -x` | Wave 0 |
| FOUND-04 | Git wrapper handles clone, branch, status, errors | unit | `uv run pytest tests/test_git_ops.py -x` | Wave 0 |
| FOUND-05 | tmux wrapper creates sessions, checks liveness | unit | `uv run pytest tests/test_tmux.py -x` | Wave 0 |
| FOUND-06 | Atomic write produces complete files, no partial reads | unit | `uv run pytest tests/test_file_ops.py -x` | Wave 0 |
| FOUND-07 | Project bootstrapped with uv, pyproject.toml valid | smoke | `uv run python -c "import vcompany"` | Wave 0 |
| COORD-04 | Agent system prompt rendered with all variables | unit | `uv run pytest tests/test_config.py::test_agent_prompt_generation -x` | Wave 0 |
| COORD-05 | CLAUDE.md generated with cross-agent awareness | unit | `uv run pytest tests/test_clone_cmd.py::test_claude_md_content -x` | Wave 0 |
| COORD-06 | checkin.md and standup.md deployed to clone | integration | `uv run pytest tests/test_clone_cmd.py::test_command_files_deployed -x` | Wave 0 |
| COORD-07 | .claude/settings.json deployed with hook config | integration | `uv run pytest tests/test_clone_cmd.py::test_settings_json_deployed -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` with `[tool.pytest.ini_options]` section
- [ ] `tests/conftest.py` -- shared fixtures (tmp directories, sample agents.yaml, mock git repos)
- [ ] `tests/test_config.py` -- FOUND-01 validation tests
- [ ] `tests/test_git_ops.py` -- FOUND-04 wrapper tests
- [ ] `tests/test_tmux.py` -- FOUND-05 wrapper tests
- [ ] `tests/test_file_ops.py` -- FOUND-06 atomic write tests
- [ ] `tests/test_init_cmd.py` -- FOUND-02 integration tests
- [ ] `tests/test_clone_cmd.py` -- FOUND-03, COORD-05, COORD-06, COORD-07 tests
- [ ] Framework install: `uv add --dev pytest`

## Open Questions

1. **Exact pyproject.toml package name and layout**
   - What we know: Entry point is `vco = "vcompany.cli.main:cli"`. Using src layout.
   - What's unclear: Whether uv init will produce a src layout by default or needs flags.
   - Recommendation: Use `uv init --lib` for src layout, or manually adjust after `uv init`. Verify the `[tool.setuptools.packages.find]` or `[build-system]` section is correct.

2. **libtmux exact API for version 0.55.x**
   - What we know: The wrapper pattern isolates API calls. Basic methods like `new_session`, `kill`, `send_keys`, `capture_pane` are stable across recent versions.
   - What's unclear: Exact property names for pane PID (`pane_pid` vs other attributes). The `sessions.get()` API may have changed.
   - Recommendation: After installing libtmux, run a quick interactive test in Python to verify the API. The wrapper isolates any needed corrections.

3. **GSD config.json exact schema for agent clones**
   - What we know: VCO-ARCHITECTURE.md shows a sample with mode, granularity, workflow, git settings.
   - What's unclear: Whether .planning/config.json in clones needs all fields or just overrides.
   - Recommendation: Deploy the full config as shown in VCO-ARCHITECTURE.md. GSD reads the whole file.

## Sources

### Primary (HIGH confidence)
- VCO-ARCHITECTURE.md -- authoritative system design, directory structure, agent prompt template, GSD config schema
- .planning/research/ARCHITECTURE.md -- component boundaries, project structure, build order
- .planning/research/PITFALLS.md -- atomic write races, tmux zombie detection, crash recovery patterns
- .planning/research/STACK.md -- library versions, alternatives considered, version compatibility
- CONTEXT.md decisions D-01 through D-14 -- locked implementation choices

### Secondary (MEDIUM confidence)
- Pydantic v2 documentation -- model_validator, field_validator syntax
- click documentation -- command groups, argument/option patterns
- Jinja2 documentation -- StrictUndefined, Environment configuration

### Tertiary (LOW confidence)
- libtmux 0.55.x API specifics -- need runtime verification after install (pre-1.0 API)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries specified in STACK.md with versions, verified against system
- Architecture: HIGH -- project structure defined in VCO-ARCHITECTURE.md + ARCHITECTURE.md research
- Pitfalls: HIGH -- atomic write, tmux zombies, libtmux instability all documented in PITFALLS.md
- Environment: HIGH -- all tools probed, uv gap identified with clear remediation

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, locked decisions)
