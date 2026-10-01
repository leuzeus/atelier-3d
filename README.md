# Atelier 3D

[![CI](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml/badge.svg)](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plugin Codex pour préparer et produire des assets 3D à partir d'images de référence,
avec un choix de méthode par composant, des données de construction explicites et
une validation humaine aux étapes déterminantes.

**Version 0.4.0 — socle de développement.** Le runtime et ses contrats sont testés.
L'installation Codex et les connexions ont été vérifiées sous Windows. Une
production complète sur un vrai vêtement ou un asset articulé reste à qualifier.
Voir [les résultats et limites](VALIDATION.md).

## Ce que fait le plugin

- Analyse les références, les pièces, les matériaux, les proportions, les parties
  cachées et les articulations ; distingue observations et hypothèses.
- Propose une pipeline par composant, explique les alternatives et conserve la
  décision humaine avant de construire les packages.
- Produit un dossier technique et un board à examiner avant la reconstruction.
- Orchestre les jobs Comfy locaux et les opérations Blender avec preuves,
  copies de travail, checkpoints et reprise après erreur.
- Exige des validations liées au candidat actuel avant finition, comportement
  et livraison. Pour un jeu, l'import dans le moteur fait partie des contrôles.

| Méthode | Usage | Données de construction |
| --- | --- | --- |
| `PATTERN_SEWN` | Vêtements et composants textiles | Patrons polygonaux en cm, panneaux, coutures, matières et simulation préparée |
| `MULTIVIEW_PART` | Pièces volumiques séparées | Vues propres cohérentes, dimensions, ancrages et reconstruction par pièce |

Un même asset peut utiliser les deux méthodes. Une dépendance indisponible ne
permet pas de substituer discrètement une autre méthode à celle approuvée.

## Board textile en trois parties

Le board est construit depuis **les images de référence originales**, puis
présenté à l'utilisateur pour valider le découpage avant la 3D.

1. **Vues orthographiques** : face, profil et dos, cadrage et échelle communs,
   proportions comparées aux références et zones extrapolées signalées.
2. **Décomposition du vêtement** : illustration produite avec **Codex Image** à
   partir des originaux et de la liste exacte des pièces. Le compositeur ajoute
   IDs, noms, traits de rappel, matières, dimensions et caractéristiques.
3. **Patrons 2D de fabrication** : contours issus des packages, avec coupe,
   couture/piqûre, plis ou milieu, droit-fil, marges, quantités et repères
   d'assemblage appariés. Toutes les pièces utilisent la même échelle.

`studio_prepare_exploded_view` prépare la demande d'image ; Codex appelle ensuite
le générateur intégré et `studio_register_exploded_view` enregistre son résultat
réel. Studio ne lance pas lui-même ce générateur. Le board final est un SVG autonome
accompagné d'un dossier HTML. Il sert à la revue du découpage pour la 3D ; ce n'est
pas une certification de patronage ni une planche de coupe à imprimer en taille réelle.

Une modification des images, du dossier, des packages ou du board invalide
l'approbation correspondante. Voir [le contrat de fabrication](references/fabrication-board.md).

## Installation et premier usage

Le profil d'installation fourni est qualifié **sous Windows**. Studio requiert
**Python 3.11+**, sans dépendance Python tierce. ComfyUI, son MCP officiel,
Blender et son MCP sont des installations externes. Codex Image doit être
disponible dans la conversation pour la vue éclatée du board textile.

```powershell
git clone https://github.com/leuzeus/atelier-3d.git
Set-Location atelier-3d
python -m venv .venv
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Suivre ensuite [le guide d'installation et de configuration](references/getting-started.md).
Cloner le dépôt ou télécharger un ZIP n'installe pas le plugin dans Codex.

Après installation, sélectionner **Atelier 3D** avec `@` dans une conversation
Codex locale, joindre les références et préciser un dossier d'asset distinct du
code du plugin. Exemple de brief :

> Prépare un vêtement pour un jeu Unreal Engine PC/console à la troisième personne,
> sur un personnage de 1,80 m, à partir des images jointes. Propose la méthode de
> fabrication, distingue les observations des hypothèses et présente le dossier
> technique et le board de découpage avant la construction 3D.

La validation du board doit être donnée après avoir vu son contenu. Une demande
générale de production ne vaut pas approbation d'une image encore inexistante.

## Architecture

Les **11 skills** guident Codex ; le serveur Studio expose **29 outils MCP** et
utilise **17 schémas JSON**. L'état canonique du projet est conservé dans SQLite
sous `.a3d`, avec les preuves et décisions. Les fichiers `.partpkg` et
`.garmentpkg` sont des archives de transport contrôlées.

Studio appelle le [MCP officiel Comfy local](https://docs.comfy.org/agent-tools/mcp)
via stdio. Codex transmet les opérations préparées par Studio au MCP Blender.
Le plugin fournit les contrôles métier et le code d'opérations, sans embarquer
ces moteurs ni leurs modèles. Codex et Codex Image restent des services externes ;
le terme « local » décrit Studio, les fichiers de projet et l'adaptateur Comfy.

| Dossier | Responsabilité |
| --- | --- |
| `a3d`, `servers/studio` | État, contrats, admission, packages, jobs et MCP |
| `blender`, `hooks` | Opérations contrôlées, checkpoints et contexte de session |
| `skills`, `references` | Parcours de travail et documentation |
| `schemas`, `templates`, `workflows` | Contrats, dossier type et graphes Comfy à qualifier |
| `tests` | Tests de contrats/protocoles et données synthétiques |

## Documentation

- [Installer, configurer et démarrer](references/getting-started.md)
- [Déroulement et état du projet](references/production.md)
- [Proposition de méthode et revue du découpage](references/construction-review.md)
- [Board et patrons de fabrication](references/fabrication-board.md)
- [Contrôles des étapes et récupération](references/lifecycle-guards.md)
- [Packages](references/packages.md), [références visuelles](references/references-3d.md),
  [Comfy local](references/comfy-official.md), [Blender](references/blender.md)
- [Validation](VALIDATION.md), [historique](CHANGELOG.md),
  [contribution](CONTRIBUTING.md), [sécurité](SECURITY.md),
  [maintenance GitHub](references/repository-maintenance.md)

## Limites actuelles

Les exemples sont synthétiques : ils ne démontrent pas la fidélité d'un vêtement.
Les templates SD1.5 et Hunyuan doivent être adaptés et qualifiés sur les nœuds et
modèles présents. Aucun modèle n'est téléchargé automatiquement.

La construction des panneaux Cloth est fournie ; le placement, le fitting,
le bake, la retopologie, les UV, le rig et les exports restent des travaux
assistés à exécuter et à vérifier sur chaque asset. Les contrôles numériques
ne certifient pas l'apparence ni la véracité d'une preuve déclarée.

Les hooks et les scripts Blender ne constituent pas un bac à sable du système.
Une mutation interrompue bloque la suite jusqu'à restauration contrôlée. Un job
Comfy dont la soumission est incertaine n'est pas renvoyé automatiquement.

## Licence

Le code et la documentation sont sous [licence MIT](LICENSE).
Les moteurs, modèles, références fournis par l'utilisateur et assets produits
conservent leurs propres droits et conditions ; ils ne sont pas distribués ici.
