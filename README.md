# Docker altRcode

**English** | [Français](README.fr.md)

## Description

A development agent (opencode or Claude Code) confined in an ephemeral Docker container.

This stack provides better privacy and security than an agent installed directly on the host machine.

- **One container per session**, a single active agent (`DEFAULT_AGENT=opencode|claude` in `.env`, or `AGENT=` at launch). No Docker socket, no keys in the image.
- **Host dispatcher** (`dispatcher/dispatcher.py`): 0600 unix socket, only runs the `make` targets declared in `[ops]` of the target project's config — anything else is structurally impossible.
- **Egress proxy** (`dispatcher/egress_proxy.py`, `DOMAIN_WHITELIST=1`): all of the container's HTTP(S) traffic goes through a domain whitelist (global + per project). HTTP 403 otherwise.
- **Pin checking** (`PIN_PROTECTION=1`): the project's authority files (Makefile, compose, `.env`) are hashed at startup, with no write access for the stack. If one of them changes during the session, every `make` operation is refused until the next launch.

```text
docker-altrcode/
├── bin/
│   ├── docker-altrcode         # session wrapper (dispatcher + container)
│   ├── opencode-session-ctl    # opencode session management (SQLite)
│   └── claude-session-ctl      # Claude Code session management (JSONL)
├── config/
│   ├── opencode-settings.jsonc
│   ├── claude-settings.json
│   ├── AGENTS.md               # global guide for the agents (English)
│   ├── AGENTS.fr.md            # French version, selected by USER_LANGUAGE=fr
│   └── CLAUDE.md               # bridge → AGENTS.md (Claude Code)
├── container/
│   ├── entrypoint.sh
│   └── altrcode-ctl            # dispatcher client (runs inside the container)
├── dispatcher/
│   ├── dispatcher.py           # host unix socket server
│   ├── egress_proxy.py         # HTTP/HTTPS proxy filtered by domain
│   └── projects/
│       └── xxxx.conf           # project config (ops, pins, domains)
├── examples/                   # templates to copy into the target project
│   ├── docker-altrcode.conf    # dispatcher config for the stack itself
│   ├── drupal.conf             # Drupal dispatcher config
│   ├── symfony.conf            # Symfony dispatcher config
│   ├── git-workflow.md         # .opencode/instructions/git-workflow.md template (English)
│   ├── git-workflow.fr.md      # French version of the same template
│   └── opencode.jsonc          # chrome-devtools MCP template for opencode
├── tools/
│   └── whisper-input           # push-to-talk speech-to-text daemon (host)
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── Makefile
```

### Security levels

| Level | Env | How it works |
|---|---|---|
| Dispatcher | *(always on)* | 0600 unix socket on the host. Only the `make` targets declared in `[ops]` of the project config can be run. |
| Domain whitelist | `DOMAIN_WHITELIST=1` | Egress proxy on the host. All HTTP(S) traffic filtered by domain (suffix match). HTTP 403 otherwise. |
| Pin checking | `PIN_PROTECTION=1` | Authority files hashed at startup. Stack operations (make commands) refused if a change is detected during the session. Pinned files are also mounted `:ro` in the container (individual overmounts on `/work`). |

The domain whitelist works on two levels: global domains (LLMs, tools, npm…) are declared in `DOMAIN_GLOBAL_WHITELIST` in `.env`; project-specific domains are in `[domains]` of `dispatcher/projects/xxxx.conf`. The proxy merges both lists.

### Pin-checked files

The files listed in `[pins]` of the project config are hashed at startup (`~/.cache/docker-altrcode/run/<project>/pins.json`) and mounted `:ro` in the container. They live on the host, in the project directory:

```text
<root>/                         # root = [project] root field of the config
├── Makefile                    # always pinned
├── docker-compose*.yml         # stack compose files
└── app/
    └── .env.*.local            # local environment variables
```

Each project's `root` path is defined in `dispatcher/projects/<name>.conf`.

### Host volumes

