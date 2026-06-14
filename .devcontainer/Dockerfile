# Choose a base image with Python 3.11 and Node.js pre-installed, or start from Ubuntu and install both.
# Using the official Microsoft Python devcontainer image as a base.
FROM mcr.microsoft.com/vscode/devcontainers/python:3.11

# Install Node.js (via nvm) and other useful tools.
# Install nodejs LTS and npm
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends curl git ca-certificates \
    # Install nvm and Node.js LTS
    && mkdir -p /usr/local/share/nvm && chmod a+w /usr/local/share/nvm \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash \
    && . /usr/local/share/nvm/nvm.sh \
    && nvm install --lts \
    && nvm alias default lts/* \
    # Clean up
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Set environment variables for nvm
ENV NVM_DIR=/usr/local/share/nvm
ENV NODE_VERSION=lts/*
RUN echo \"source /usr/local/share/nvm/nvm.sh\" >> /etc/bash.bashrc && \
    echo \"source /usr/local/share/nvm/nvm.sh\" >> /etc/zsh/zshrc

# Install uv (Python installer) as recommended by the Hermes project.
# Install uv via pip (or via the official installer). Using pip for simplicity.
RUN pip install --no-cache-dir uv

# Set the working directory to /workspace (the default in VS Code devcontainers)
WORKDIR /workspace

# Optionally, you can pre‑fetch dependencies here if you want them baked into the image.
# For flexibility, we'll leave dependency installation to the postCreateCommand in devcontainer.json.