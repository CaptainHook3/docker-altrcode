#!/bin/sh
# docker-altrcode entrypoint: runs opencode or claude under the host UID/GID.
set -eu

HOME_DIR="/home/dev"
export HOME="$HOME_DIR"

# Git identity injected from .env.
if [ -n "${GIT_NAME:-}" ]; then
    git config --global user.name "$GIT_NAME"
fi
if [ -n "${GIT_EMAIL:-}" ]; then
    git config --global user.email "$GIT_EMAIL"
fi

# Egress proxy: DOCKER_ALTRCODE_PROXY is set by the wrapper when DOMAIN_WHITELIST=1.
if [ -n "${DOCKER_ALTRCODE_PROXY:-}" ]; then
    export HTTP_PROXY="$DOCKER_ALTRCODE_PROXY"
    export HTTPS_PROXY="$DOCKER_ALTRCODE_PROXY"
    export ALL_PROXY="$DOCKER_ALTRCODE_PROXY"
    export http_proxy="$DOCKER_ALTRCODE_PROXY"
    export https_proxy="$DOCKER_ALTRCODE_PROXY"
    export all_proxy="$DOCKER_ALTRCODE_PROXY"
    # NO_PROXY: loopback + Docker host (Chrome CDP on host.docker.internal:9222).
    export NO_PROXY="localhost,127.0.0.1,::1,host.docker.internal,${HOST_DOCKER_INTERNAL:-172.17.0.1}"
    export no_proxy="localhost,127.0.0.1,::1,host.docker.internal,${HOST_DOCKER_INTERNAL:-172.17.0.1}"
    export NODE_USE_ENV_PROXY=1   # Node 24: route fetch through the proxy
    echo "[docker-altrcode] egress proxy active: $DOCKER_ALTRCODE_PROXY"
    # opencode: background service disabled (service.json, see bin/docker-altrcode);
    # its private server inherits these variables, nothing to propagate.
else
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy \
          NODE_USE_ENV_PROXY
    export NO_PROXY="localhost,127.0.0.1,::1,host.docker.internal,${HOST_DOCKER_INTERNAL:-172.17.0.1}"
    export no_proxy="localhost,127.0.0.1,::1,host.docker.internal,${HOST_DOCKER_INTERNAL:-172.17.0.1}"
fi

# Agent: DEFAULT_AGENT (opencode|claude), set by the wrapper to the session's agent.
DEFAULT_AGENT="${DEFAULT_AGENT:-opencode}"
case "$DEFAULT_AGENT" in
    opencode|claude) ;;
    *) echo "[docker-altrcode] unknown DEFAULT_AGENT: '$DEFAULT_AGENT' (expected: opencode|claude)" >&2; exit 1 ;;
esac

# Claude: CLAUDE_DEFAULT_MODEL -> ANTHROPIC_DEFAULT_MODEL (startup model).
if [ "$DEFAULT_AGENT" = "claude" ] && [ -n "${CLAUDE_DEFAULT_MODEL:-}" ]; then
    export ANTHROPIC_DEFAULT_MODEL="$CLAUDE_DEFAULT_MODEL"
    echo "[docker-altrcode] claude: default model = $CLAUDE_DEFAULT_MODEL"
fi

exec "$DEFAULT_AGENT" "$@"
