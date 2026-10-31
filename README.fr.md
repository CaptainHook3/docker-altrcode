# Docker altRcode

[English](README.md) | **Français**

## Description

Agent de développement confiné (opencode ou Claude Code) dans un conteneur Docker éphémère.

Cette stack fournit un meilleur niveau de confidentialité et de sécurité qu'un agent directement installé sur la machine hôte.

- **Un conteneur par session**, un seul agent actif (`DEFAULT_AGENT=opencode|claude` dans le `.env`, ou `AGENT=` au lancement). Pas de socket Docker, pas de clés dans l'image.
- **Dispatcher hôte** (`dispatcher/dispatcher.py`) : socket unix 0600, n'exécute que les cibles `make` déclarées dans `[ops]` de la config du projet cible — le reste est structurellement impossible.
- **Proxy d'egress** (`dispatcher/egress_proxy.py`, `DOMAIN_WHITELIST=1`) : tout le trafic HTTP(S) du conteneur passe par une whitelist de domaines (globaux + par projet). HTTP 403 sinon.
- **Pin checking** (`PIN_PROTECTION=1`) : les fichiers d'autorité du projet (Makefile, compose, `.env`) sont hashés au démarrage, sans accès en écriture pour la stack. Si l'un change pendant la session, toute opération `make` est refusée jusqu'au prochain lancement.

```text
docker-altrcode/
├── bin/
│   ├── docker-altrcode         # wrapper de session (dispatcher + conteneur)
│   ├── opencode-session-ctl    # gestion sessions opencode (SQLite)
│   └── claude-session-ctl      # gestion sessions Claude Code (JSONL)
├── config/
│   ├── opencode-settings.jsonc
│   ├── claude-settings.json
│   ├── AGENTS.md               # guide global pour les agents (anglais)
│   ├── AGENTS.fr.md            # version française, choisie par USER_LANGUAGE=fr
│   └── CLAUDE.md               # pont → AGENTS.md (Claude Code)
├── container/
│   ├── entrypoint.sh
│   └── altrcode-ctl            # client dispatcher (exécuté dans le conteneur)
├── dispatcher/
│   ├── dispatcher.py           # serveur socket unix hôte
│   ├── egress_proxy.py         # proxy HTTP/HTTPS filtré par domaine
│   └── projects/
│       └── xxxx.conf           # config projet (ops, pins, domains)
├── examples/                   # templates à copier dans le projet cible
│   ├── docker-altrcode.conf    # conf dispatcher pour la stack elle-même
│   ├── drupal.conf             # conf dispatcher Drupal
│   ├── symfony.conf            # conf dispatcher Symfony
│   ├── git-workflow.md         # template .opencode/instructions/git-workflow.md (anglais)
│   ├── git-workflow.fr.md      # version française du même template
│   └── opencode.jsonc          # template MCP chrome-devtools pour opencode
├── tools/
│   └── whisper-input           # daemon speech-to-text push-to-talk (hôte)
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── Makefile
```

### Niveaux de sécurité

| Niveau | Env | Fonctionnement |
|---|---|---|
| Dispatcher | *(toujours actif)* | Socket unix 0600 hôte. Seules les cibles `make` déclarées dans `[ops]` du conf projet sont exécutables. |
| Whitelist de domaines | `DOMAIN_WHITELIST=1` | Proxy egress hôte. Tout trafic HTTP(S) filtré par domaine (suffix match). HTTP 403 sinon. |
| Pin checking | `PIN_PROTECTION=1` | Hash des fichiers d'autorité au démarrage. Opération de stack (commande make) refusée si modification détectée en session. Les fichiers pinnés sont aussi montés en `:ro` dans le conteneur (overmounts individuels sur `/work`). |

La whitelist de domaines fonctionne à deux niveaux : les domaines globaux (LLM, outils, npm…) sont déclarés dans `DOMAIN_GLOBAL_WHITELIST` du `.env` ; les domaines spécifiques à chaque projet sont dans `[domains]` de `dispatcher/projects/xxxx.conf`. Les deux listes sont fusionnées par le proxy.

### Fichiers pin checkés

