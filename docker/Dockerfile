# vCompany Claude Code agent image
# Base: node:22-slim (D-01) with Python 3.12, git, tmux, uv
# One universal image for all agent types (D-03)
FROM node:22-slim

# System dependencies: Python 3.12, git, tmux, curl (for uv installer)
# Single RUN to minimize layers; clean apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    git tmux curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Claude Code globally (D-02)
RUN npm install -g @anthropic-ai/claude-code

# Apply tweakcc patches at build time (D-02) -- deterministic, no runtime surprises
RUN npx tweakcc --apply

# Install vcompany (vco CLI) so agents can use vco signal/report/send-file/ask
# Build context is repo root — Dockerfile is at docker/Dockerfile
COPY pyproject.toml /opt/vcompany/pyproject.toml
COPY src/ /opt/vcompany/src/
RUN cd /opt/vcompany && uv pip install --system -e .

# Install vco-worker package (Phase 30) for channel protocol communication
COPY packages/vco-worker/ /opt/vco-worker/
RUN cd /opt/vco-worker && uv pip install --system -e .

# Default Claude settings baked into image (D-09)
# Container writable layer preserves modifications across stop/start
RUN mkdir -p /root/.claude
COPY docker/settings.json /root/.claude/settings.json

# Working directory mounted at runtime via -v host_clone:/workspace
WORKDIR /workspace

# Default entrypoint: vco-worker reads from stdin, writes to stdout
# DockerChannelTransport pipes channel protocol via docker run -i
CMD ["python", "-m", "vco_worker"]
