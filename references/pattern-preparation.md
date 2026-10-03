# Préparer PATTERN_SEWN avant l'assemblage

`prepare_pattern_assembly` prépare et mesure les entrées du parcours cousu.
Cette opération n'exécute aucun Cloth, ne ferme aucune couture et n'accorde
aucune qualification physique, de fitting, de comportement ou d'export.
Elle produit une dérivation traçable des patrons, une recette et un diagnostic
de préparation, avant les transitions décrites dans
[le parcours d'assemblage](pattern-assembly.md).

Le résultat est l'un des trois états suivants :

| État | Sens | Suite autorisée |
| --- | --- | --- |
| `READY` | Les contrôles de préparation disposent des données nécessaires et n'ont pas trouvé de défaut bloquant sur ce candidat. | Poursuivre les essais d'assemblage natifs. Ce n'est pas un PASS Cloth ni un vêtement accepté. |
| `NEEDS_CORRECTION` | Un défaut mesuré empêche l'admission : métrique, maillage, placement, couture, collision ou appui contradictoire. | Lire sa localisation et corriger une nouvelle variante technique dans les budgets existants. |
| `NEEDS_CLARIFICATION` | Une décision ou une donnée source manque : plan, repère, intention d'ouverture, matière ou donnée de fabrication nécessaire. | Compléter la donnée ou demander le seul choix de conception réellement indéterminé. Ne pas inventer une validation. |

Un candidat non prêt est conservé pour diagnostic sans remplacer le candidat
courant. Un résultat `READY` peut devenir la nouvelle géométrie de préparation
active ; son prédécesseur reste archivé. Les sources approuvées, les anciens
reçus et les checkpoints restent conservés dans les deux cas.

## Entrées natives

Créer un fichier conforme à
[`pattern-preparation.schema.json`](../schemas/pattern-preparation.schema.json),
à partir du [template](../templates/pattern-preparation.json). Le template est
volontairement incomplet : il ne contient aucun faux hash de plan ou de dossier
et ne garantit pas `READY`.

```json
{
  "operation": "prepare_pattern_assembly",
  "arguments": {
    "component_id": "garment.coat",
    "recipe_path": "sewing/recipe-source.json",
    "preparation_path": "sewing/preparation.json"
  }
}
```

Fournir aussi `project_root` à `studio_blender_operation`, puis transmettre son
code exact au Blender de travail isolé. Utiliser les reçus et artefacts natifs
retournés ; un script de production ad hoc n'est pas nécessaire pour obtenir
la préparation ou ses vues.

| Champ | Contenu |
| --- | --- |
| `version`, `component_id`, `source_ref` | Version 1, composant exact, provenance des choix de préparation. |
| `migration` | Option explicite `{"retire_legacy_preparations": true}`, avec un `assembly_plan` sourcé obligatoire. Archive la recette ancienne et produit une nouvelle recette sans empiler les anciens préparateurs. |
| `regular_mesh` | Espacement nominal `spacing_cm`, minimum `min_spacing_cm`, distance de raffinement `refinement_distance_cm`, budget `max_vertices` et cible optionnelle `target_min_angle_degrees` (15° par défaut). Toutes les distances sont métriques. |
| `assembly_plan` | Référence `{path, sha256}` du plan de préforme, coutures, appuis et budgets. Sans ce plan, la dérivation visible ne constitue pas une préparation complète. |
| `construction_dossier` | Référence `{path, sha256}` du dossier exact lié à la planche de construction approuvée : droit-fil, crans, matières, couches, ouvertures et intentions de fabrication. L'opération retrouve ce dossier depuis la planche si le champ est omis ; un autre dossier est refusé. |
| `mass_policy` | `native_uniform_vertex` déclare la distribution scalaire native ; `require_exact_surface_density` exige une distribution surfacique exacte et ne doit pas être satisfaite par une approximation cachée. |
| `material_profiles` | Profils partagés, avec `id`, `source_ref`, IDs de `pieces`, `areal_density_kg_m2`, `category` (`main`, `lining`, `reinforcement`, `accessory`) et `cloth_profile`. `phase_base` désigne les réglages scalaires de phase ; un autre nom doit correspondre au profil régional natif réellement affecté à ces pièces dans chaque phase. `visual_material_ref` peut conserver une référence visuelle distincte de la physique. Déclarer explicitement les hypothèses. |

Les chemins référencés restent à l'intérieur du projet et les SHA doivent
correspondre à leurs fichiers réels. Une copie de recette préparée est un nouvel
artefact ; l'opération ne modifie pas le package ou la recette source en place.
Le plan produit est lié au nouveau mapping dérivé. Les bords et partenaires
sont reconstruits depuis leurs IDs et les paramètres communs de longueur d'arc,
pas par reprise d'anciens indices de triangles.

## Audit des patrons et maillage dérivé

L'audit conserve les contours 2D, IDs, bords nommés, embu, droit-fil et types
`permanent`, `closure`, `detachable`. Il confronte les coutures à leurs longueurs,
sens, extrémités et données de fabrication. Une discordance doit désigner la
pièce, le bord ou la couture concernée. Les crans et le droit-fil appartiennent
aux données source ; ils ne sont pas déduits d'une triangulation ou d'une image
de rendu. Leur absence ne justifie pas de les fabriquer.

Le maillage régulier est une dérivation de simulation, indépendante des contours
approuvés. Une répartition intérieure hexagonale et un raffinement local borné
alimentent la triangulation contrainte native. Les contours et ancres source
restent fixes. Les deux bords d'une couture partagent leur rééchantillonnage
normalisé de longueur d'arc même si leurs nombres de points source diffèrent.
Le mapping conserve les correspondances entre géométrie dérivée, panneaux,
bords et paramètres source.

Les crans identifiés du dossier sont insérés à leur paramètre d'arc exact dans
le rééchantillonnage commun ; ils ne sont pas arrondis au sommet le plus proche.
Les extrémités des bords nommés conservent les arrêts géométriques de couture.
Un cran de couture d'une pièce sur elle-même qui ne précise pas son côté reste
ambigu ; le rapport demande une clarification au lieu de lui inventer un bord.

La densité est choisie avant les essais physiques : taille nominale pour les
zones larges, densité adaptée aux détails et aux bords où elle est nécessaire.
Un contour dense n'impose pas une même densité partout. Le budget de sommets
et la taille minimale empêchent le raffinement illimité. Si les contraintes
de contour ne permettent pas la qualité demandée, conserver le refus et sa
localisation ; ne pas déplacer un contour approuvé pour améliorer une statistique.

Le rapport donne les effectifs et les distributions pertinentes : longueurs
d'arêtes, angles, aspects des triangles, surfaces et déformations. Les extrema
sont localisés par panneau, face et coordonnées UV source. Une moyenne seule
peut masquer une emmanchure très déformée ou quelques triangles presque plats.
Les métriques 3D sont confrontées aux métriques 2D source, avec les déformations
principales par face lorsque disponibles ; un bon ratio sur quelques arêtes
ne suffit pas à qualifier la métrique d'un triangle.

## Prépositionnement, appuis et matière

### Réutiliser les outils de déformation de Blender

Pour une courbure simple, le chemin natif utilise le modificateur Blender
`Simple Deform`, méthode `BEND`. Il ne réimplémente pas sa formule. Le cadre
orthonormal du panneau peut déclarer `native_bend`, avec `angle_degrees`,
`deform_axis`, `origin_cm` et `rotation_degrees` (Euler XYZ en degrés). L'origine
et la rotation du Bend sont exprimées dans le repère local du panneau, après
soustraction de `offset_uv_cm`. Le cadre extérieur place ensuite le résultat
autour du personnage, sans échelle.

Le plugin construit un objet temporaire par panneau dérivé, évalue le
modificateur par le graphe de dépendances Blender, vérifie la conservation des
sommets et des faces, puis conserve les correspondances avec les UV source.
Les paramètres, la version Blender et les empreintes sont tracés. Il réévalue
le modificateur après remeshing ; aucune ancienne liste d'indices ne définit
la courbure du nouveau maillage. L'évaluation Python hors Blender refuse
explicitement ce backend au lieu de lui substituer silencieusement un panneau
plat. Les contrôles de qualité, couture, déplacement et collision restent
communs aux différentes préformes.

Exemple de cadre pour un coupon de 10 × 20 cm, sans prétention de fitting :

```json
{
  "source_ref": "coupon métrique 10x20, axe longitudinal v",
  "origin_cm": [0, 0, 0],
  "u_axis": [1, 0, 0],
  "v_axis": [0, 1, 0],
  "native_bend": {
    "angle_degrees": 90,
    "deform_axis": "Z",
    "origin_cm": [0, 0, 0],
    "rotation_degrees": [-90, 0, 0]
  }
}
```

Une préforme `native_bend` entre dans le montage par une préparation `READY`
exacte. L'entrée directe historique `preposition` sans ce reçu est refusée
pour ce backend : elle ne doit pas contourner l'audit des déformations
principales ou des contacts entre panneaux.

Les axes doivent être explicites : un Bend Z courbe suivant X dans son propre
repère. Un panneau local `(u,v,0)` doit être présenté dans son plan neutre pour
que `v` reste longitudinal. Une rotation d'origine de −90° autour de X permet
cette disposition ; les signes et les dimensions sont vérifiés par un coupon
natif. Une courbure visible ne prouve pas la conservation de la métrique.

Garment Tool propose également `Edit Bend` avant la simulation. Cet add-on
n'est pas une dépendance installée ni une API appelée par ce parcours. Le
backend natif disponible évite de conditionner la préparation à son acquisition.
Pour une épaule ou un volume complexe, conserver une cage ou des sections
sourcées et une vérification locale ; un seul Bend ne devine pas la coupe,
l'enfilage, les repères ni l'aisance.

Références : [Bend natif](https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/simple_deform.html),
[API SimpleDeformModifier](https://docs.blender.org/api/main/bpy.types.SimpleDeformModifier.html),
[Garment Tool — Edit Bend](https://joseconseco.github.io/GarmentToolDocs/quick_guide/).

### Conserver les trois états

Le patron approuvé reste la référence 2D. Le maillage dérivé courbé est la
position initiale visible. Le vêtement assemblé constitue un troisième état,
issu des transitions de couture et de consolidation. Avant consolidation,
Cloth utilise `A3D.FlatRest` comme `Rest Shape Key`, avec `Dynamic Mesh`
désactivé, y compris après une reprise de montage. Le préformage ne devient
donc pas implicitement un nouveau repos physique.

Après consolidation permanente, le parcours déclare `A3D.AssembledRest` en 3D
et conserve les métriques 2D par face pour mesurer les déformations. Il ne
moyenne pas les positions de plusieurs îlots 2D pour créer un repos soudé.
Voir [Rest Shape Key](https://docs.blender.org/manual/fr/5.2/physics/cloth/settings/shape.html).

Placer le maillage dérivé près de sa position assemblée avec une préforme
explicitement reliée aux UV source. Les cadres rigides et cages de placement
du plan restent des guides de positionnement. La préforme ne remplace pas le
patron par une surface procédurale finale. Les petites translations et rotations
techniques doivent rester sourcées et bornées ; elles ne changent ni la coupe,
ni ses longueurs, ni le corps cible.

Un déplacement rigide du panneau ne lui donne pas de volume. Pour entourer le
buste, utiliser une cage courbe ou une préforme `arc_sections` : chaque section
associe une hauteur UV `v_cm`, un décalage `arc_offset_cm` et une polyligne 3D
`curve_cm`. Le paramètre `s = arc_offset_cm + u_direction * u` parcourt la vraie
longueur d'arc de la section. L'interpolation entre sections conserve une
correspondance explicite avec les UV ; elle n'utilise aucun indice historique.
Le domaine doit couvrir tous les points évalués : aucune projection aux
extrémités ou répétition périodique implicite ne masque un repère incomplet.

Des sections identiques extrudées courbent un panneau sans allongement continu.
Des sections variables ou des raccords d'épaule peuvent introduire du
cisaillement : leur métrique doit être mesurée sur les faces dérivées. Le corps
sert de repère et d'obstacle ; sa circonférence ne remplace pas celle disponible
dans les patrons. L'aisance et l'évasement restent présents dans la préforme.
Le rapprochement des coutures vient après cette mise en volume. Il ne doit pas
être chargé de tirer des panneaux encore plats à travers le mannequin.

Le rapport de flexion `bending` décrit les angles dièdres entre faces adjacentes
d'un même panneau. Il est distinct des déformations principales et ne constitue
ni une rigidité matérielle mesurée, ni une validation Cloth. Une forte courbure
peut être compatible avec une faible déformation ; une faible déformation seule
ne prouve jamais que le panneau est convenablement placé autour du corps.

La préparation mesure le déplacement depuis le placement métrique dérivé et
applique le budget du plan avant de déclarer `READY`. La transition suivante
consomme exactement le mesh préparé et son reçu ; elle ne réapplique pas une
ancienne préforme sur les coordonnées obtenues. Les bornes métriques de la
recette restent obligatoires même si un plan propose des bornes plus permissives.

Une ancienne préforme déformée ne devient pas admissible parce qu'on en copie
les positions sur une nouvelle triangulation. Pour un cas déjà déformé,
repartir des placements métriques source et comparer les mesures avant/après.
Une diminution du stretch ne prouve pas que les manches sont enfilées, que les
coutures sont assez proches ou que le vêtement évite le corps.

L'enveloppe auxiliaire est identifiée séparément du corps cible. Un squelette
ajouré requiert un auxiliaire approprié, mesuré et examiné visuellement.
La préparation vérifie le contexte déclaré et mesure ses contacts avant Cloth,
y compris lorsqu'un futur assemblage demande `collision.mode="drape_only"`.
Une pénétration profonde reste un défaut de placement/enfilage ; ne pas relever
le seuil, déplacer le corps ou projeter arbitrairement tous les sommets à sa
surface. La classification conserve aussi les intersections entre panneaux.

Conserver séparément les appuis temporaires, les appuis de drapé et les attaches
fonctionnelles. Reprendre leurs IDs, bords et poids exacts ; préciser toute
reclassification technique. Les appuis de drapé sont conservés pendant le
montage. Les appuis temporaires seront retirés progressivement par les étapes
natives suivantes, sans changement silencieux des poids source. Les contraintes
incompatibles restent des défauts explicites.

La masse totale, la densité surfacique demandée et la distribution effectivement
possible doivent apparaître séparément. Le profil Cloth natif utilise une masse
scalaire par sommet. `native_uniform_vertex` peut conserver la masse totale
tout en créant une densité locale différente si les aires tributaires des
sommets varient. La régularisation réduit ce problème sans rendre la distribution
exacte. Le rapport expose cette variation ; il ne prétend pas appliquer une
masse indépendante à chaque sommet. Des profils de densités différentes ou
l'exigence d'une densité surfacique exacte nécessitent une capacité réellement
prise en charge, sinon une clarification ou un refus explicite.

La catégorie de matière ne modifie pas à elle seule sa rigidité. Un renfort
déclaré avec `phase_base` garde la physique commune : cette hypothèse doit être
visible, et ne constitue pas une caractérisation de son comportement. Les
profils régionaux réutilisent les capacités natives existantes et leurs poids ;
aucun groupe d'appui ne sert de distribution de masse déguisée.

## Sorties et revue

L'opération retourne des références `{path, sha256}` vers le maillage dérivé,
le mapping de couture, la recette préparée, le plan d'assemblage lié au mapping
courant et son reçu. Elle conserve un `.blend` versionné et un rapport comprenant
statut, métriques, localisations des défauts, appuis, masse et provenance.
Lire les champs réellement produits ; un artefact manquant doit rester signalé.

Les vues natives de face, profil, dos et les détails d'emmanchure sont produites
sur ce candidat, en modes lissé et filaire. Les vues aident à examiner silhouette,
orientation, densité, zones surraffinées, contacts et séparation des couches.
Le mode lissé ne corrige pas les triangles ni la métrique source. Il ne doit
pas masquer une géométrie insuffisante ou être confondu avec un drapé physique.

Examiner les pixels avant toute conclusion visuelle. Un rapport peut indiquer
que les fichiers de rendu existent ; cela ne signifie pas qu'ils ont été
inspectés ni approuvés. Garder distincts : préparation mesurée, revue des images,
fitting, comportement et acceptation artistique.

## Reproduction sur le cas réel

Le test `tests/native_pattern_preparation_real.py` se lance avec
`scripts/run_pattern_validation.py`, dans une nouvelle sortie sous
`work/pattern-preparation-20261003` sur G:. Il copie le témoin réel conservé,
réassocie seulement la session du clone, appelle l'entrée native et compare
la préparation obtenue à la géométrie historique. Il ne commande jamais la
scène Blender actuellement connectée et n'écrit pas dans le projet consommateur.

Les originaux, packages, reçus, patrons, mappings et base sont inventoriés avant
et après. TEMP, TMP, profil Blender et sorties restent sur G:. Aucune simulation
de montage, fermeture, consolidation, détente ou drapé n'est lancée par ce test.
La nouvelle triangulation et le placement sont jugés sur leurs propres mesures,
sans transfert des anciens PASS de montage libre.

Pour les panneaux plans, le témoin utilise les cadres rigides métriques source.
Les cylindres des manches et du col utilisent une cage rectangulaire UV couvrant
les contours approuvés, avec des échantillons d'arc espacés d'au plus 0,5 cm.
Ses cibles sont recalculées à partir de la formule de placement source ; elles
ne proviennent pas du mesh simulé historique ni de ses indices. Cette cage
indépendante couvre aussi les nouveaux échantillons de bord et les crans.

Ce témoin de placement rigide sert de comparaison. La variante
`tests/native_pattern_preparation_volume.py` construit ensuite un buste courbe
avec le même package et les mêmes limites. Elle utilise les sections issues
des bords nommés, les mesures géométriques du thorax et les os du reçu R21.
Elle rapproche rigidement les axes des manches des bras et conserve le col
comme diagnostic indépendant. Les repères anatomiques et l'enveloppe restent
à qualifier ; la présence d'une courbure ne suffit pas à autoriser le Cloth.

Le helper `a3d/preform_volume.py::volume_frames` est un adaptateur de recette
pour une convention UV commune explicitement déclarée, avec les rôles
devant/centre/côté/dos et leurs bords nommés. Il refuse une disposition UV qui
ne respecte pas cette convention. Ce n'est pas une inférence universelle de
coupe. Le contrat natif `arc_sections` permet d'autres repères et d'autres
dispositions UV explicitement sourcées. Les coutures restent associées par leurs
IDs et paramètres d'arc, indépendamment de cet adaptateur de placement.

Le rapport `volume-guide-hypothesis.json` sépare les sections source brutes des
sections du guide après lissage. Le guide est une hypothèse de placement :
son lissage ne réécrit ni les patrons ni leurs longueurs. Les premiers essais
qui rapprochent les épaules mais dépassent les bornes de déformation sont
conservés comme refus. Le candidat retenu doit encore satisfaire les contrôles
de maillage, de collision, de couches et de fitting avant toute acceptation.

`tests/native_pattern_preparation_bend.py` reprend ce témoin réel avec le
modificateur natif pour les huit pièces de manches et le col. Le rayon, les
repères et les patrons sont conservés ; le buste complexe reste guidé par ses
sections sourcées. Ce témoin vérifie la réutilisation de Blender sans présenter
un cylindre ou une préforme comme un fitting qualifié.

Pour repartir d'une ancienne recette, déclarer `migration.retire_legacy_preparations`
avec la valeur `true` et fournir le plan de remplacement sourcé. Le plugin archive
la recette d'entrée octet pour octet dans `legacy-recipe.json` puis retire
uniquement les sept entrées redondantes (`experimental_prefit`,
`interface_preparation`, `panel_mount`, `fitting_placement`, `fitting_pose`,
`contact_recovery`, `fitting_tacks`) dans une nouvelle `recipe.json`. Le reçu
conserve leurs valeurs exactes et les empreintes avant/après. Les autres champs,
dont coutures, pins, limites et masse, restent inchangés. Reclassifier les appuis
explicites dans le plan ; leur transition est mesurée séparément.
Aucun PASS n'est transféré. Sans cette migration explicite, le chemin nominal
refuse les préparateurs redondants. Pour continuer la géométrie ancienne sans reconstruire les patrons,
utiliser la transition `migrate` documentée dans le parcours d'assemblage ;
elle exige son reçu source vérifiable et ne remplace pas cet audit de préparation.

Les valeurs historiques de contact doivent garder leur contexte : environ
7,81 cm après une préparation de pose R21, contre environ 9,56 cm sur un autre
candidat libre examiné ensuite. Elles ne sont pas des variations de tolérance.
Comparer le nouveau candidat au témoin exact relu par le test ; ne pas traiter
un écart de date, de pose ou de mesh comme une amélioration mesurée.

Consulter [VALIDATION.md](../VALIDATION.md) pour les exécutions effectivement
réalisées et leurs limites. La présence de cette recette et du test ne constitue
pas leur exécution. Même `READY` laisse le fitting et le comportement non qualifiés
tant que leurs preuves natives et leur revue visuelle n'ont pas été obtenues.

## Migration des primitives

| Fichier / fonction | Décision | Raison et migration |
| --- | --- | --- |
| `a3d/sewing.py::prepare_boundaries`, `resample_parameters` | Conserver, étendre | Même domaine d'arc et mêmes partenaires ; l'argument optionnel ajoute les crans exacts aux deux côtés. Les anciens appels restent valides. |
| `blender/sewing.py::triangulate`, `build_mesh` | Conserver les primitives, remplacer la préparation nominale | La préparation ajoute une grille triangulaire graduée et un raffinement borné. Les anciens appels sans configuration régulière gardent leur comportement. |
| `a3d/pattern_preparation.py` | Nouvelle entrée de calcul | Audit du dossier approuvé, densité, repos par face, déformation principale et localisations ; ne réécrit aucun patron. |
| `blender/preform.py::preform_coordinates` et `_bend_panel` | Réutiliser Blender | Le modificateur natif évalue les courbures simples. Convertir les paramètres source de pose et de rayon en cadre et `native_bend`, puis réévaluer depuis les UV à chaque dérivation. Les cages historiques restent lisibles. |
| `a3d/pattern_assembly.py::preform_coordinates`, variant `arc_sections` | Étendre la primitive | Mettre en volume les patrons par des sections 3D paramétrées en longueur d'arc. Conserver l'UV, les partenaires et les contrôles de déformation ; remplacer les cadres plans insuffisants par un nouveau plan sourcé. |
| `blender/pattern_preparation.py::prepare_pattern_assembly` | Entrée native nominale | Produit le candidat, les rapports, la nouvelle recette, le plan, les vues et le master avec checkpoint. |
| `blender/pattern_preparation.py::migrate_preparation_recipe` | Migration additive | Archive les anciens champs et retire leur exécution de la nouvelle recette. Aucun reçu ou PASS physique n'est transféré. |
| `blender/pattern_assembly.py::transition_pattern_assembly` | Conserver, adapter l'entrée | Un reçu `READY` exact est consommé par `preposition`, sans remesher ni rejouer le placement. |
| `blender/preparation_review.py` | Séparer du maillage de simulation | Copies d'affichage à géométrie identique ; rendu neutre lissé et filaire. Le master montre le candidat et ses colliders, sans superposer l'ancien montage. |
| Cylindres calculés dans les anciens préparateurs / cages des premiers témoins | Remplacer dans les nouvelles recettes simples | Utiliser `native_bend` ; conserver les anciens paramètres et reçus pour comparaison, sans rejouer leurs positions sur un nouveau maillage. Les sections complexes sourcées restent disponibles. |
| `experimental_prefit`, `panel_mount`, `interface_preparation`, `fitting_placement`, `fitting_pose`, `contact_recovery`, `fitting_tacks` dans les anciennes recettes | Déprécier l'empilement nominal | Garder les sources et reçus historiques ; activer la migration explicite et fournir un seul plan sourcé. Les fonctions restent disponibles pour la reprise historique. |

Aucune suppression de fonction historique pendant cette migration. Changer une
densité, un affichage ou un placement dérivé ne révoque pas l'approbation du dessin
source inchangé. Une correction de coupe exige un nouveau package séparé avec
différences mesurées et la décision de conception correspondante.