Les fichiers listés dans `[pins]` du conf projet sont hashés au démarrage (`~/.cache/docker-altrcode/run/<projet>/pins.json`) et montés en `:ro` dans le conteneur. Ils vivent sur l'hôte dans le répertoire du projet :

```text
<root>/                         # root = champ [project] root du conf
├── Makefile                    # toujours pinné
├── docker-compose*.yml         # compose de la stack
└── app/
    └── .env.*.local            # variables d'environnement locales
```

Le chemin `root` de chaque projet est défini dans `dispatcher/projects/<nom>.conf`.

### Volumes hôte

Les données persistées par les agents sont écrites sur l'hôte, hors de l'image Docker :

| Chemin hôte | Contenu |
|---|---|
| `~/.config/docker-altrcode/` | Configs agents copiées au démarrage (settings, AGENTS.md), configs projet `.conf`, état Claude Code (`claude/` : sessions JSONL, mémoire, cache) |
| `~/.local/state/docker-altrcode/` | Persistance opencode : conversations (SQLite) |
| `~/.cache/docker-altrcode/` | Cache opencode, socket unix runtime, logs dispatcher/egress, fichier de pins |

### Configs agents

Au démarrage de chaque session, `bin/docker-altrcode` copie les fichiers de config depuis le dépôt vers `~/.config/docker-altrcode/` avant de lancer le conteneur.

| Fichier source (dépôt) | Copie montée dans le conteneur |
|---|---|
| `config/opencode-settings.jsonc` | `~/.config/docker-altrcode/opencode/opencode.jsonc` |
| `config/AGENTS.md` ou `config/AGENTS.<langue>.md` | `~/.config/docker-altrcode/opencode/AGENTS.md` |
| `config/CLAUDE.md` | `~/.config/docker-altrcode/claude/CLAUDE.md` |
| `config/claude-settings.json` | `~/.config/docker-altrcode/claude/settings.json` (après `envsubst`) |

Les instructions des agents suivent `USER_LANGUAGE` du `.env` : `config/AGENTS.<langue>.md` est utilisé s'il existe (par exemple `AGENTS.fr.md` pour `fr`), sinon le `config/AGENTS.md` anglais. La copie s'appelle toujours `AGENTS.md` dans le conteneur.

Les volumes d'état sont montés en `:rw` (projets, backups, cache…). Les fichiers d'instructions (`AGENTS.md`, `CLAUDE.md`) sont montés en `:ro` par overmount individuel — l'agent peut les lire mais pas les écrire. Le dépôt source (`config/`) n'est jamais monté dans le conteneur. Les copies sont régénérées depuis le dépôt à chaque nouvelle session.

Côté Claude Code, tout `~/.config/docker-altrcode/claude/` est monté sur `~/.claude` et partagé entre projets et instances : connexion, conversations (`projects/-work/<id>.jsonl`, reprises par `/resume`), mémoire auto, historique des prompts. Seul `~/.claude/sessions/` (registre des processus Claude en cours, un `<pid>.json` par instance) est un `tmpfs` propre à chaque conteneur : deux instances parallèles ont le même pid et s'y écraseraient. Ce registre est vidé à l'arrêt, sans effet sur `/resume`.

Côté opencode, l'état (`~/.config`, `~/.local/share`, `~/.local/state`, `~/.cache`) est aussi partagé entre projets et instances. Les sessions restent tout de même séparées par projet : opencode identifie un projet par son dépôt git, pas par son chemin. Le service opencode en arrière-plan est désactivé (`"disabled": true` dans `~/.config/opencode/service.json`) car ses fichiers communs s'écraseraient entre instances parallèles ; chaque instance utilise son propre serveur, avec le proxy de son conteneur.

## Installation

1. Prérequis : `docker`, `docker compose`, `python3`, `envsubst` sur l'hôte.

2. Copier et remplir `.env` :
   ```bash
   cp .env.example .env
   ```

3. Créer la config du projet cible dans `dispatcher/projects/xxxx.conf` : ajuster `root`, `container`, et optionnellement `[ops]`, `[pins]`, `[domains]`, `[extra_dirs]`. Des templates sont disponibles dans `examples/`.

