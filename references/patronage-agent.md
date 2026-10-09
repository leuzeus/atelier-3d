# Rôle de patronage intégré au plugin

Le rôle **Patronage** prend en charge le dimensionnement d'un vêtement avant
son montage 3D. Il s'applique aux familles déclarées par les données du projet,
sans mannequin, pièce ou coordonnées propres à un vêtement dans ses calculs.
Son entrée permanente est le [skill patronage](../skills/patronage/SKILL.md).
L'orchestrateur l'utilise pour un vêtement à produire ou une correction de taille.

Ce rôle organise les services existants. Il ne crée pas une nouvelle méthode
géométrique ni une acceptation par son seul nom. Le runtime effectue les calculs ;
l'utilisateur décide du corps, de l'intention, des nouvelles coupes et des vues.

## Répartition des responsabilités

| Responsable | Propriété |
| --- | --- |
| Patronage | Fiche de mensurations, aisance, capacités source, écarts, propositions de variantes et contrôles des raccords |
| Orchestrateur | État SQLite, admission, runs, checkpoints, intégration Blender et livraison |
| Utilisateur | Anatomie cible, intention de coupe, adoption des patrons modifiés et revue visuelle |

La compétence métier est permanente dans le plugin. Elle ne déclenche pas
automatiquement un sous-agent de développement ni un processus en arrière-plan.

## Parcours de travail

1. Reprendre les références originales, le corps et les décisions acceptés.
2. Mesurer les trajets requis : tours, carrures, longueurs et pentes d'épaule,
   emmanchures, équilibre dos/devant, bras et poignets selon le vêtement.
   Chaque mesure conserve ses repères, trajet, pose, méthode et source exacte.
3. Appliquer l'aisance explicitement décidée pour mouvement, sous-couches et
   silhouette. Une catégorie ne fournit aucun nombre automatique.
4. Comparer les patrons aux lignes de couture avec leurs relations réelles,
   couches, crans, plis et prises de matière. Pour un devant ouvert, traiter la
   couverture, l'écartement et le recouvrement sans inventer un tour fermé.
5. Distinguer capacité insuffisante, guide/montage déformé, limite de méthode et
   mesure manquante. Une image ou un timeout ne produit pas un déficit chiffré.
6. Si nécessaire, préparer une variante calculée séparée, contrôler ses raccords
   et présenter la planche avant adoption. Puis reprendre les mesures dépendantes.
7. Transmettre la géométrie et les contrôles admissibles à la préparation native,
   puis à la toile numérique, au fitting et aux vues à examiner.

L'outil `studio_prepare_patronage_review` consomme `project_root`, `dossier_path`,
`specification_path`, `fit_profile_path` et un nouvel `output_dir` sous
`preparation/`. `design_decision_path` est optionnel et exige sa décision
numérique ; son état canonique est contrôlé et toute revue manquante ou révoquée
reste explicitement requise, sans empêcher la restitution diagnostique.
Le code recompile les sources,
réutilise les sections corporelles et trajets matière réellement mesurés,
authentifie leur provenance native et génère `report.json` et `report.md`.
Les trajets manquants restent incomplets. Les deltas ne sont calculés que pour
des trajets fermés correspondants ; ils ne répartissent pas les modifications
entre pièces ni n'adoptent une variante. Aucun calcul manuel de tableau n'est
nécessaire. Les références sont vérifiées avant et après ; aucun nouvel état
de gate ni scène n'est créé.

Une intention provenant d'un autre dossier reste une proposition diagnostique,
avec périmètre à réconcilier, même si sa décision originale est revue. Elle
ne devient pas une intention canonique du dossier courant. Les revues de fitting
sont relues à chaque frontière, y compris sans décision numérique optionnelle.
L'outil journalise et recontrôle les sources Python de `a3d/` et les contrats
JSON de `schemas/` pendant le calcul.

