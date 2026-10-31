# docker-altrcode — single image: opencode + Claude Code + git + altrcode-ctl.
# One agent per session (DEFAULT_AGENT). No docker CLI, no Docker socket.
FROM node:24-slim

# git: opencode snapshots + local operations. python3: altrcode-ctl client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        python3 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Both npm agents — DEFAULT_AGENT (or AGENT= at launch) decides which one runs.
# AGENTS_REFRESH changes on every `make build`: this step is always re-run (latest
# agent versions) while the layers above stay cached.
ARG AGENTS_REFRESH=0
RUN npm install -g @opencode/cli @anthropic-ai/claude-code

# Dispatcher client (only channel to the host).
COPY container/altrcode-ctl /usr/local/bin/altrcode-ctl
RUN chmod +x /usr/local/bin/altrcode-ctl

COPY container/entrypoint.sh /usr/local/bin/docker-altrcode-entrypoint
RUN chmod +x /usr/local/bin/docker-altrcode-entrypoint

WORKDIR /work

# dev user created at build time with the host UID/GID (useradd fails at runtime).
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupadd -o -g ${HOST_GID} dev \
    && useradd -o -u ${HOST_UID} -g ${HOST_GID} -m -d /home/dev -s /bin/bash dev

# GIT_NAME/GIT_EMAIL injected via .env; git config applied in the entrypoint.
ENV GIT_NAME="" GIT_EMAIL=""

ENTRYPOINT ["/usr/local/bin/docker-altrcode-entrypoint"]