4. Construire l'image :
   ```bash
   make build
   ```

5. Lancer une session :
   ```bash
   make up                              # projet et agent de DEFAULT_PROJECT / DEFAULT_AGENT du .env
   make up PROJECT=xxxx AGENT=opencode  # projet et agent explicites
   ```

## Utilisation

**Démarrer une session :**
```bash
make up                              # projet et agent de DEFAULT_PROJECT / DEFAULT_AGENT du .env
make up PROJECT=xxxx AGENT=opencode  # projet et agent explicites
```

`PROJECT=` et `AGENT=` écrasent les variables `DEFAULT_PROJECT` et `DEFAULT_AGENT` du `.env` pour la commande en cours uniquement. Chacun peut être donné seul (`make up AGENT=opencode`). C'est valable pour toutes les commandes qui les acceptent.

**État des conteneurs :**
```bash
make ps
```

**Navigateur Chrome headless (CDP) :**
```bash
make chrome-up    # démarrer Chrome (réseau hôte, CDP port 9222)
make chrome-down  # arrêter
```
Le conteneur utilise `network_mode: host` — il partage le réseau de l'hôte, y compris son `/etc/hosts`. Les stacks locales sont donc accessibles par leur domaine dès qu'elles tournent. Chrome est disponible pour les projets ayant un `.mcp.json` configurant le serveur MCP `chrome-devtools`.

## Maintenance

**Gestion des sessions :**
```bash
make session-list                                    # sessions de DEFAULT_AGENT
make session-list AGENT=opencode                     # sessions d'un agent explicite
make session-clean                                   # toutes les sessions de DEFAULT_AGENT
make session-clean AGENT=opencode                    # toutes les sessions d'un agent explicite
make session-clean arg=<session-id>                  # une session de DEFAULT_AGENT
make session-clean AGENT=opencode arg=<session-id>   # une session d'un agent explicite
```

Avec `AGENT=claude`, `session-clean` supprime le transcript (`projects/<projet>/<id>.jsonl`, source de `/resume`), ses artefacts, `file-history/<id>`, `session-env/<id>` et les entrées de `history.jsonl` (sauvegardé en `.backup-<date>` avant modification). La mémoire auto (`projects/<projet>/memory/`) est conservée.

**Explorer un container :**

```bash
make ps                             # repérer le nom du conteneur agent : docker-altrcode_agents-run-<id>
make exec arg=82b3aef27e7a          # conteneur agent docker-altrcode_agents-run-82b3aef27e7a
make exec arg=chrome                # conteneur docker-altrcode_chrome
```

`<id>` est le suffixe du nom affiché par `make ps` (12 caractères hexadécimaux), à ne pas confondre avec la colonne CONTAINER ID.

**Mise à jour :**

L'auto-update est désactivé dans les deux agents (`env.DISABLE_AUTOUPDATER=1` dans `claude-settings.json` pour Claude Code, `update: disable` pour opencode) — ils ne se mettent pas à jour seuls depuis le conteneur. Pour les mettre à jour :

```bash
make build            # réinstalle toujours les agents (dernières versions), le reste de l'image reste en cache
make build NOCACHE=1  # reconstruction complète, y compris la dernière image de base node:24-slim
```

`NOCACHE=1` n'est utile que de temps en temps, pour les mises à jour système de l'image. Une modification de `docker-compose.yml` ne nécessite pas de rebuild : il est relu à chaque `make up`.

Les volumes hôte (conversations, sessions, mémoire) ne sont pas affectés par le rebuild.

**Désinstallation :**

```bash
make down
bash tools/clean-host.sh
```

`make down` arrête et supprime les conteneurs agents en cours (tous projets confondus) et le réseau de la stack. Il ne touche à aucune donnée sur l'hôte : configurations, connexion Claude, sessions et mémoire sont conservées.

`tools/clean-host.sh` supprime toutes les données laissées par la stack sur la machine hôte (configurations, sessions, mémoire des agents, cache, base de données opencode) :