Data persisted by the agents is written on the host, outside the Docker image:

| Host path | Contents |
|---|---|
| `~/.config/docker-altrcode/` | Agent configs copied at startup (settings, AGENTS.md), project `.conf` files, Claude Code state (`claude/`: JSONL sessions, memory, cache) |
| `~/.local/state/docker-altrcode/` | opencode persistence: conversations (SQLite) |
| `~/.cache/docker-altrcode/` | opencode cache, runtime unix socket, dispatcher/egress logs, pins file |

### Agent configs

At the start of every session, `bin/docker-altrcode` copies the config files from the repository to `~/.config/docker-altrcode/` before starting the container.

| Source file (repository) | Copy mounted in the container |
|---|---|
| `config/opencode-settings.jsonc` | `~/.config/docker-altrcode/opencode/opencode.jsonc` |
| `config/AGENTS.md` or `config/AGENTS.<lang>.md` | `~/.config/docker-altrcode/opencode/AGENTS.md` |
| `config/CLAUDE.md` | `~/.config/docker-altrcode/claude/CLAUDE.md` |
| `config/claude-settings.json` | `~/.config/docker-altrcode/claude/settings.json` (after `envsubst`) |

The agent instructions follow `USER_LANGUAGE` from `.env`: `config/AGENTS.<lang>.md` is used when it exists (e.g. `AGENTS.fr.md` for `fr`), otherwise the English `config/AGENTS.md`. The copy is always named `AGENTS.md` in the container.

State volumes are mounted `:rw` (projects, backups, cache…). Instruction files (`AGENTS.md`, `CLAUDE.md`) are mounted `:ro` through individual overmounts — the agent can read them but not write them. The source repository (`config/`) is never mounted in the container. The copies are regenerated from the repository for every new session.

On the Claude Code side, the whole `~/.config/docker-altrcode/claude/` directory is mounted on `~/.claude` and shared across projects and instances: login, conversations (`projects/-work/<id>.jsonl`, resumed with `/resume`), auto memory, prompt history. Only `~/.claude/sessions/` (the registry of running Claude processes, one `<pid>.json` per instance) is a `tmpfs` specific to each container: two parallel instances have the same pid and would overwrite each other there. This registry is emptied on shutdown, with no effect on `/resume`.

On the opencode side, the state (`~/.config`, `~/.local/share`, `~/.local/state`, `~/.cache`) is also shared across projects and instances. Sessions still stay separated per project: opencode identifies a project by its git repository, not by its path. The opencode background service is disabled (`"disabled": true` in `~/.config/opencode/service.json`) because its shared files would overwrite each other between parallel instances; each instance uses its own server, with its container's proxy.

## Installation

1. Prerequisites: `docker`, `docker compose`, `python3`, `envsubst` on the host.

2. Copy and fill in `.env`:
   ```bash
   cp .env.example .env
   ```

3. Create the target project config in `dispatcher/projects/xxxx.conf`: adjust `root`, `container`, and optionally `[ops]`, `[pins]`, `[domains]`, `[extra_dirs]`. Templates are available in `examples/`.

4. Build the image:
   ```bash
   make build
   ```

5. Start a session:
   ```bash
   make up                              # project and agent from DEFAULT_PROJECT / DEFAULT_AGENT in .env
   make up PROJECT=xxxx AGENT=opencode  # explicit project and agent
   ```

## Usage

**Start a session:**
```bash
make up                              # project and agent from DEFAULT_PROJECT / DEFAULT_AGENT in .env
make up PROJECT=xxxx AGENT=opencode  # explicit project and agent
```

`PROJECT=` and `AGENT=` override the `DEFAULT_PROJECT` and `DEFAULT_AGENT` variables of `.env` for the current command only. Each one can be given alone (`make up AGENT=opencode`). This applies to every command that accepts them.

**Container status:**
```bash
make ps
```

