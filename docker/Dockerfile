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

# Default Claude settings baked into image (D-09)
# Container writable layer preserves modifications across stop/start
RUN mkdir -p /root/.claude
COPY settings.json /root/.claude/settings.json

# Working directory mounted at runtime via -v host_clone:/workspace
WORKDIR /workspace

# Keep container alive for exec-based interaction
# tmux server started by DockerTransport.setup() via docker exec
CMD ["sleep", "infinity"]
