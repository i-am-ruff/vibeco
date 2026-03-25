# Stack Research

**Domain:** Python CLI orchestrator + Discord bot for multi-agent Claude Code management
**Researched:** 2026-03-25
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Runtime | 3.12 has significant performance improvements (up to 5% faster) and better error messages. 3.11 is the floor per PROJECT.md but 3.12 is the target. Xubuntu 24.04 ships 3.12. |
| discord.py | 2.7.x | Discord bot framework | The standard Python Discord library. Async-native, actively maintained, supports slash commands, message components, threads, webhooks. No credible alternative exists for Python Discord bots. |
| anthropic | 0.86.x | Claude API for PM/Strategist | Official Anthropic SDK. Required for the Strategist bot that answers agent questions and reviews plans. Pin to ~0.86 but expect frequent updates. |
| click | 8.2.x | CLI framework for `vco` | Battle-tested, 38.7% market share in Python CLIs. Decorator-based command groups map perfectly to `vco init`, `vco dispatch`, `vco status`, etc. Mature plugin ecosystem. |
| libtmux | 0.55.x | tmux session management | Typed Python API over tmux. Create/destroy sessions, send keys to panes, read pane output. Exactly what `vco dispatch` and `vco monitor` need for agent session lifecycle. **Pin tightly** -- pre-1.0 with breaking API changes. |
| PyYAML | 6.0.x | agents.yaml parsing | Standard YAML parser for Python. agents.yaml is the core configuration format. Use `yaml.safe_load()` always. |
| Rich | 14.2.x | Terminal output formatting | Tables, progress bars, colored output for `vco status`, `vco standup`, monitor logs. Makes CLI output readable without a web UI. |

### Database / State

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Filesystem (YAML/Markdown) | N/A | All state storage | vCompany state lives in files: agents.yaml, PROJECT-STATUS.md, ROADMAP.md, git logs. No database needed. This is correct -- adding SQLite or similar would add complexity with zero value for a single-machine orchestrator. |

### Infrastructure / Runtime

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| tmux | 3.4+ | Agent session management | Each agent runs in a tmux pane. Monitor checks liveness via tmux. Ubuntu 24.04 ships tmux 3.4. |
| Git | 2.43+ | Agent isolation and integration | Each agent gets a full clone. Branches for isolation, merging for integration. Ubuntu 24.04 ships 2.43. |
| GitHub CLI (gh) | 2.x | GitHub operations | Used by agents and potentially by `vco integrate` for PR creation. Already a dependency of GSD. |
| Node.js | 22 LTS | Claude Code / GSD runtime | Claude Code and GSD run on Node. Not a Python dependency but a system requirement. |
| uv | 0.9.x | Python package/project management | 10-100x faster than pip. Handles venv creation, dependency resolution, lockfiles. Use `uv` for the project from day one instead of pip + venv + pip-tools. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.11.x | Data validation and config models | Model agents.yaml schema, Discord webhook payloads, monitor state. Type-safe configuration prevents runtime surprises. |
| pydantic-settings | 2.13.x | Environment/dotenv config | Load Discord bot token, Anthropic API key, and other secrets from .env files. Validates on startup -- fail fast on missing config. |
| httpx | 0.28.x | HTTP client (async + sync) | Discord webhook calls from agents (ask_discord.py). Prefer over aiohttp because vco CLI needs sync calls too, and httpx handles both. Prefer over requests because httpx is async-capable. |
| watchfiles | 0.24.x | File system monitoring | Monitor loop watches for new PLAN.md files (plan gate trigger). Rust-backed, faster than watchdog, native async support. |
| asyncio (stdlib) | N/A | Async orchestration | discord.py is async-native. The Strategist bot, monitor loop, and webhook handlers all benefit from asyncio. Part of stdlib -- no install needed. |
| subprocess / asyncio.subprocess | N/A | Process spawning | Dispatch Claude Code sessions, run git commands, invoke GSD. Use `asyncio.create_subprocess_exec` in async contexts (bot, monitor), `subprocess.run` in sync CLI commands. |
| pathlib (stdlib) | N/A | Path manipulation | All file path operations for clones, context files, config. Type-safe, cross-platform (though we only target Linux). |
| dataclasses (stdlib) | N/A | Simple data containers | Internal state objects that don't need Pydantic validation overhead. Use for monitor state, agent status tracking. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package management + venv | `uv init`, `uv add`, `uv sync`. Replaces pip, pip-tools, virtualenv, pyproject.toml management. |
| ruff | Linting + formatting | Single tool replaces flake8 + black + isort. Fast (Rust-based). Configure in pyproject.toml. |
| pytest | Testing | Standard Python test runner. Use pytest-asyncio for testing async bot/monitor code. |
| pytest-asyncio | Async test support | Required for testing discord.py bot handlers and async monitor functions. |
| mypy | Type checking | Optional but recommended. Pydantic models + type hints catch bugs early. Use `--strict` mode. |

