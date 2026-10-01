# Installation et premier projet

## Prérequis

Le profil d'installation fourni cible Windows. Il nécessite Git, Python 3.11+
et une version de Codex qui expose `codex plugin`. Utiliser le binaire de
l'application si un ancien exécutable `codex` présent dans le PATH masque ces
commandes. Le runtime Studio utilise uniquement la bibliothèque standard Python.

Pour produire : disposer d'un ComfyUI local fonctionnel, de
[Comfy MCP local](https://docs.comfy.org/agent-tools/mcp) et de comfy-cli,
ainsi que de Blender et du MCP Blender connecté à Codex. Ces dépendances sont
installées séparément. Le plugin ne démarre pas le moteur et ne télécharge ni
modèle, ni nœud. La vue éclatée textile nécessite Codex Image dans la conversation.

## Préparer le checkout Windows

Depuis le dossier où conserver le code :

```powershell
git clone https://github.com/leuzeus/atelier-3d.git
Set-Location atelier-3d
python -m venv .venv
.\.venv\Scripts\python.exe -B scripts/studio.py configure --output config.local.json
```

Ouvrir `config.local.json` et adapter les valeurs avant l'installation :

| Clé | Valeur attendue |
| --- | --- |
| `comfyui.base_url` | Adresse HTTP avec port sur la boucle locale, par défaut `http://127.0.0.1:8188` |
| `comfyui.mcp_command` | Exécutable `comfy-mcp`, de préférence un chemin absolu accessible à Codex |
| `comfyui.cli_command` | Exécutable `comfy`, de préférence un chemin absolu |
| `comfyui.data_root` | Chemin absolu de votre dossier de données ComfyUI existant ; **à renseigner pour le profil Windows**, ne pas laisser `null` |
| `comfyui.max_parallel_jobs` | Limite souhaitée, initialement 1 |
| `blender.expected_mcp_server` | Nom du serveur MCP Blender connecté |
| `workspace.default_root` | Dossier de projets souhaité, ou `null` pour le préciser par projet |

Le dossier de données ComfyUI est distinct du code moteur et de son environnement
Python. Cette configuration ne déplace aucun modèle. Dans un fichier JSON,
utiliser `/` pour les séparateurs Windows ou doubler les antislashs.

L'ordre de recherche est : `A3D_CONFIG`, puis `config.json` sous `PLUGIN_DATA`,
puis `config.local.json` à la racine du checkout, puis `templates/config.json`.
Le fichier local est ignoré par Git et exclu de l'archive portable.

```powershell
.\.venv\Scripts\python.exe -B scripts/studio.py doctor
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/studio.py doctor --live-comfy
```

Le diagnostic live interroge le MCP déjà installé, sans installer de dépendance
ni lancer de génération. `UNAVAILABLE` signifie qu'une dépendance est absente ou
injoignable. Vérifier les résultats, pas seulement le code de sortie du diagnostic.

## Installer dans Codex

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_local_install.py
$marketplacePath = (Resolve-Path .local/marketplace).Path
codex plugin marketplace add "$marketplacePath"
codex plugin add atelier-3d@atelier-3d-local
```

Le script prépare une copie dans `.local/marketplace/plugins/atelier-3d-<version>`.
Elle contient les chemins Python et de configuration propres à cette machine.
Ne pas publier ce dossier ni le déplacer après installation. Le script ne modifie
pas les caches de Codex et n'accorde aucune confiance aux hooks.

Relancer la conversation ou recharger la connexion MCP si elle conserve l'ancienne
version. Vérifier le nom et la version du serveur ainsi que les 29 outils. Examiner
les six définitions de hooks dans l'interface native avant de les approuver.
Un serveur déjà attaché à une ancienne conversation ne se recharge pas forcément
lorsqu'une nouvelle version est installée.

### Mise à jour et erreurs de hooks

Terminer les opérations en cours avant de remplacer le plugin. Après une mise à
jour, fermer puis rouvrir Codex avant de reprendre la production. Le remplacement
du cache peut retirer les scripts d'une ancienne version alors qu'une conversation
conserve encore ses chemins : un hook peut alors sortir avec le code 1 avant même
d'exécuter ses contrôles. Recharger seulement le MCP ne prouve pas que les hooks
de la conversation ont été rechargés.

Pour diagnostiquer `hook exited with code 1`, distinguer trois vérifications :

- Les définitions sont présentes, activées et approuvées dans Codex.
- Les commandes de la copie installée s'exécutent avec succès ; cela teste les
  scripts, mais pas leur chargement dans une conversation déjà ouverte.
- Une nouvelle exécution dans l'application réussit après rechargement. Consulter
  les résultats du nouvel échange ; un ancien échec reste une preuve historique.

Relever l'événement, la version et le chemin concernés, ainsi que l'erreur détaillée
si elle est disponible. Ne pas attribuer un code 1 au remplacement du cache sur la
seule base du message générique. Si l'échec persiste dans un nouvel échange après
redémarrage, poursuivre le diagnostic du lanceur et de son environnement. Ne pas
désactiver les hooks, recréer manuellement l'ancien cache ou accorder leur confiance
par script pour masquer le problème.

Le profil de compatibilité a été vérifié avec Codex 0.159.2. Il utilise
`.codex-plugin/plugin.json`, un `cwd` relatif et une copie du manifeste portable
renommée `plugin.portable.json` pour éviter un défaut de découverte des hooks
observé sur cette version. Requalifier ce profil après une évolution du chargeur.
La réussite des tests Python sur Linux ne qualifie pas l'installation Codex Linux.

Si la version est déjà préparée, le script refuse de l'écraser. Conserver cette
copie et utiliser une nouvelle version des sources pour une mise à jour installable.
Les données d'assets et leurs décisions ne sont pas migrées en faux états approuvés.

## Démarrer un asset

1. Créer ou choisir un dossier d'asset distinct du checkout du plugin.
2. Dans Codex, sélectionner `@Atelier 3D`, joindre les images originales, préciser
   la destination (`game`, `animation`, `render`, `3d_print`), les dimensions et
   les composants qui doivent rester séparés ou mobiles.
3. Examiner l'analyse et les vues : signaler ce qui est observé, caché ou extrapolé.
4. Examiner la méthode proposée par composant avant de confirmer les routes.
5. Pour des patrons, faire préparer le dossier et les packages, puis la vue
   éclatée Codex Image et le board en trois parties. Ouvrir le SVG/HTML et vérifier
   les proportions, pièces, matières, coutures, plis, droit-fil et repères.
6. Donner la décision sur ce board précis. La reconstruction peut alors commencer
   via les opérations contrôlées ; valider la silhouette avant les comportements.

Codex peut présenter des choix quand une information manque. La provenance d'une
image et la fidélité d'une hypothèse ne doivent jamais être fabriquées pour
franchir une étape. Lire [le parcours complet](production.md).

## CLI et archive portable

```powershell
.\.venv\Scripts\python.exe -B scripts/studio.py tools
.\.venv\Scripts\python.exe -B scripts/studio.py call studio_create_project --arguments create-project.json
New-Item -ItemType Directory -Force dist | Out-Null
.\.venv\Scripts\python.exe -B scripts/package_plugin.py --output dist/atelier-3d-0.5.3.zip
```

`create-project.json` doit contenir `project_root` absolu et un `asset` conforme à
`schemas/asset.schema.json`. Les chemins d'artefacts sont ensuite relatifs à ce
projet. Adapter les exemples de contrats sous `tests/fixtures` ; leurs images
uniformes ne sont pas des références de production.

L'archive portable inclut sources, contrats, skills, documentation et licence,
avec inventaire et empreintes. Elle exclut la configuration machine et les assets.
Elle ne remplace pas la préparation du profil local et refuse l'écrasement d'une
archive existante.
