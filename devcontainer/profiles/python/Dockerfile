# vibe language profile: python (task_040)
#
# Thin child image built FROM the vibe base (vibe-dev:latest by default) that
# adds a Python toolchain: python3 + venv/pip via apt, then uv (astral.sh)
# installed for user `node`, then `uv tool install ruff` / `uv tool install
# mypy` on top of it. Built by `vibe --profile python` (or the `.vibe/profile`
# / VIBE_PROFILE persistent selectors) — see README.md's "Language profiles"
# section for the full mechanism. Toolchain only, never project deps.
#
# Adds roughly 200-250 MB on top of the base image (apt's python3 stack plus
# uv's own small binary and the two tool venvs it manages).
#
# Everything below runs at BUILD time, so no init-firewall.sh entry is
# needed: by the time a container starts and the firewall comes up, the
# toolchain is already baked into the image layer — no runtime network
# access to astral.sh/pypi.org is required.
ARG BASE=vibe-dev:latest
FROM ${BASE}

USER root

# One RUN: apt needs root (the base image only grants node passwordless sudo
# for init-firewall.sh and avahi-daemon, not apt-get), so the apt-get install
# runs as root and the uv install + `uv tool install` calls run as user node
# (via `su - node -c '...'`, a login shell so $HOME resolves to /home/node)
# — all inside the SAME layer, keeping this a single RUN per the profile
# Dockerfile convention (one toolchain layer, never a project-deps layer).
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-venv \
      python3-pip \
      curl \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && su - node -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' \
    && su - node -c '$HOME/.local/bin/uv tool install ruff' \
    && su - node -c '$HOME/.local/bin/uv tool install mypy'

# uv's installer and `uv tool install` both land in ~/.local/bin, which the
# base image never puts on PATH (its only PATH extension is npm-global/bin).
ENV PATH="/home/node/.local/bin:${PATH}"

USER node
