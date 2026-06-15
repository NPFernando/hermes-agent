# Hermes Agent development container.
# Keep this image intentionally small; language/tool versions that developers
# need in-editor are configured in devcontainer.json features.
FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Install uv from the official image so dependency resolution matches the
# documented local workflow without relying on pip bootstrapping.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /workspaces/hermes-agent