Le script affiche la taille de chaque répertoire concerné et demande une confirmation avant de supprimer. Les répertoires nettoyés sont `~/.config/docker-altrcode`, `~/.local/state/docker-altrcode` et `~/.cache/docker-altrcode` (chemins XDG respectés si définis).

> Les images Docker ne sont pas supprimées par ce script. Pour les retirer aussi :
> ```bash
> docker rmi agents_docker-altrcode zenika/alpine-chrome:latest
> ```

## Organisation des projets cible

Les projets ciblés suivent une convention native opencode/Claude Code. La stack lit d'abord ses propres instructions dans `config/AGENTS.md` puis cherche celles du projet pour les compléter en fonction des spécificités de chacun de manière optimisée, en suivant le principe du `Hierarchical context` / `Lazy context loading`.

```text
<projet>/
├── Makefile                       # entrée make (push, tests, stack…)
├── AGENTS.md                      # source unique — courte, indexe les sous-fichiers
├── CLAUDE.md                      # pont d'une ligne : @AGENTS.md
└── .opencode/
    └── instructions/              # sous-fichiers par thème, chargés à la demande
        ├── stack.md               # démarrer, tester, déployer
        ├── git-workflow.md        # branches, commits, workflow
        └── <thème>.md             # règles métier (nom libre)
```

- **`AGENTS.md`** : auto-chargé par opencode, importé par Claude Code via `CLAUDE.md`. Contient une description courte du projet et un index (tableau `quand tu travailles sur X, lis <chemin>`) avec des chemins relatifs explicites vers les sous-fichiers.
- **`CLAUDE.md`** : une seule ligne — `@AGENTS.md`. Rien d'autre.
- **`.opencode/instructions/*.md`** : un fichier par thème, chargé à la demande selon la tâche — pas injecté systématiquement en contexte.

Des templates prêts à l'emploi sont disponibles dans `examples/` : configs dispatcher (`drupal.conf`, `symfony.conf`, `docker-altrcode.conf`), `git-workflow.md` (anglais) ou `git-workflow.fr.md` (français) à copier sous le nom `.opencode/instructions/git-workflow.md`, `.mcp.json` et `opencode.jsonc` pour le MCP chrome-devtools.

### Workflow Git

La politique git du projet (branches, conventions de commit, workflow) doit être décrite dans le fichier `.opencode/instructions/git-workflow.md` du projet cible, chargé par l'agent quand il travaille sur git.

`git add` et `git commit` sont exécutés par le git embarqué dans le conteneur. `git push` en revanche nécessite les clés SSH de l'hôte — il passe par le dispatcher via une cible `make git-push` du projet :

```makefile
## git-push         :     Push current branch (git push origin <arg> or current branch).
.PHONY: git-push
git-push:
	git push origin $(if $(arg),$(arg),$(shell git rev-parse --abbrev-ref HEAD))
```

À déclarer dans le conf du projet pour autoriser le git push :

```ini
[ops]
git-push = 1
```

L'agent appelle `altrcode-ctl git-push` (branche courante) ou `altrcode-ctl git-push ma-branche`.

### Skills par projet

```text
<projet>/
└── .claude/
    └── skills/
        └── <id>/                  # id = nom du dossier
            ├── SKILL.md           # frontmatter : name + description (obligatoire)
            └── ...                # scripts, références, etc.
```

- `.claude/skills/` est lu nativement par Claude Code et par opencode (source de compatibilité) — un seul dossier pour les deux agents.
- Un skill sans `description` dans son frontmatter n'est pas annoncé à l'agent.
- Un skill projet écrase le même id éventuel au niveau global (stack).

### MCP par projet

Les deux agents lisent leur propre fichier de config MCP — formats différents, pas de fichier partagé.

```text
<projet>/
├── .mcp.json              # MCP Claude Code  → { "mcpServers": { "<nom>": { ... } } }
└── opencode.jsonc         # MCP opencode     → { "mcp": { "<nom>": { ... } } }
```

- **`.mcp.json`** : versionnable, partagé avec l'équipe. Approuvé interactivement à la première session. Un template est disponible dans `examples/.mcp.json`.
- **`opencode.jsonc`** : config projet opencode, section `mcp`. Un template est disponible dans `examples/opencode.jsonc`.
- L'ajout via CLI (`claude mcp add`, `opencode mcp add`) est en mode `ask` dans les deux configs de la stack.