**Headless Chrome browser (CDP):**
```bash
make chrome-up    # start Chrome (host network, CDP port 9222)
make chrome-down  # stop
```
The container uses `network_mode: host` — it shares the host's network, including its `/etc/hosts`. Local stacks are therefore reachable by their domain as soon as they run. Chrome is available to projects that have a `.mcp.json` configuring the `chrome-devtools` MCP server.

## Maintenance

**Session management:**
```bash
make session-list                                    # sessions of DEFAULT_AGENT
make session-list AGENT=opencode                     # sessions of an explicit agent
make session-clean                                   # all sessions of DEFAULT_AGENT
make session-clean AGENT=opencode                    # all sessions of an explicit agent
make session-clean arg=<session-id>                  # one session of DEFAULT_AGENT
make session-clean AGENT=opencode arg=<session-id>   # one session of an explicit agent
```

With `AGENT=claude`, `session-clean` deletes the transcript (`projects/<project>/<id>.jsonl`, what `/resume` reads), its artifacts, `file-history/<id>`, `session-env/<id>` and the `history.jsonl` entries (backed up as `.backup-<date>` before being modified). Auto memory (`projects/<project>/memory/`) is kept.

**Exploring a container:**

```bash
make ps                             # find the agent container name: docker-altrcode_agents-run-<id>
make exec arg=82b3aef27e7a          # agent container docker-altrcode_agents-run-82b3aef27e7a
make exec arg=chrome                # container docker-altrcode_chrome
```

`<id>` is the suffix of the name shown by `make ps` (12 hexadecimal characters), not to be confused with the CONTAINER ID column.

**Updating:**

Auto-update is disabled in both agents (`env.DISABLE_AUTOUPDATER=1` in `claude-settings.json` for Claude Code, `update: disable` for opencode) — they do not update themselves from within the container. To update them:

```bash
make build            # always reinstalls the agents (latest versions), the rest of the image stays cached
make build NOCACHE=1  # full rebuild, including the latest node:24-slim base image
```

`NOCACHE=1` is only useful from time to time, for system updates of the image. A change to `docker-compose.yml` does not require a rebuild: it is read again on every `make up`.

Host volumes (conversations, sessions, memory) are not affected by a rebuild.

**Uninstalling:**

```bash
make down
bash tools/clean-host.sh
```

`make down` stops and removes the running agent containers (all projects) and the stack network. It does not touch any data on the host: configurations, Claude login, sessions and memory are kept.

`tools/clean-host.sh` removes all data left by the stack on the host machine (configurations, sessions, agent memory, cache, opencode database).

The script shows the size of each affected directory and asks for confirmation before deleting. The cleaned directories are `~/.config/docker-altrcode`, `~/.local/state/docker-altrcode` and `~/.cache/docker-altrcode` (XDG paths honored when set).

> Docker images are not removed by this script. To remove them as well:
> ```bash
> docker rmi agents_docker-altrcode zenika/alpine-chrome:latest
> ```

## Target project layout

Target projects follow a native opencode/Claude Code convention. The stack first reads its own instructions from `config/AGENTS.md`, then looks for the project's own instructions to complement them with each project's specifics in an optimized way, following the `Hierarchical context` / `Lazy context loading` principle.

```text
<project>/
├── Makefile                       # make entry point (push, tests, stack…)
├── AGENTS.md                      # single source — short, indexes the sub-files
├── CLAUDE.md                      # one-line bridge: @AGENTS.md
└── .opencode/
    └── instructions/              # per-topic sub-files, loaded on demand
        ├── stack.md               # start, test, deploy
        ├── git-workflow.md        # branches, commits, workflow
        └── <topic>.md             # business rules (free name)
```

- **`AGENTS.md`**: auto-loaded by opencode, imported by Claude Code through `CLAUDE.md`. Contains a short project description and an index (a `when you work on X, read <path>` table) with explicit relative paths to the sub-files.
- **`CLAUDE.md`**: a single line — `@AGENTS.md`. Nothing else.
- **`.opencode/instructions/*.md`**: one file per topic, loaded on demand depending on the task — not systematically injected into the context.