`refresh_body_regions=true` peut remesurer les sections obliques source dans de
nouveaux fichiers, après vérification des références originales et de leur
origine corporelle native. Si elles sont périmées, l'outil produit un supplément
et une fiche de référence dérivés dans son dossier de sortie. Il conserve les
anciens fichiers et ne transfère aucune revue. Une référence absente ou modifiée
reste un refus. La décision numérique et ses fichiers exacts restent vérifiés.
Si une section corporelle sert plusieurs mesures de couches ou composants,
ses cibles déclarent `measurement_id` pour identifier leur propriétaire ;
l'outil refuse une répartition implicite de l'aisance entre ces mesures.

Les autres services à réutiliser sont `studio_prepare_body_target`,
`studio_compile_production_dossier` et `studio_prepare_pattern_ease_variant`.
`studio_prepare_body_path_review(project_root, body_profile_path,
specification_path, output_dir)` mesure les frontières corporelles déclarées
par `source_joint` dans l'adapter du corps natif authentifié. Sa spécification
versionnée déclare les chemins, les budgets de lecture, géométrie, temps et
sortie ; les projections sont optionnelles. Le service écrit un rapport exact,
sa fiche de revue et un reçu dans un dossier neuf sous `preparation/`, sans
modifier le corps, la fiche originale, SQLite ou une gate. Une interface
ouverte, branchée ou multiple est refusée. Une courbe source fermée conserve
le statut `SOURCE_REGION_BOUNDARY_LENGTH` et `tailoring_homology: REVIEW_REQUIRED` :
elle ne remplace pas automatiquement un tour horizontal ou un trajet de col.
Les projections montrent les bords réels mais ne qualifient pas leur occlusion.

Dans la branche de développement, `opening_exploration` peut compléter cette
spécification avec `path_id`, `reference_plane: BODY_SAGITTAL`,
`front_anchor: UNIQUE_FRONTMOST_INTERSECTION`, `max_pairs`, `max_seconds` et
`max_output_bytes`. Le code intersecte la vraie boucle avec le plan sagittal
du cadre corporel, puis propose des paires de sommets dans son ordre
topologique. Il mesure séparément l'arc frontal omis et l'arc restant et
génère `opening-options.svg`. Une ambiguïté est refusée ; aucun point proche
n'est substitué. Le calcul et le SVG partagent un budget cumulatif et leurs
octets combinés restent bornés. L'acceptation du repère corporel n'adopte pas
ces ouvertures : aucune paire, aisance ou correspondance au patron n'est choisie.
Cette extension n'est pas encore chargée par l'installation 0701.

Avant de proposer une ouverture, vérifier la topologie assemblée de la ligne
source. Le diagnostic `CLOSED_PERMANENT_ENDPOINT_CYCLE` exige des indices de
sommets exacts et des ponts de coutures permanentes ; il ne soude pas par
proximité. Des extrémités séparées dans un patron à plat peuvent rejoindre
le même sommet d'une autre pièce. Dans ce cas, l'état d'une fermeture
fonctionnelle ne prouve pas que la ligne d'encolure est ouverte. La longueur
UV reste un trajet matière ouvert ; la preuve topologique seule ne crée
aucune homologie anatomique, capacité d'enfilage ou admission de fitting.

Le noyau de développement `a3d.open_front_reference` prépare une autre revue
depuis la pièce centrale explicitement déclarée `inner_front`, côté `center`.
Il mesure ses courbes matière et ses extrémités aux trois sections corporelles
déclarées, ses attaches et son retrait dans le cadre du corps. Il distingue
la matière source, sa projection dans le guide et le retrait physique entre
couches, encore non mesuré. La visibilité et les marges sont des intentions
humaines distinctes, à enregistrer sur les fichiers examinés. Le choix
« toute la largeur visible » conserve cette règle pour une future variante ;
il ne fige pas sa largeur aux valeurs du patron initial.
Le caller doit authentifier les packages, le corps, les guides et le replay
du maillage natif ; le noyau pur ne crée pas cette provenance. Cette méthode
concerne les vêtements ouverts avec une référence centrale déclarée. Une
référence absente ou ambiguë demande des données explicites ; elle ne peut
servir de règle universelle de dimensionnement pour un vêtement fermé.