### Répertoires supplémentaires

Un projet peut nécessiter l'accès à plusieurs repos liés (stack docker + ansible, terraform…). La section `[extra_dirs]` du conf permet de monter des répertoires supplémentaires dans le conteneur :

```ini
[extra_dirs]
/home/mike/Documents/Projets/xxxx-ansible   = /work-ansible
/home/mike/Documents/Projets/xxxx-terraform = /work-terraform
```

Chaque entrée est montée en `:rw` à côté de `/work`. Avec Claude Code, `/add-dir /work-ansible` charge le second repo dans le contexte de la session. Avec opencode, l'agent accède aux fichiers si on lui demande explicitement (les répertoires disponibles sont annoncés dans `config/AGENTS.md`).

La section peut être absente — aucun volume supplémentaire n'est alors monté.

> **Limites** : les extra dirs sont montés en `:rw` sans pin checking ni overmount `:ro`. Le dispatcher n'exécute des commandes `make` que depuis `root` (le repo principal) — les extra dirs sont en lecture/écriture libre.

## Speech-to-text

`tools/whisper-input` est un daemon push-to-talk hôte. Le daemon tourne en arrière-plan avec le modèle chargé en mémoire ; les commandes `begin`/`end` (ou `toggle`) lui sont envoyées via socket unix depuis les raccourcis du WM/DE. Le texte est injecté dans la fenêtre active — fonctionne dans opencode comme dans Claude Code sans aucun changement Docker. Compatible X11 et Wayland.

### Prérequis

- GPU NVIDIA avec **CUDA** (drivers + CUDA toolkit). Vérifier : `nvidia-smi`
- `python3`, `arecord` (paquet `alsa-utils`) — présents par défaut sur Ubuntu
- Outil d'injection selon le serveur d'affichage :
  - **X11** (Ubuntu 24 et antérieur) : `sudo apt install xdotool`
  - **Wayland** (Ubuntu 26+) : `sudo apt install wtype`

### Installation

```bash
mkdir -p ~/.local/bin ~/.local/share/whisper-input
python3 -m venv ~/.local/share/whisper-input/venv
~/.local/share/whisper-input/venv/bin/pip install faster-whisper "av==13.0.0"
cp tools/whisper-input ~/.local/bin/whisper-input # Modif custom pour pouvoir écrire le texte vers la fenêtre active
chmod +x ~/.local/bin/whisper-input
```

> Si le GPU n'est pas détecté au premier lancement, force le backend CUDA 12 :
> ```bash
> ~/.local/share/whisper-input/venv/bin/pip install ctranslate2 --extra-index-url https://pypi.nvidia.com
> ```

### Configuration (~/.bashrc sur l'hôte)

Ajouter dans `~/.bashrc` :

```bash
# whisper-input (speech-to-text push-to-talk)
export WHISPER_MODEL=large-v3
export WHISPER_LANG=fr
alias whisper='whisper-input daemon > /dev/null 2>&1 &'
alias whisper-stop='whisper-input stop'
```

Puis recharger : `source ~/.bashrc`

### Raccourci clavier (WM/DE)

Le daemon ne capte aucune touche lui-même — lier `begin`/`end` (ou `toggle`) dans le gestionnaire de fenêtres :

**GNOME** (Paramètres → Clavier → Raccourcis personnalisés) — mode toggle (une pression démarre, la suivante arrête) :
```text
whisper-input toggle   →   F9
```

**i3 / sway** (`~/.config/i3/config`) — push-to-talk réel (appuyer/relâcher) :
```text
bindsym F9         exec --no-startup-id whisper-input begin
bindsym --release F9 exec --no-startup-id whisper-input end
```

### Lancement

```bash
whisper
```

Au premier démarrage, le modèle (~3 Go) est téléchargé depuis Hugging Face. Il est mis en cache dans :

```text
~/.cache/huggingface/hub/blobs/          ← binaire du modèle (2,9 Go)
~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3/   ← config, tokenizer (~3 Mo)
```