Ready-to-use templates are available in `examples/`: dispatcher configs (`drupal.conf`, `symfony.conf`, `docker-altrcode.conf`), `git-workflow.md` (English) or `git-workflow.fr.md` (French) to copy as `.opencode/instructions/git-workflow.md`, `.mcp.json` and `opencode.jsonc` for the chrome-devtools MCP.

### Git workflow

The project's git policy (branches, commit conventions, workflow) should be described in the target project's `.opencode/instructions/git-workflow.md` file, which the agent loads when it works on git.

`git add` and `git commit` are run by the git bundled in the container. `git push`, however, needs the host's SSH keys — it goes through the dispatcher via a `make git-push` target of the project:

```makefile
## git-push         :     Push current branch (git push origin <arg> or current branch).
.PHONY: git-push
git-push:
	git push origin $(if $(arg),$(arg),$(shell git rev-parse --abbrev-ref HEAD))
```

To be declared in the project config to allow git push:

```ini
[ops]
git-push = 1
```

The agent calls `altrcode-ctl git-push` (current branch) or `altrcode-ctl git-push my-branch`.

### Per-project skills

```text
<project>/
└── .claude/
    └── skills/
        └── <id>/                  # id = directory name
            ├── SKILL.md           # frontmatter: name + description (required)
            └── ...                # scripts, references, etc.
```

- `.claude/skills/` is read natively by Claude Code and by opencode (compatibility source) — a single directory for both agents.
- A skill without a `description` in its frontmatter is not announced to the agent.
- A project skill overrides a global (stack-level) skill with the same id.

### Per-project MCP

Each agent reads its own MCP config file — different formats, no shared file.

```text
<project>/
├── .mcp.json              # Claude Code MCP → { "mcpServers": { "<name>": { ... } } }
└── opencode.jsonc         # opencode MCP    → { "mcp": { "<name>": { ... } } }
```

- **`.mcp.json`**: can be versioned, shared with the team. Approved interactively at the first session. A template is available in `examples/.mcp.json`.
- **`opencode.jsonc`**: opencode project config, `mcp` section. A template is available in `examples/opencode.jsonc`.
- Adding servers through the CLI (`claude mcp add`, `opencode mcp add`) is set to `ask` mode in both stack configs.

### Extra directories

A project may need access to several related repositories (docker stack + ansible, terraform…). The `[extra_dirs]` section of the config mounts extra directories in the container:

```ini
[extra_dirs]
/home/mike/Documents/Projets/xxxx-ansible   = /work-ansible
/home/mike/Documents/Projets/xxxx-terraform = /work-terraform
```

Each entry is mounted `:rw` next to `/work`. With Claude Code, `/add-dir /work-ansible` loads the second repository into the session context. With opencode, the agent accesses the files when explicitly asked to (the available directories are announced in `config/AGENTS.md`).

The section can be omitted — no extra volume is mounted then.

> **Limits**: extra dirs are mounted `:rw` with neither pin checking nor `:ro` overmounts. The dispatcher only runs `make` commands from `root` (the main repository) — extra dirs are freely readable and writable.

## Speech-to-text

`tools/whisper-input` is a push-to-talk daemon running on the host. The daemon runs in the background with the model loaded in memory; the `begin`/`end` (or `toggle`) commands are sent to it over a unix socket from WM/DE shortcuts. The text is typed into the active window — it works in opencode as well as in Claude Code, without any Docker change. Compatible with X11 and Wayland.

### Prerequisites

- NVIDIA GPU with **CUDA** (drivers + CUDA toolkit). Check with: `nvidia-smi`
- `python3`, `arecord` (`alsa-utils` package) — installed by default on Ubuntu
- A typing tool matching the display server:
  - **X11** (Ubuntu 24 and earlier): `sudo apt install xdotool`
  - **Wayland** (Ubuntu 26+): `sudo apt install wtype`

### Installation