## Project Structure

```
vcompany/
  pyproject.toml          # uv project config, dependencies, tool settings
  uv.lock                 # Locked dependency versions
  src/
    vco/
      __init__.py
      cli.py              # click CLI entry point
      commands/            # One module per vco command group
        init.py
        clone.py
        dispatch.py
        monitor.py
        integrate.py
        status.py
        standup.py
      config/
        models.py          # Pydantic models for agents.yaml, settings
        settings.py        # pydantic-settings for env vars
      agent/
        session.py         # libtmux session management
        dispatch.py        # Agent spawning logic
        recovery.py        # Crash detection and relaunch
      git/
        operations.py      # Clone, branch, merge operations (subprocess)
      discord/
        bot.py             # Strategist bot (discord.py)
        webhooks.py        # Webhook helpers
        channels.py        # Channel management
      hooks/
        ask_discord.py     # AskUserQuestion hook (standalone script)
        plan_gate.py       # Plan gate hook
      monitor/
        loop.py            # Main monitor loop
        liveness.py        # Agent liveness checking
        status_gen.py      # PROJECT-STATUS.md generation
  tests/
    ...
```

## Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
uv init vcompany
cd vcompany

# Core dependencies
uv add "discord.py>=2.7,<3" "anthropic>=0.86,<1" "click>=8.2,<9" \
       "libtmux>=0.55,<0.56" "PyYAML>=6.0,<7" "rich>=14.2,<15" \
       "pydantic>=2.11,<3" "pydantic-settings>=2.13,<3" \
       "httpx>=0.28,<1" "watchfiles>=0.24,<1"

