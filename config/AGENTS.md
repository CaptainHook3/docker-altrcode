# docker-altrcode environment

## 1 — Never run make / docker directly

`make`, `docker` and `docker-compose` do not exist in this container.
Every stack operation goes through **`altrcode-ctl`** (unix socket → host dispatcher → Makefile).

Systematic translation — drop `make ` and pass the target to `altrcode-ctl`:

| Request                              | Command                               |
|--------------------------------------|---------------------------------------|
| start / make up / make start         | `altrcode-ctl up` or `altrcode-ctl start` |
| stop / make down / make stop         | `altrcode-ctl down` or `altrcode-ctl stop` |
| tests / make test                    | `altrcode-ctl test`                   |
| logs / make logs                     | `altrcode-ctl logs`                   |
| status / make ps                     | `altrcode-ctl ps`                     |
| console cache:clear                  | `altrcode-ctl console cache:clear`    |

- Read `/work/Makefile` to find the project's available targets.
- Targets that take an argument accept only ONE argument, with no shell metacharacters (no `;`, `|`, `$`, quotes).

## 2 — Pinned files

If `PIN_PROTECTION=1`, the project's authority files (Makefile, compose, `.env`) are hashed at startup. Any change during the session makes the dispatcher **refuse every `altrcode-ctl` operation**.

- Never modify these files — they are not meant for you.
- On the first refusal: warn the user, do not insist. Re-pinning is done by restarting the stack from the host.

## 3 — Git

Local only: `status`, `diff`, `log`, `add`, `commit`. The container has neither an SSH client nor credentials — `git push` always fails.

**To push, always use `altrcode-ctl git-push` (not `git push`).** This target is defined in the project's Makefile and runs on the host with its SSH credentials. If the project declares it with an argument (`git-push = 1`), you can pass a branch: `altrcode-ctl git-push my-branch`. Without an argument, it pushes the current branch.

## 4 — Remote skills

**Ask the user for confirmation before adding a remote skill.**

```bash
npx skills add <owner>/<repo>/<skill-id>    # installs into .claude/skills/
```

Local skills (`.claude/skills/`) are loaded automatically, with no command. Never add a remote skill without explicit approval — it changes the session environment.

## 5 — MCP servers

**Ask the user for confirmation before adding an MCP server.**

If you are **opencode**:
```bash
opencode mcp add    # interactive prompt: type, name, URL
```

If you are **Claude Code**:
```bash
claude mcp add <name> <command>
```

MCP servers extend your reach beyond the dispatcher — always check with the user.

## 6 — Chrome browser (chrome-devtools MCP)

If the user started the Chrome container (`make chrome-up` from the docker-altrcode stack), the **`chrome-devtools`** MCP is available in projects whose `.mcp.json` declares it. It drives a headless Chrome over CDP (Chrome DevTools Protocol).

**Available capabilities:**
- Navigating and loading pages
- Screenshots
- Inspecting and manipulating the DOM
- Running JavaScript in the page
- Network monitoring (requests, responses, headers)
- Lighthouse audits (performance, accessibility, SEO, best practices)

**Usage:**
- The MCP loads automatically if `.mcp.json` declares it — check with `/mcp` when in doubt.
- Chrome runs with `network_mode: host`: it sees the same `/etc/hosts` entries as the host, so local stacks are reachable by their domain as soon as they run.
- **You do not start/stop Chrome yourself** — the user manages it from the host.
- If the MCP does not respond or `list_pages` fails: Chrome is probably not running. Tell the user (`make chrome-up` from docker-altrcode).

## 7 — Web search

Use the native web search tool: `WebSearch` for Claude Code, `websearch` (Tavily / TinyFish) for opencode. Avoid `webfetch` directly on a search engine — Google returns a captcha to requests without a browser.

## General

- Work in `/work`. Do not modify `/home/dev/.config/` or the sandbox state.
- If other directories are mounted (`/work-ansible`, `/work-terraform`…), they contain repositories related to the main project. Explore them if the context calls for it or if the user explicitly asks you to.
