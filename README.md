# Atelier 3D

Le [contrôle de complétude des pièces](references/piece-completeness.md)
affiche la couverture locale et globale du candidat Blender, détecte absences
et doublons et empêche qu'un composant complet valide tout le vêtement.
Voir [la portée testée](VALIDATION.md) pour la vérification native restante.

Avant d’exécuter du code via Blender MCP, le plugin demande explicitement
l’autorisation de l’utilisateur et attend sa réponse affirmative. Voir
[le protocole Blender](references/blender.md). Cette consigne ne modifie pas
les permissions MCP de Codex.

La [préparation native des patrons](references/pattern-preparation.md) contrôle
la coupe et les correspondances, dérive un maillage régulier et mesure sa
préforme autour du corps avant tout Cloth. Elle conserve les patrons approuvés,
produit les vues neutres/wireframe et transmet sa géométrie exacte à l'assemblage.
Ses états `READY`, `NEEDS_CORRECTION` et `NEEDS_CLARIFICATION` restent distincts
d'une qualification physique ou d'une acceptation finale.

Le parcours `PATTERN_SEWN` dispose d'une [refonte locale de l'assemblage](references/pattern-assembly.md) :
préforme sourcée, Cloth court, fermeture bornée, consolidation géométrique,
détente continue et drapé distinct. Les patrons approuvés restent immuables.
Voir [VALIDATION.md](VALIDATION.md) pour la portée réellement testée ; une
consolidation ne qualifie pas le fitting, le comportement ou l'export.

