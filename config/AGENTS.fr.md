# Environnement docker-altrcode

## 1 — Jamais make / docker en direct

`make`, `docker`, `docker-compose` n'existent pas dans ce conteneur.
Toute opération de stack passe par **`altrcode-ctl`** (socket unix → dispatcher hôte → Makefile).

Traduction systématique — retire `make ` et passe la cible à `altrcode-ctl` :

| Demande                              | Commande                              |
|--------------------------------------|---------------------------------------|
| démarrer / make up / make start      | `altrcode-ctl up` ou `altrcode-ctl start` |
| arrêter / make down / make stop      | `altrcode-ctl down` ou `altrcode-ctl stop` |
| tests / make test                    | `altrcode-ctl test`                   |
| logs / make logs                     | `altrcode-ctl logs`                   |
| état / make ps                       | `altrcode-ctl ps`                     |
| console cache:clear                  | `altrcode-ctl console cache:clear`    |

- Consulte `/work/Makefile` pour connaître les cibles disponibles du projet.
- Les cibles avec argument n'acceptent qu'UN argument, sans métacaractères shell (pas de `;`, `|`, `$`, quotes).

## 2 — Fichiers pinnés

Si `PIN_PROTECTION=1`, les fichiers d'autorité du projet (Makefile, compose, `.env`) sont hashés au démarrage. Toute modification pendant la session entraîne le **refus de toute opération `altrcode-ctl`** par le dispatcher.

- Ne modifie jamais ces fichiers — ils ne te sont pas destinés.
- Au premier refus : préviens l'utilisateur, n'insiste pas. Le re-pin se fait en relançant la stack depuis l'hôte.

## 3 — Git

Local uniquement : `status`, `diff`, `log`, `add`, `commit`. Le conteneur n'a ni client SSH ni identifiants — `git push` échoue systématiquement.

**Pour pusher, utilise toujours `altrcode-ctl git-push` (pas `git push`).** Cette cible est définie dans le Makefile du projet et s'exécute côté hôte avec ses identifiants SSH. Si le projet la déclare avec argument (`git-push = 1`), tu peux passer une branche : `altrcode-ctl git-push ma-branche`. Sans argument, elle pousse la branche courante.

## 4 — Skills distants

**Demande confirmation à l'utilisateur avant d'ajouter un skill distant.**

```bash
npx skills add <owner>/<repo>/<skill-id>    # installe dans .claude/skills/
```

Les skills locaux (`.claude/skills/`) sont chargés automatiquement sans commande. N'ajoute jamais un skill distant sans accord explicite — cela modifie l'environnement de la session.

## 5 — Serveurs MCP

**Demande confirmation à l'utilisateur avant d'ajouter un serveur MCP.**

Si tu es **opencode** :
```bash
opencode mcp add    # prompt interactif : type, nom, URL
```

Si tu es **Claude Code** :
```bash
claude mcp add <nom> <commande>
```

Les MCPs étendent ta surface d'action au-delà du dispatcher — toujours valider avec l'utilisateur.

## 6 — Navigateur Chrome (MCP chrome-devtools)

Si l'utilisateur a démarré le conteneur Chrome (`make chrome-up` depuis la stack docker-altrcode), le MCP **`chrome-devtools`** est disponible dans les projets qui ont un `.mcp.json` le déclarant. Il pilote un Chrome headless via CDP (Chrome DevTools Protocol).

**Capacités disponibles :**
- Navigation et chargement de pages
- Captures d'écran
- Inspection et manipulation du DOM
- Exécution de JavaScript dans la page
- Monitoring réseau (requêtes, réponses, headers)
- Audits Lighthouse (performance, accessibilité, SEO, bonnes pratiques)

**Utilisation :**
- Le MCP se charge automatiquement si `.mcp.json` le déclare — vérifie avec `/mcp` en cas de doute.
- Le Chrome tourne avec `network_mode: host` : il voit les mêmes entrées `/etc/hosts` que l'hôte, donc les stacks locales sont accessibles par leur domaine dès qu'elles tournent.
- **Tu ne démarres/arrêtes pas Chrome toi-même** — c'est l'utilisateur qui le gère depuis l'hôte.
- Si le MCP ne répond pas ou si `list_pages` échoue : Chrome n'est probablement pas démarré. Signale-le à l'utilisateur (`make chrome-up` depuis docker-altrcode).

## 7 — Recherche web

Utilise l'outil de recherche web natif : `WebSearch` pour Claude Code, `websearch` (Tavily / TinyFish) pour opencode. Évite `webfetch` directement sur un moteur de recherche — Google retourne un captcha aux requêtes sans navigateur.

## Général

- Travaille dans `/work`. Ne modifie pas `/home/dev/.config/` ni l'état du sandbox.
- Si d'autres répertoires sont montés (`/work-ansible`, `/work-terraform`…), ils contiennent des repos liés au projet principal. Explore-les si le contexte le demande ou si l'utilisateur te le demande explicitement.
