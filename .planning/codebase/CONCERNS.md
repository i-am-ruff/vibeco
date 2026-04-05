# Codebase Concerns

**Analysis Date:** 2026-04-05

## Dependency Declaration Drift

- `src/vcompany/cli/signal_cmd.py` imports `httpx`.
- `src/vcompany/daemon/daemon.py` also imports `httpx` for async health checking.
- `pyproject.toml` does not declare `httpx` in the root dependency list or dev group.

**Impact**
- Fresh installs or minimal containers can fail if `httpx` is not already present transitively.
- Runtime behavior depends on an undeclared dependency.

**Recommended direction**
- Add `httpx` explicitly to `pyproject.toml` if it is required in production/runtime paths.

## Build Supply Chain Risk

- `docker/Dockerfile` installs `uv` via `curl -LsSf https://astral.sh/uv/install.sh | sh`.

**Impact**
- The build trusts a remotely served installer script at image-build time.
- Reproducibility and integrity checking are weaker than a pinned artifact or verified checksum flow.

**Recommended direction**
- Pin or verify the installer, or replace the bootstrap step with a reviewed/pinned package acquisition path.

## Local-Path Assumption In File Transport

- `src/vcompany/daemon/comm.py` documents a TODO on `SendFilePayload`: it assumes the daemon can read a host `file_path`.

**Impact**
- Current file-send semantics are tightly coupled to co-located filesystem access.
- Remote/distributed worker deployments will need a different artifact transport model.

**Recommended direction**
- Move toward byte-stream, upload, or externally addressable artifact references instead of host-path-only semantics.

## High-Complexity Hotspots

Large files concentrate a lot of behavior:
- `src/vcompany/daemon/runtime_api.py` — 808 lines
- `src/vcompany/supervisor/company_root.py` — 712 lines
- `src/vcompany/daemon/daemon.py` — 630 lines
- `src/vcompany/bot/cogs/plan_review.py` — 632 lines
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` — 480 lines

**Impact**
- Changes in these files have wide blast radius.
- Review and test effort is higher because multiple responsibilities live in a small number of modules.

**Recommended direction**
- When extending these modules, carve out smaller seams instead of piling more policy and transport logic into the same files.

## Onboarding / Discoverability Gap

- `README.md` is empty.

**Impact**
- New contributors must reverse-engineer setup and architecture from `VCO-ARCHITECTURE.md`, `CLAUDE.md`, source files, and tests.
- Basic “how do I run this?” and “what are the main entrypoints?” guidance is missing at the repo root.

**Recommended direction**
- Add a short root README covering setup, primary commands, repo layout, and links to deeper docs.

## Secret Handling Concentration

- `.env` exists as a standard local config source for `src/vcompany/bot/config.py`.
- `.gitignore` ignores `.env`, which is correct, but the repo’s operational model still centers sensitive local credentials in a predictable location.

**Impact**
- Humans or agents can accidentally reference or expose secret-bearing local files during debugging or prompt-driven work if guardrails are weak.

**Recommended direction**
- Keep `.env` out of generated docs and prompts, maintain a safe `.env.example`, and treat any tooling that reads arbitrary local files as high risk around secrets.

## Codex / GSD Compatibility Risk In This Repo

- This repo carries both `.claude/get-shit-done/` and `.codex/` workflow assets.
- The Codex-side bridge relies on model mappings and role configs that can diverge from account-supported models and from upstream GSD assumptions.

**Impact**
- Workflow quality or execution can degrade silently when Codex role defaults, supported models, and upstream GSD model aliases do not match.
- Codebase mapping quality is especially sensitive because shallow reports are still formally “successful” unless someone checks the output.

**Recommended direction**
- Keep Codex-side model mappings, prompt translation rules, and account-supported model constraints aligned whenever GSD profiles change.