Les [renforcements après l'étude OpenSew](references/opensew-improvements.md)
ajoutent la métrique source par face pendant Cloth, les contacts entre frames,
un enfilage mesuré et l'ordre explicite des couches. Leurs coupons ont une
portée limitée ; les anciens PASS gardent leur périmètre et le fitting réel
reste non qualifié. Ces améliorations locales de la version 0.6.7 sont
incluses dans la version 0.6.8.

[![CI](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml/badge.svg)](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plugin Codex pour préparer et produire des assets 3D à partir d'images de référence,
avec un choix de méthode par composant, des données de construction explicites et
une validation humaine aux étapes déterminantes.

**Version 0.6.8 — complétude des pièces et autorisation du code Blender.** Le runtime et ses contrats sont testés.
Le profil d'installation Windows est testé, avec découverte MCP et diagnostic
compatibles avec le manifeste Codex. Une
production complète sur un vrai vêtement ou un asset articulé reste à qualifier.
Voir [les résultats et limites](VALIDATION.md) et la
[release 0.6.8](https://github.com/leuzeus/atelier-3d/releases/tag/v0.6.8).
Le paquet portable contient le plugin et ses références ; les scènes, modèles,
configurations locales et sorties de production sont exclus.


La [préparation native du fitting](references/fitting-preparation.md) peut produire
une enveloppe auxiliaire depuis la référence évaluée du corps et un champ de
pose continu depuis les bords nommés des patrons et les os mesurés. Elle conserve
FlatRest, les pins fixes et les seuils physiques. Les recettes peuvent décrire
quelques profils de rigidité partagés et des renforts locaux : poids et maxima
Blender exécutés sont enregistrés et vérifiés. Ces préparations ne constituent
ni acceptation anatomique, ni simulation portée réussie, ni preuve visuelle.
Le diagnostic d'enfilage précise désormais les manques même sans collider.

La reprise vide utilise l'opérateur autorisé par le MCP officiel, sans
réinitialiser les préférences ni perdre ses add-ons ou sa connexion. Le test
interactif isolé vérifie son garde réel, les requêtes suivantes et la récupération.
Le test autonome de 0.6.3 ne couvrait pas ce garde. Une [sélection explicite du
corps source](references/body-source.md) produit sa pose évaluée figée sans
importer l'ancien vêtement. Elle ne crée pas de collider et ne valide pas les
repères anatomiques ou le fitting.

La version 0.6.3 permet l'inspection de capacité malgré des contacts refusés,
une [reprise native dans une scène vide et un fitting séparé](references/clean-construction-fitting.md),
avec conservation du témoin et des approbations exactes. Un placement rigide
optionnel exige un corps cible identifié et des repères homologues explicites.
Les pénétrations profondes sont refusées avant une projection destructrice.
La reprise propre du cas réel reproduit exactement les coordonnées du montage
réussi : aucune contamination cumulative n'est établie. Le proxy anatomique
reste NOT_QUALIFIED et le fitting réel n'est pas exécuté.

La version 0.6.2 rend l'inspection d'un candidat géométriquement refusé lisible,
avec les mêmes contrôles d'identité, rest, topologie et pins. Elle ajoute la
[préparation locale et le montage d'un groupe sélectionné](references/local-interfaces.md)
depuis les coordonnées cousues actuelles. Sur la fixture réelle de 17 panneaux,
le local puis le full sans collider passent à 18 images : écart maximal
0,1752 cm, étirement 0,8184–1,2379 et déplacement maximal 8,4330 cm.
Les seuils physiques restent inchangés. Le fitting réel, la stabilité longue,
la validation humaine et l'import Unreal restent à qualifier.

La version 0.6.1 ajoute le [montage par étapes](references/sewn-stages.md) :
`apply_sewn_result` reprend un résultat local PASS sans collider dans une copie
native, avec ses indices et reçus ; `simulate_sewn(purpose=assembly)` permet
l'assemblage complet libre ; `prepare_sewn_stage` conserve les coordonnées
cousues pour préparer les interfaces restantes puis introduire le mannequin
identifié pour un fitting distinct. Le parcours complet passe sur fixture.
Le transfert réel de 5 455 sommets passe aussi ; à cette version, l'assemblage réel
de 17 panneaux était refusé avant Cloth pour orientation d'emmanchure. Les essais
bornés de prépositionnement n'avaient pas produit de candidat admissible. Cette version
livre la continuité native sans qualifier le vêtement réel ou son fitting.

La version 0.6.0 permet de tester un [prépositionnement borné des panneaux](references/experimental-prefit.md)
dans l'opération `garment`, sur demande explicite et sans modifier les patrons.
Elle ajoute un raffinement optionnel de la triangulation et conserve les contrôles
finaux mesurés même après refus de qualité. Le cas réel échoue encore pendant Cloth :
le prépositionnement expérimental ne qualifie pas le vêtement et reste désactivé par défaut.

La version 0.5.9 précise le [diagnostic des déplacements Cloth](references/cloth-motion.md) :
excursion depuis le début de phase et incrément entre images évaluées, avec
sommet source, pièce, UV, bords nommés et poids de maintien. L'image qui dépasse
le budget est conservée dans l'historique. Les anciens diagnostics restent
lisibles sans inventer leurs incréments. Aucun seuil ni profil physique n'est
modifié ; ces mesures ne prouvent pas seules une instabilité ou un fitting accepté.

La version 0.5.8 ajoute une [fiche de fitting mesurée](references/measured-fitting.md) :
sections homologues corps/enveloppe, capacité sur un chemin fermé des lignes de
couture, aisance et incertitude. Les données manquantes restent NOT_QUALIFIED.
Une proposition alloue un déficit mesuré en cm sans modifier les patrons.
Des attaches natives provisoires peuvent maintenir une fermeture existante
pendant l'essai local ; elles ne deviennent pas des coutures permanentes et ne
qualifient pas full/freeze. Le dessin/appliqué des retouches, le montage progressif
et le fitting du vêtement réel restent à qualifier.

La version 0.5.7 conserve les diagnostics des probes physiques avant nettoyage :
profil exécuté, durée, coupons, supports, qualité et écarts. `inspect_sewing_failure`
distingue `backend_probe_simulation=FAIL` et `garment_simulation=NOT_EXECUTED`.
Un nouvel échec local invalide la qualification courante pour le lancement full,
en conservant les preuves historiques. Voir [le diagnostic des probes](references/probe-diagnostics.md).

La version 0.5.6 conserve un diagnostic lorsqu'un candidat `garment` est rejeté
avant Cloth : coutures et segments d'orientation, coordonnées source/3D,
cosinus et seuil, ou contacts initiaux par pièce, sommet et collider.
`inspect_garment_failure` le lit même pendant la récupération et après restauration.
Le candidat reste rejeté ; aucun reçu de construction ni PASS Cloth n'est accordé.
Voir [le diagnostic de rejet](references/garment-rejections.md).

La version 0.5.5 ajoute `inspect_sewing_placement` avant Cloth : écarts et
positions des coutures, bords source, poids de maintien, intersections des
segments de rapprochement et orientations vis-à-vis des colliders déclarés.
Chaque tentative native conserve aussi son rapport initial. Ces mesures guident
la préparation du montage ; elles ne valident ni le drapé ni le fitting.
Voir [la revue de prépositionnement](references/sewing-placement.md).

La version 0.5.4 ajoute un cadrage contrôlé du candidat avec `frame_view`, sans
édition de géométrie, de visibilité ou de caméra. Après un échec Cloth évalué,
elle conserve un diagnostic non accepté avec positions, mappings, déformations,
écarts par couture, pénétrations et projections SVG. Ces preuves restent lisibles
après nettoyage de l'essai et restauration du checkpoint. Voir le
[parcours de cadrage et diagnostic](references/viewport-diagnostics.md).

La version 0.5.3 conserve des reçus distincts et immuables pour chaque composant
et package. Elle permet de récupérer une preuve d'import historique depuis un
checkpoint lorsque le reçu unique d'un projet 0.4.0 a été écrasé par un autre
composant. La vérification précède la migration et conserve l'ancien mesh comme
diagnostic non validé. Voir [le protocole de reprise](references/blender-continuity.md).

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

## Templates ComfyUI réutilisables

Le [catalogue des templates](workflows/comfy/README.md) décrit les deux bases
enregistrées : `reference-sd15` pour préparer une image de référence depuis un
original et `hunyuan-multiview` pour reconstruire une partie volumique depuis
les vues de face et de gauche. Il fournit les paramètres, exemples et limites.

Studio charge le graphe API enregistré dans `workflows/comfy/registry.json`,
applique les paramètres déclarés et conserve le workflow exact de chaque job.
Réutiliser une base adaptée au besoin ; une nouvelle structure ou un workflow
externe exige une variante revue et enregistrée. La compatibilité doit être
validée sur les modèles et nœuds installés avant exécution. Les bases fournies
restent à qualifier ; elles ne génèrent pas les panneaux `PATTERN_SEWN`.

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

Le préformage textile n'exige pas Garment Tool. Il utilise les outils natifs
de Blender : `Simple Deform → Bend` pour courber les pièces simples, puis
Cloth pour le montage. Avant consolidation, `Rest Shape Key` conserve
`A3D.FlatRest` et `Dynamic Mesh` reste désactivé ; après consolidation, le repos
3D et les métriques 2D par face sont conservés séparément. Le backend est testé
sous Blender 5.2.2 LTS. Le MCP pilote les opérations dans une copie de travail ;
aucun add-on textile supplémentaire n'est à installer. Voir la
[recette de préparation et ses contrôles](references/pattern-preparation.md).

Après le remplacement d'une version installée, fermer puis rouvrir Codex avant
de reprendre la production : une conversation peut conserver les chemins de
l'ancienne copie. Voir [mise à jour et erreurs de hooks](references/getting-started.md#mise-à-jour-et-erreurs-de-hooks).

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
utilise **24 schémas JSON**. L'état canonique du projet est conservé dans SQLite
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
- [Templates ComfyUI : usages, paramètres et réutilisation](workflows/comfy/README.md)
- [Déroulement et état du projet](references/production.md)
- [Proposition de méthode et revue du découpage](references/construction-review.md)
- [Board et patrons de fabrication](references/fabrication-board.md)
- [Du board approuvé à une toile cousue](references/sewn-toile.md)
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

La recette native sépare contours précis, maillage de simulation et surface
cousue. Elle vérifie masse par sommet, contexte de collision et essais physiques
locaux avant la toile complète, puis conserve les ouvertures et pièces amovibles.
Les placements sont limités aux panneaux plats ou enroulés ; le fitting complexe,
le bake d’animation, la retopologie, les UV, le rig et les exports restent des travaux
assistés à exécuter et à vérifier sur chaque asset. Les contrôles numériques
ne certifient pas l'apparence ni la véracité d'une preuve déclarée.

Les hooks et les scripts Blender ne constituent pas un bac à sable du système.
Une mutation interrompue bloque la suite jusqu'à restauration contrôlée. Un job
Comfy dont la soumission est incertaine n'est pas renvoyé automatiquement.

## Licence

Le code et la documentation sont sous [licence MIT](LICENSE).
Les moteurs, modèles, références fournis par l'utilisateur et assets produits
conservent leurs propres droits et conditions ; ils ne sont pas distribués ici.