La relecture des UV source d'un maillage natif synchronisé réutilise maintenant
son sampler de bord et sa gradation, avec le profil complet, son binding et
son journal de travail authentifiés. Le transport binary32 est reproduit pour
la gradation ; les ancres finales doivent retrouver exactement les doubles
source restaurés par le writer. Une enveloppe locale borne le replay, sans
réutiliser une ancienne horloge. Les observations d'un placement refusé peuvent
étayer ce diagnostic source, mais n'admettent aucun placement ou fitting.
Les options de compilation peuvent préparer des propositions de chemins depuis
les guides et les maillages exacts. Lire séparément compilation, préflight de
fitting et propositions ; une compilation complète ne qualifie pas la taille.

Voir [le corps cible](garment-body-target.md), [l'aisance](garment-fit-intent.md),
[les mesures source](limb-source-measurements.md) et
[les variantes calculées](pattern-ease-variants.md) et
[la préparation des révisions approuvées](reviewed-pattern-revisions.md) et
[leur adoption canonique](reviewed-source-adoption.md).

## Profil de sous-agent Codex fourni

Le package inclut [atelier3d-patronage.toml](../templates/agents/atelier3d-patronage.toml),
une définition réutilisable du même rôle. Il ne fixe ni modèle, ni effort de
raisonnement, ni permissions : ces réglages restent hérités de l'hôte.

Codex charge ses profils personnalisés depuis `.codex/agents/` du projet ou
`~/.codex/agents/`. Le profil livré dans `templates/agents/` n'est pas enregistré
automatiquement par le manifeste du plugin. Son activation native doit suivre
la configuration du projet hôte ; ne pas copier dans le profil utilisateur,
réécrire sa configuration ou lancer un sous-agent sous prétexte que ce template
est présent. Le skill reste l'entrée distribuée et découvrable du plugin.
Voir [la configuration officielle des sous-agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Portée actuelle

Les services corporels, les mesures de chemins source et les variantes bornées
existent déjà. L'adaptation complète d'un torse ouvert et la correspondance de
toutes les mesures de tailleur restent à développer et qualifier. Le rôle doit
les signaler plutôt que présenter des fonctions nouvelles comme disponibles.

Le noyau [de trajets ouverts](body-surface-paths.md) mesure maintenant les
polylignes des arêtes source entre extrémités déclarées, dans des régions
explicites. Il distingue longueur sur arêtes, corde et descente ; il ne
qualifie pas une géodésique lisse. Les premiers trajets d'épaule ont été
examinés sur le mannequin exact puis acceptés comme références corporelles.
La correspondance aux coutures du manteau ample reste distincte, notamment
pour une épaule tombante. La nouvelle option `surface_exploration` de la revue
corporelle est développée sur cette branche ; vérifier sa disponibilité dans
le runtime avant de l'utiliser.

Le premier outil de comparaison utilise le contrat de fitting existant pour
les tours corporels et trajets de matière déclarés. Il ne calcule pas encore
automatiquement toutes les carrures, longueurs et pentes d'épaule. Ces mesures
nécessitent leurs définitions et services dédiés ; les points cutanés déjà
présents ne sont pas relabellisés comme mesures de tailleur.

Ses sorties indiquent les valeurs réellement mesurées, les cibles approuvées,
les écarts calculables, les données manquantes, les fichiers avant/après et la
prochaine action admissible. Une proposition non revue ne lie aucun package.
Toutes les opérations Blender gardent leur autorisation exacte et les contrôles
du pipeline. La simulation, le fitting et la revue artistique restent distincts.