Les lancements suivants sont immédiats (chargement depuis le cache local).

### Arrêt

```bash
whisper-stop
```

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | Taille du modèle (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `WHISPER_LANG` | `en` | Langue de transcription |

## À propos

### FAQ

**Mon projet cible nécessite-t-il un Makefile pour que les commandes de stack fonctionnent ?**

Oui, si vous souhaitez utiliser le dispatcher. Chaque opération déclarée dans `[ops]` du conf projet correspond à une cible `make` du projet cible. Le dispatcher exécute `make <op>` dans le répertoire `root` du projet — sans Makefile, il n'y a rien à exécuter. Si votre projet n'a pas de Makefile (projet statique, repo de config…), laissez simplement `[ops]` vide ou absent : l'agent peut lire et écrire les fichiers librement, seule l'exécution de commandes de stack est impossible.

**Dois-je utiliser `make start` ou `make up` ?**

C'est pareil : `start` est un alias de `up`, les deux cibles exécutent exactement la même commande.

**Puis-je lancer deux instances de docker-altrcode en parallèle sur deux projets différents ?**

Oui. Chaque `make up PROJECT=xxxx` monte un conteneur Docker indépendant, avec son propre socket dispatcher et son propre proxy d'egress. Les deux sessions coexistent sans interférence. L'état des agents est en revanche partagé (connexion, conversations, mémoire) — Claude Code gère les accès concurrents, et le registre des processus en cours est isolé par conteneur (`tmpfs`). L'autre ressource partagée est le Chrome headless si vous l'utilisez (`make chrome-up`) — il tourne sur un port unique et les deux agents y accèdent concurremment, sans isolation entre sessions.

**Puis-je lancer deux instances de docker-altrcode en parallèle sur le même projet ?**

Non. Le dispatcher, le proxy d'egress et la socket sont rangés par projet (`~/.cache/docker-altrcode/run/<projet>/`) : une seconde instance couperait ceux de la première, qui perdrait `altrcode-ctl` (et le réseau si la whitelist est active). Le lanceur refuse donc de démarrer si une instance du même projet est déjà active (`run/<projet>/owner.pid`). Si le lanceur précédent est mort (crash, terminal fermé), le fichier est ignoré et ses processus orphelins sont nettoyés comme d'habitude.

Même sans cette limite, deux agents dans la même copie de travail écriraient dans les mêmes fichiers et le même index git, et piloteraient la même stack projet. Pour faire travailler deux agents en parallèle sur un même dépôt, cloner le dépôt une seconde fois et le déclarer comme un autre projet (par exemple `dispatcher/projects/<projet>-2.conf` avec `root` pointant vers le clone) — en gardant en tête que les deux clones partagent les conteneurs de la stack projet s'ils la démarrent.

**Puis-je lancer docker-altrcode sur lui-même comme projet cible ?**

Oui, un template est fourni dans `examples/docker-altrcode.conf`. L'agent peut lire et modifier les fichiers du dépôt. En revanche, sans cibles `[ops]` déclarées (ou avec seulement `git-push`), il ne peut pas redémarrer la stack ni builder l'image — ce qui est intentionnel : les modifications prennent effet au prochain `make start`/`make up` lancé manuellement.

**Pourquoi je ne vois pas les modèles que j'ai paramétrés dans mon `.env` sur opencode ?**

Si `OPENCODE_MODELS_WHITELIST=1`, le script de démarrage génère une config opencode qui désactive le provider built-in et enregistre un provider custom avec uniquement les modèles déclarés dans `OPENCODE_MODELS`. Ces modèles n'apparaissent pas sous une section "Scaleway" dans `/models` mais sous "Recents" après première utilisation — c'est une limitation d'opencode pour les providers custom. Si vous ne les voyez nulle part, désactivez la whitelist (`OPENCODE_MODELS_WHITELIST=0`), sélectionnez chaque modèle une fois, puis réactivez-la : ils apparaîtront ensuite systématiquement dans "Recents".

**Pourquoi whisper-input utilise un patch ?**

Le script `tools/whisper-input` est une version modifiée du daemon upstream. La modification porte sur l'injection du texte transcrit : le script original ne supporte pas tous les environnements d'affichage (X11 et Wayland), et le comportement par défaut ne correspond pas à l'usage ciblé ici (injection dans la fenêtre active du terminal plutôt qu'un champ de formulaire). Le patch est minimal et documenté dans le script lui-même.