```bash
mkdir -p ~/.local/bin ~/.local/share/whisper-input
python3 -m venv ~/.local/share/whisper-input/venv
~/.local/share/whisper-input/venv/bin/pip install faster-whisper "av==13.0.0"
cp tools/whisper-input ~/.local/bin/whisper-input # custom patch to type the text into the active window
chmod +x ~/.local/bin/whisper-input
```

> If the GPU is not detected on the first launch, force the CUDA 12 backend:
> ```bash
> ~/.local/share/whisper-input/venv/bin/pip install ctranslate2 --extra-index-url https://pypi.nvidia.com
> ```

### Configuration (~/.bashrc on the host)

Add to `~/.bashrc`:

```bash
# whisper-input (speech-to-text push-to-talk)
export WHISPER_MODEL=large-v3
export WHISPER_LANG=en
alias whisper='whisper-input daemon > /dev/null 2>&1 &'
alias whisper-stop='whisper-input stop'
```

Then reload: `source ~/.bashrc`

### Keyboard shortcut (WM/DE)

The daemon does not capture any key itself — bind `begin`/`end` (or `toggle`) in your window manager:

**GNOME** (Settings → Keyboard → Custom Shortcuts) — toggle mode (one press starts, the next one stops):
```text
whisper-input toggle   →   F9
```

**i3 / sway** (`~/.config/i3/config`) — true push-to-talk (press/release):
```text
bindsym F9         exec --no-startup-id whisper-input begin
bindsym --release F9 exec --no-startup-id whisper-input end
```

### Starting

```bash
whisper
```

On first start, the model (~3 GB) is downloaded from Hugging Face. It is cached in:

```text
~/.cache/huggingface/hub/blobs/          ← model binary (2.9 GB)
~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3/   ← config, tokenizer (~3 MB)
```

Subsequent starts are immediate (loaded from the local cache).

### Stopping

