<!-- Example git workflow, to place in the .opencode/instructions/ directory of the target project -->

# Git workflow

## Règles d'action (impératives)
| Demande de l'utilisateur | Action |
|---|---|
| Rien sur git | **Ne pas toucher à git** : ni `add`, ni `commit`, ni branche, ni stash, même en fin de tâche. |
| « versionne » / « commit » sans précision | `git add` des fichiers modifiés par la tâche, commit, puis `altrcode-ctl git-push`, **sur la branche courante** (pas de changement de branche). |
| « crée une branche » | Depuis `develop` : `git checkout develop` puis `git checkout -b feature/<titre-pertinent>` ; le titre décrit le travail en cours. |

- **Aucune signature ni attribution** dans les commits : pas de `Co-Authored-By`, pas de mention de Claude/IA/agent, pas de trailer ni de corps ajouté. Message seul.
- Push uniquement via `altrcode-ctl git-push [branche]` (`make git-push` → `git push origin <branche>` côté hôte), jamais `git push`. Pas de `--force`, rebase ou amend d'un commit poussé sans accord explicite.
- Pas d'accès réseau au remote depuis le conteneur (`fetch`/`pull` à faire par l'utilisateur).

## Branches
- `master` = production ; `develop` = intégration, base de toute nouvelle branche.
- Nom : `feature/<titre-kebab-case>`, ex. `feature/fix-redis-db-injection` : minuscules, tirets, sans numéro ni caractère spécial. Branches courtes, une par sujet.
- Les anciennes branches `feature/<n>/...` (historique) restent telles quelles.
- Mise en prod / hotfix / merge requests : gérés par l'utilisateur sauf demande.

## Messages de commit
- Une seule ligne courte, **en anglais**, au format Conventional Commits : `<type>(<scope>): <description>`, ex. `fix(cache): isolate redis db per environment`.
- `type` ∈ `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `style` ; `scope` (optionnel) = zone touchée (`api-v3`, `api-v2`, `connector`, `live`, `bo`, `stats`, `cache`, `docker`, `tests`…). Description à l'impératif, minuscule, sans point final, ≤ 72 caractères au total.
- Pas de corps, pas de numéro de ticket, pas de trailer. Toujours via `git commit -m "..."`.
- L'historique ancien (`#feature/10/...`) n'est pas à reproduire.
- Un commit = un changement cohérent ; références de tests (générées sur dump de prod uniquement, cf. testing) et migrations dans le même commit.
- Ne jamais commiter : `app/.env*.local`, dumps, `public/images`, `public/data`, `var/`, `vendor/`, `node_modules/`, secrets. Relire `git status` / `git diff --cached` avant de commiter.
- Avant commit : `altrcode-ctl fix "<fichiers /app/...>"` sur les PHP modifiés.

## Hook pre-commit
`git/pre-commit` (installé dans `.git/hooks/`, partagé hôte/conteneur) lance php-cs-fixer sur les fichiers PHP indexés puis les ré-indexe. Il s'exécute là où tourne `git commit` (le push via `altrcode-ctl git-push` ne le déclenche pas).

Le hook détecte automatiquement le contexte d'exécution :
- depuis l'hôte : `make fix arg="<fichiers>"` ;
- depuis le conteneur : `altrcode-ctl fix "<fichiers>"` → dispatcher → `make fix` côté hôte.

Aucune action manuelle requise : `git commit` fonctionne dans les deux contextes.