**Dans quel cas utiliser Claude Code plutôt qu'opencode, et vice versa ?**

Claude Code (Anthropic) utilise les modèles Claude — parmi les plus capables du marché à ce jour. Avec une licence Claude Max, le coût est forfaitaire et illimité, ce qui en fait l'option la plus économique pour un usage intensif. C'est le choix naturel si la performance brute est la priorité.

opencode permet d'utiliser des modèles open weight hébergés chez un provider tiers, comme Scaleway. Ces modèles sont produits par des laboratoires indépendants d'Anthropic, leur entraînement et leurs poids sont publics, et le traitement des données dépend uniquement du contrat avec le provider choisi. Scaleway est un hébergeur européen soumis au RGPD, ce qui peut être déterminant pour des projets où la confidentialité du code ou des données est une contrainte forte. La contrepartie est un coût à l'usage (tokens) et des modèles généralement moins performants que Claude sur les tâches complexes.

**Sur quelles versions des agents le projet a-t-il été testé ?**

Claude Code 2.1.314 et opencode 2.2.5 (octobre 2026). L'image installe la dernière version publiée sur npm au moment du `make build` ; l'auto-update étant désactivé dans le conteneur, la version reste figée jusqu'au rebuild suivant.

**La stack docker-altrcode est-elle respectueuse de mes données ? Envoie-t-elle des données d'utilisation à son développeur ?**

docker-altrcode est un ensemble de scripts et de fichiers de configuration qui tournent entièrement sur votre machine. Il n'y a pas de télémétrie, pas de serveur central, pas d'appel réseau initié par la stack elle-même. Les seuls flux sortants sont les requêtes de l'agent vers le provider LLM que vous avez configuré (Anthropic ou Scaleway selon l'agent choisi), filtrées par votre whitelist de domaines si `DOMAIN_WHITELIST=1`. La stack ne collecte rien et n'envoie rien à son développeur.

**Puis-je utiliser ou modifier docker-altrcode gratuitement ?**

Oui, sans restriction. docker-altrcode est publié sous licence **MIT** : vous pouvez l'utiliser, le modifier, le redistribuer et l'intégrer dans des projets commerciaux, gratuitement et sans demander d'autorisation. La seule obligation est de conserver la mention de licence d'origine. Voir le fichier `LICENSE` à la racine du dépôt.

### Références

- [Confused Deputy: The Old Bug That AI Agents Keep Reintroducing](https://auth0.com/blog/confused-deputy-the-old-bug-that-ai-agents-keep-reintroducing) — motivation du dispatcher : exécution make sans transmettre les secrets de l'agent (Auth0, sept. 2026)
- [Policy Versus Physics: Docker Sandboxing for My AI SRE Agent](https://hackernoon.com/policy-versus-physics-docker-sandboxing-for-my-ai-sre-agent) — motivation du proxy d'egress : pourquoi un filtre réseau au niveau OS plutôt qu'une règle de prompt (HackerNoon, juil. 2026)
- [Choose a sandbox environment — Claude Code](https://code.claude.com/docs/en/sandbox-environments) — comparatif Docker/container/VM pour l'isolation des agents Claude Code
- [Memory — Claude Code](https://code.claude.com/docs/en/memory) — AGENTS.md, chargement hiérarchique du contexte (CLAUDE.md, skills, index)
- [HTTP CONNECT tunneling](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/CONNECT) — mécanisme du proxy d'egress HTTPS (tunnel TCP sans MITM)
- [opencode docs](https://opencode.ai/docs) — AGENTS.md, providers, skills, permissions
- [Claude Code docs](https://code.claude.com/docs) — hooks, MCP, permissions, settings
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — moteur de transcription speech-to-text (réimplémentation CTranslate2 de Whisper)
