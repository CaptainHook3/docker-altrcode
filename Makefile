-include .env

PROJECT        ?= $(DEFAULT_PROJECT)
AGENT          ?=
PROJECT_NAME    = docker-altrcode
COMPOSE         = docker compose -f docker-compose.yml
BIN             = bin/docker-altrcode
SESSION_CTL        = bin/opencode-session-ctl
CLAUDE_SESSION_CTL = bin/claude-session-ctl
EFFECTIVE_AGENT = $(or $(AGENT),$(DEFAULT_AGENT),opencode)

# Defaults for docker-compose (the wrapper overrides them at run time).
export PROJECT_DIR            ?= $(CURDIR)
export DOCKER_ALTRCODE_CONF   ?= $(HOME)/.config/docker-altrcode
export DOCKER_ALTRCODE_STATE  ?= $(HOME)/.local/state/docker-altrcode
export DOCKER_ALTRCODE_CACHE  ?= $(HOME)/.cache/docker-altrcode
export DOCKER_ALTRCODE_OPENCODE_CONF  ?= $(DOCKER_ALTRCODE_CONF)/opencode
export DOCKER_ALTRCODE_OPENCODE_SHARE ?= $(DOCKER_ALTRCODE_STATE)/share/opencode
export DOCKER_ALTRCODE_OPENCODE_STATE ?= $(DOCKER_ALTRCODE_STATE)/state/opencode
export DOCKER_ALTRCODE_OPENCODE_CACHE ?= $(DOCKER_ALTRCODE_CACHE)/opencode
export DOCKER_ALTRCODE_CLAUDE_CONF    ?= $(DOCKER_ALTRCODE_CONF)/claude
export DOCKER_ALTRCODE_CTL_SOCKET ?= $(DOCKER_ALTRCODE_CACHE)/run/altrcode/ctl.sock
export HOST_UID ?= $(shell id -u)
export HOST_GID ?= $(shell id -g)

.DEFAULT_GOAL := help

## Available targets:   make <target> [PROJECT=name] [AGENT=opencode|claude] [arg="..."]

## help         :     Show this help.
.PHONY: help
help: Makefile
	@sed -n 's/^##//p' $<

## build        :     Build the Docker image (host UID/GID injected).
##                    Example: make build              → agents updated, other layers cached
##                    Example: make build NOCACHE=1    → full rebuild, latest base image included
.PHONY: build
build:
	$(COMPOSE) build $(if $(NOCACHE),--no-cache --pull) \
		--build-arg AGENTS_REFRESH=$(shell date +%s) \
		--build-arg HOST_UID=$(shell id -u) --build-arg HOST_GID=$(shell id -g)

## up / start   :     Start an interactive agent session.
##                    Example: make up PROJECT=xxxx AGENT=claude
.PHONY: up start
up start:
	@test -n "$(PROJECT)" || { echo "error: DEFAULT_PROJECT missing from .env" >&2; exit 1; }
	bash $(BIN) $(PROJECT) $(AGENT)

## down         :     Stop and remove the running containers.
##                    Example: make down
.PHONY: down
down:
	$(COMPOSE) down -v --remove-orphans

## exec         :     Open a shell (bash, else sh) in a stack container.
##                    Example: make exec arg=chrome        → container docker-altrcode_chrome
##                    Example: make exec arg=82b3aef27e7a  → container docker-altrcode_agents-run-82b3aef27e7a
.PHONY: exec
exec:
	@if echo "$(arg)" | grep -Eq '^[0-9a-f]{12}$$'; then \
	    name="$(PROJECT_NAME)_agents-run-$(arg)"; \
	else \
	    name="$(PROJECT_NAME)_$(arg)"; \
	fi; \
	docker exec -ti "$$name" sh -c 'command -v bash >/dev/null && exec bash || exec sh'

## ps           :     Show container status.
##                    Example: make ps
.PHONY: ps
ps:
	docker ps

## git-push         :     Push current branch (git push origin <arg> or current branch).
.PHONY: git-push
git-push:
	git push origin $(if $(arg),$(arg),$(shell git rev-parse --abbrev-ref HEAD))

## chrome-up    :     Start the headless Chrome container (CDP port 9222).
##                    Example: make chrome-up
.PHONY: chrome-up
chrome-up:
	$(COMPOSE) --profile chrome up -d chrome

## chrome-down  :     Stop the headless Chrome container.
##                    Example: make chrome-down
.PHONY: chrome-down
chrome-down:
	$(COMPOSE) stop chrome

## session-list  :     List opencode or claude sessions.
##                    Example: make session-list AGENT=claude
.PHONY: session-list
session-list:
ifeq ($(EFFECTIVE_AGENT),claude)
	python3 $(CLAUDE_SESSION_CTL) list
else
	python3 $(SESSION_CTL) list
endif

## session-clean :     Delete sessions (all if arg is omitted, otherwise one by id).
##                    Example: make session-clean AGENT=opencode arg=<session-id>
.PHONY: session-clean
session-clean:
ifeq ($(EFFECTIVE_AGENT),claude)
	python3 $(CLAUDE_SESSION_CTL) clean $(or $(arg),$(firstword $(filter-out session-clean,$(MAKECMDGOALS))))
else
	python3 $(SESSION_CTL) clean $(or $(arg),$(firstword $(filter-out session-clean,$(MAKECMDGOALS))))
endif

# Swallow an optional positional argument (e.g. make session-clean <id>).
%:
	@:
