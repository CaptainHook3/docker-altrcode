<!-- Example git workflow, to place in the .opencode/instructions/ directory of the target project -->

# Git workflow

## Action rules (mandatory)
| User request | Action |
|---|---|
| Nothing about git | **Do not touch git**: no `add`, no `commit`, no branch, no stash, even at the end of a task. |
| "version it" / "commit" with no detail | `git add` the files changed by the task, commit, then `altrcode-ctl git-push`, **on the current branch** (no branch switch). |
| "create a branch" | From `develop`: `git checkout develop` then `git checkout -b feature/<relevant-title>`; the title describes the work in progress. |

- **No signature or attribution** in commits: no `Co-Authored-By`, no mention of Claude/AI/agent, no trailer or added body. Message only.
- Push only through `altrcode-ctl git-push [branch]` (`make git-push` → `git push origin <branch>` on the host), never `git push`. No `--force`, rebase or amend of a pushed commit without explicit approval.
- No network access to the remote from the container (`fetch`/`pull` are done by the user).

## Branches
- `master` = production; `develop` = integration, base of every new branch.
- Name: `feature/<kebab-case-title>`, e.g. `feature/fix-redis-db-injection`: lowercase, hyphens, no number or special character. Short-lived branches, one per topic.
- Old `feature/<n>/...` branches (history) stay as they are.
- Production releases / hotfixes / merge requests: handled by the user unless asked.

## Commit messages
- A single short line, **in English**, in Conventional Commits format: `<type>(<scope>): <description>`, e.g. `fix(cache): isolate redis db per environment`.
- `type` ∈ `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `style`; `scope` (optional) = affected area (`api-v3`, `api-v2`, `connector`, `live`, `bo`, `stats`, `cache`, `docker`, `tests`…). Imperative description, lowercase, no trailing period, ≤ 72 characters in total.
- No body, no ticket number, no trailer. Always through `git commit -m "..."`.
- The old history (`#feature/10/...`) is not to be reproduced.
- One commit = one coherent change; test references (generated from a production dump only, see testing) and migrations go in the same commit.
- Never commit: `app/.env*.local`, dumps, `public/images`, `public/data`, `var/`, `vendor/`, `node_modules/`, secrets. Review `git status` / `git diff --cached` before committing.
- Before committing: `altrcode-ctl fix "<files /app/...>"` on the modified PHP files.

## Pre-commit hook
`git/pre-commit` (installed in `.git/hooks/`, shared between host and container) runs php-cs-fixer on the staged PHP files, then re-stages them. It runs wherever `git commit` runs (the push through `altrcode-ctl git-push` does not trigger it).

The hook detects its execution context automatically:
- from the host: `make fix arg="<files>"`;
- from the container: `altrcode-ctl fix "<files>"` → dispatcher → `make fix` on the host.

No manual action required: `git commit` works in both contexts.