```bash
whisper-stop
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | Model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `WHISPER_LANG` | `en` | Transcription language |

## About

### FAQ

**Does my target project need a Makefile for stack commands to work?**

Yes, if you want to use the dispatcher. Each operation declared in `[ops]` of the project config maps to a `make` target of the target project. The dispatcher runs `make <op>` in the project's `root` directory — without a Makefile, there is nothing to run. If your project has no Makefile (static project, config repository…), simply leave `[ops]` empty or omit it: the agent can freely read and write files, only running stack commands is impossible.

**Should I use `make start` or `make up`?**

They are the same: `start` is an alias of `up`, both targets run exactly the same command.

**Can I run two docker-altrcode instances in parallel on two different projects?**

Yes. Each `make up PROJECT=xxxx` starts an independent Docker container, with its own dispatcher socket and its own egress proxy. Both sessions coexist without interfering. Agent state, however, is shared (login, conversations, memory) — Claude Code handles concurrent access, and the registry of running processes is isolated per container (`tmpfs`). The other shared resource is headless Chrome if you use it (`make chrome-up`) — it runs on a single port and both agents access it concurrently, with no isolation between sessions.

**Can I run two docker-altrcode instances in parallel on the same project?**

No. The dispatcher, the egress proxy and the socket are stored per project (`~/.cache/docker-altrcode/run/<project>/`): a second instance would cut off the first one's, which would lose `altrcode-ctl` (and network access if the whitelist is active). The launcher therefore refuses to start if an instance of the same project is already running (`run/<project>/owner.pid`). If the previous launcher died (crash, closed terminal), the file is ignored and its orphan processes are cleaned up as usual.

Even without this limit, two agents in the same working copy would write to the same files and the same git index, and would drive the same project stack. To have two agents work in parallel on the same repository, clone the repository a second time and declare it as another project (for example `dispatcher/projects/<project>-2.conf` with `root` pointing to the clone) — keeping in mind that both clones share the project stack's containers if they start it.

**Can I run docker-altrcode on itself as the target project?**

Yes, a template is provided in `examples/docker-altrcode.conf`. The agent can read and modify the repository files. However, without declared `[ops]` targets (or with only `git-push`), it can neither restart the stack nor build the image — which is intentional: changes take effect at the next `make start`/`make up` run by hand.

**Why don't I see the models configured in my `.env` in opencode?**

If `OPENCODE_MODELS_WHITELIST=1`, the startup script generates an opencode config that disables the built-in provider and registers a custom provider with only the models declared in `OPENCODE_MODELS`. These models do not appear under a "Scaleway" section in `/models` but under "Recents" after their first use — this is an opencode limitation for custom providers. If you don't see them anywhere, disable the whitelist (`OPENCODE_MODELS_WHITELIST=0`), select each model once, then enable it again: they will then always appear in "Recents".

**Why does whisper-input use a patch?**

The `tools/whisper-input` script is a modified version of the upstream daemon. The change concerns how the transcribed text is typed: the original script does not support every display environment (X11 and Wayland), and its default behavior does not match the use case here (typing into the terminal's active window rather than a form field). The patch is minimal and documented in the script itself.

**When should I use Claude Code rather than opencode, and vice versa?**

Claude Code (Anthropic) uses Claude models — among the most capable on the market to date. With a Claude Max subscription, the cost is flat and unlimited, which makes it the most economical option for heavy use. It is the natural choice if raw performance is the priority.

opencode lets you use open-weight models hosted by a third-party provider, such as Scaleway. These models are produced by labs independent from Anthropic, their training and weights are public, and data processing depends only on the contract with the chosen provider. Scaleway is a European host subject to the GDPR, which can be decisive for projects where code or data confidentiality is a hard constraint. The trade-off is pay-per-use pricing (tokens) and models that generally perform worse than Claude on complex tasks.

**Which agent versions has the project been tested with?**

Claude Code 2.1.314 and opencode 2.2.5 (October 2026). The image installs the latest version published on npm at `make build` time; since auto-update is disabled in the container, the version stays fixed until the next rebuild.

**Does the docker-altrcode stack respect my data? Does it send usage data to its developer?**

docker-altrcode is a set of scripts and configuration files that run entirely on your machine. There is no telemetry, no central server, no network call initiated by the stack itself. The only outgoing traffic is the agent's requests to the LLM provider you configured (Anthropic or Scaleway depending on the chosen agent), filtered by your domain whitelist if `DOMAIN_WHITELIST=1`. The stack collects nothing and sends nothing to its developer.

**Can I use or modify docker-altrcode for free?**

Yes, without restriction. docker-altrcode is released under the **MIT** license: you can use, modify, redistribute it and include it in commercial projects, for free and without asking for permission. The only obligation is to keep the original license notice. See the `LICENSE` file at the root of the repository.

### References

- [Confused Deputy: The Old Bug That AI Agents Keep Reintroducing](https://auth0.com/blog/confused-deputy-the-old-bug-that-ai-agents-keep-reintroducing) — rationale for the dispatcher: running make without passing on the agent's secrets (Auth0, Sept. 2026)
- [Policy Versus Physics: Docker Sandboxing for My AI SRE Agent](https://hackernoon.com/policy-versus-physics-docker-sandboxing-for-my-ai-sre-agent) — rationale for the egress proxy: why an OS-level network filter rather than a prompt rule (HackerNoon, July 2026)
- [Choose a sandbox environment — Claude Code](https://code.claude.com/docs/en/sandbox-environments) — Docker/container/VM comparison for isolating Claude Code agents
- [Memory — Claude Code](https://code.claude.com/docs/en/memory) — AGENTS.md, hierarchical context loading (CLAUDE.md, skills, index)
- [HTTP CONNECT tunneling](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/CONNECT) — how the HTTPS egress proxy works (TCP tunnel without MITM)
- [opencode docs](https://opencode.ai/docs) — AGENTS.md, providers, skills, permissions
- [Claude Code docs](https://code.claude.com/docs) — hooks, MCP, permissions, settings
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech-to-text transcription engine (CTranslate2 reimplementation of Whisper)