# Dev dependencies
uv add --dev "pytest>=8" "pytest-asyncio>=0.24" "ruff>=0.9" "mypy>=1.14"
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| click | typer | If team prefers type-hint-based CLI definition. Typer wraps Click anyway, so switching later is easy. Click chosen because PROJECT.md already specifies it and it has more community examples for complex subcommand patterns like `vco agent dispatch`. |
| discord.py | nextcord, disnake | Never for this project. These are forks from when discord.py was temporarily abandoned (2021). discord.py is back and actively maintained. The forks fragment the ecosystem. |
| httpx | aiohttp | If you need raw async performance for high-throughput HTTP. Not needed here -- webhook calls are low-volume. httpx's dual sync/async API is more valuable for a project that mixes sync CLI and async bot code. |
| httpx | requests | Never. requests is sync-only. The Strategist bot needs async HTTP for webhook calls without blocking the event loop. |
| libtmux | subprocess tmux calls | If libtmux's pre-1.0 API instability becomes painful. Fallback is to shell out to `tmux` directly via subprocess. Less ergonomic but zero dependency risk. |
| watchfiles | watchdog | If you need Windows/macOS cross-platform support (we don't). watchfiles is faster and has native asyncio support, which matters for the monitor loop. |
| uv | pip + venv | If uv has bugs with a specific dependency. Extremely unlikely in 2026 -- uv is production-ready and the direction Python packaging is heading. |
| filesystem state | SQLite | If vCompany later needs queryable historical data (agent performance metrics, decision logs). Not needed for v1. |
| pydantic | dataclasses + manual validation | Never for config/external data. Pydantic's validation-on-construction catches config errors at startup instead of at runtime. Use dataclasses only for internal-only data structures. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| GitPython | In maintenance mode (no new features, slow bug fixes). Adds a heavy dependency for something subprocess handles fine. | `subprocess.run(["git", ...])` or `asyncio.create_subprocess_exec("git", ...)`. Git CLI is always available and more reliable. |
| nextcord / disnake | Dead-end forks of discord.py from 2021 abandonment era. discord.py is back and maintained. Using forks means fragmented community, fewer examples, slower updates. | discord.py 2.7.x |
| requests | Sync-only HTTP client. Blocks the asyncio event loop used by discord.py and the monitor. | httpx (supports both sync and async) |
| poetry | Slower dependency resolution, heavier tooling, Python-only resolver. uv is faster by orders of magnitude and handles everything poetry does. | uv |
| argparse | Verbose, no built-in command groups, requires manual help formatting. click provides all of this with decorators. | click |
| celery / dramatiq | Task queue overkill. vCompany runs on one machine, manages processes via tmux, and has a simple 60s monitor loop. No need for a message broker. | asyncio + libtmux + subprocess |
| SQLAlchemy / any ORM | No database. State lives in files. Adding a database adds migration complexity, another failure mode, and zero value for v1. | YAML files + Pydantic models |
| Flask / FastAPI | No web server needed. Discord is the UI. Webhook receiving (if needed) can be handled by discord.py's built-in HTTP server or a minimal httpx-based approach. | discord.py for all bot interaction |

## Stack Patterns by Variant

**If the Strategist bot needs streaming responses:**
- Use `anthropic.AsyncAnthropic` with `stream=True`
- discord.py supports editing messages in-place, so stream chunks can update a single Discord message
- This improves perceived responsiveness for long Strategist answers

**If libtmux API breaks on update:**
- Fall back to `subprocess.run(["tmux", "new-session", ...])` pattern
- Wrap in a thin abstraction layer from day one so the swap is painless
- Pin libtmux to exact minor version (0.55.x)

**If agent count exceeds ~10 concurrent:**
- Monitor loop may need to parallelize liveness checks with `asyncio.gather`
- tmux can handle many sessions but libtmux iteration may slow down
- Consider grouping agents into tmux windows rather than sessions

**If webhook volume hits Discord rate limits:**
- discord.py handles rate limiting internally for bot API calls
- For raw webhook POSTs (from ask_discord.py), implement exponential backoff in httpx
- PROJECT.md already notes this as "address when it bites" -- correct approach

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| discord.py 2.7.x | Python 3.9+ | Uses aiohttp internally; do not install a conflicting aiohttp version |
| anthropic 0.86.x | Python 3.9+ | Depends on httpx internally; compatible with our direct httpx usage |
| libtmux 0.55.x | tmux 2.6+ | We target tmux 3.4+ so no issues. Pin tightly -- API changes between minor versions. |
| pydantic 2.11.x | pydantic-settings 2.13.x | Must use pydantic v2, not v1. pydantic-settings is a separate package since pydantic v2. |
| click 8.2.x | Python 3.9+ | No known conflicts. |
| watchfiles 0.24.x | Python 3.9+ | Rust extension -- binary wheels available for Linux x86_64. |
| ruff 0.9.x | Python 3.9+ | Standalone Rust binary, no Python dependency conflicts. |

## Key Design Decisions

### Why No Database
vCompany's state is inherently file-based: agents.yaml, ROADMAP.md, PROJECT-STATUS.md, git logs, PLAN.md files. These are the same files agents read and the monitor parses. A database would duplicate state and create sync issues. If queryable history is needed later, append to a JSONL log file -- still no database.

### Why subprocess Over GitPython
Git operations in vCompany are: clone, checkout, branch, merge, log, diff, status. All are single CLI commands. subprocess is simpler, has zero dependencies, always matches the installed git version, and is trivially async-able. GitPython adds 15+ MB of dependency for no benefit and is in maintenance mode.

### Why click Over typer
PROJECT.md specifies click. click has 3x the adoption, more documentation, and is the foundation typer builds on. For a CLI with ~12 subcommands and relatively straightforward options, click's decorator model is cleaner than typer's function-signature model. If someone prefers typer, migration is mechanical since typer wraps click.

### Why httpx as the Single HTTP Client
The project has two HTTP contexts: sync (CLI commands posting to Discord webhooks) and async (bot/monitor making API calls). httpx handles both with the same API surface. Using requests + aiohttp would mean two libraries, two APIs, and two sets of error handling for the same thing.

### Why uv Over pip
In 2026, uv is the standard. 10-100x faster resolution, built-in venv management, lockfiles, and a single binary. Starting with uv avoids the inevitable migration later. pyproject.toml is the project config format regardless.

## Sources

- [discord.py PyPI](https://pypi.org/project/discord.py/) -- version 2.7.1 confirmed (HIGH confidence)
- [anthropic PyPI](https://pypi.org/project/anthropic/) -- version 0.86.0 confirmed (HIGH confidence)
- [click PyPI](https://pypi.org/project/click/) -- version 8.2.x confirmed (HIGH confidence)
- [libtmux GitHub releases](https://github.com/tmux-python/libtmux/releases) -- version 0.55.0, pre-1.0 API warning confirmed (HIGH confidence)
- [PyYAML PyPI](https://pypi.org/project/PyYAML/) -- version 6.0.3 confirmed (HIGH confidence)
- [Rich GitHub releases](https://github.com/Textualize/rich/releases) -- version 14.2.0 confirmed (HIGH confidence)
- [pydantic-settings PyPI](https://pypi.org/project/pydantic-settings/) -- version 2.13.1 confirmed (HIGH confidence)
- [uv documentation](https://docs.astral.sh/uv/) -- version ~0.9.x, production-ready (HIGH confidence)
- [GitPython GitHub](https://github.com/gitpython-developers/GitPython) -- maintenance mode confirmed (HIGH confidence)
- [httpx vs aiohttp comparison](https://www.speakeasy.com/blog/python-http-clients-requests-vs-httpx-vs-aiohttp) -- dual sync/async capability confirmed (MEDIUM confidence)

---
*Stack research for: Python CLI orchestrator + Discord bot for multi-agent Claude Code management*
*Researched: 2026-03-25*
