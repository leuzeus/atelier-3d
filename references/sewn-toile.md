# Du board approuvé à une toile cousue

Le board approuve le découpage et les données de fabrication. L'exécution Cloth
emploie une **recette technique séparée**, préparée par l'agent à partir de ces
données et de la scène réelle. Aucun formulaire humain supplémentaire n'est
nécessaire pour régler la densité, les forces ou les collisions. Une modification
de conception des patrons, des références ou du découpage conserve les règles de
nouvelle revue du [board](fabrication-board.md).

## Parcours court

Toutes les opérations ci-dessous passent par `studio_blender_operation`, puis
son code exact est transmis au MCP Blender connecté. Vérifier la scène, appeler
`prepare` pour créer la copie de travail, puis conserver cette copie connectée.
Si la session existe déjà, utiliser `resume` pour en sauvegarder un checkpoint,
sans perdre les modifications en mémoire. Après une mise à jour, demander un
nouveau code exact au Studio actualisé et contrôler `runtime.version` dans le
résultat. Voir [la reprise et les panneaux legacy](blender-continuity.md).

1. Extraire le package approuvé dans un nouveau répertoire du projet. Préparer
   le mannequin auxiliaire, ses dimensions, sa pose et son modifier Collision.
   Écrire `recipe.json` selon `schemas/sewing-recipe.schema.json` ; le template
   est un exemple synthétique à adapter, pas un réglage prêt pour une robe.
2. Appeler `garment` avec `package_dir` et `recipe_path`. Cette opération construit
   les panneaux dérivés, leur forme de repos à plat et les paires de couture.
   Elle contrôle le placement avant de démarrer le solveur.
3. Appeler `inspect_sewing_placement` avec `component_id`, `recipe_path` et suivre
   [la revue mesurée de montage](sewing-placement.md). Examiner les écarts,
   supports, trajets dans les colliders, orientations et un rendu avant Cloth.
   Utiliser d'abord les placements natifs existants et conserver leurs paramètres.
4. Appeler `simulate_sewn` avec `component_id`, `recipe_path`, `phase=mount`,
   `scope=local`. Trois petits essais isolent gravité, couture de deux bords et
   contact. Ensuite, le sous-ensemble réel choisi dans `trial_pieces` est testé
   avec la recette du projet : pour un vêtement à manches, choisir la manche et
   son emmanchure. Les essais synthétiques ne remplacent pas cet essai local.
5. Après PASS technique local, appeler la même opération avec `scope=full`.
   Examiner les rendus de face, profil et dos avec les originaux. Pour une phase
   de drapé complémentaire, passer à `phase=drape` et refaire local puis full.
6. Appeler `freeze_sewn` avec `component_id` et `recipe_path`. Le runtime crée
   une copie de surface cousue et archive le maillage de simulation. Poursuivre
   les revues de reconstruction, d'assemblage et de silhouette existantes.

Exemple d'arguments pour l'essai local :

```json
{
  "component_id": "garment.coat",
  "recipe_path": "recipe.json",
  "phase": "mount",
  "scope": "local"
}
```

## Trois représentations distinctes

| Représentation | Rôle et invariants |
| --- | --- |
| Contours source et package | Patrons précis, points, IDs et bords nommés approuvés. Jamais réécrits par le solveur. |
| Maillage de simulation dérivé | Bords rééchantillonnés par longueur d'arc, à densité bornée et erreur de corde déclarée ; triangulation contrainte dans Blender. Mapping conservé vers chaque bord source. |
| Surface cousue de travail | Copie des positions simulées ; union des seules paires permanentes déclarées. La source et le mapping restent conservés. Ce n'est pas encore une retopologie de livraison. |

Deux bords source peuvent avoir des nombres de points différents. Le runtime
leur donne les mêmes paramètres d'échantillonnage pour construire une
correspondance explicite. Il vérifie longueur, sens, embu déclaré, sommets
effondrés, triangles dégénérés et étirement repos/placement. Une forte densité
de contour n'impose plus la même densité de simulation.

`seams` type chaque lien : `permanent`, `closure` ou `detachable`. Seules les
coutures permanentes produisent des ressorts puis des unions à la consolidation.
Les fermetures, pièces amovibles et bords libres restent distincts. Les attaches
fonctionnelles de ces liens restent à réaliser à l'étape de comportement.
Une proximité géométrique ne justifie jamais une soudure. Pour un ancien package
sans `kind`, déduire le type des données de fabrication approuvées ; si elles ne
tranchent pas une ouverture, demander ce choix de conception plutôt que l'inventer.

## Recette et contexte réellement exécutés

- `mass` utilise soit une masse totale en kg, soit une masse surfacique en kg/m².
  Blender attend une masse **par sommet** : `masse_totale / nombre_de_sommets`.
  L'ancien `material.mass_kg` du package n'est jamais affecté directement à ce
  champ. Le sous-ensemble local reçoit la fraction de masse correspondant à son aire.
- Le plafond de couture est fini : `mass_per_vertex_kg * sewing_force_per_kg`.
  L'amortissement est rapporté à `damping_reference_mass_kg`. Ce profil est un
  point de départ testé sur fixtures ; il ne garantit pas une réponse physique
  identique à toutes les résolutions. Les valeurs effectivement retenues par
  Blender sont contrôlées, notamment contre les bornes qui les tronqueraient.
- `placements` décrit chaque panneau, à plat ou enroulé sur un cylindre, en cm.
  Il place les sommets dérivés du patron ; il ne remplace pas le patron par un
  tube procédural. Des formes complexes demandent un placement adapté et vérifié.
  Cette version ne fournit pas d'adaptateur de fitting arbitraire.
- La scène utilise des mètres (`scale_length=1`). Le mesh simulé conserve une
  transformation identité, une clé `A3D.FlatRest` et des poids de maintien
  explicites. Les modifiers de rendu/rig restent hors du mesh de simulation.
- `colliders` identifie les objets auxiliaires par nom, dimensions, empreinte
  de géométrie évaluée et épaisseurs Collision. `inspect` retourne ces mesures.
  Le mannequin peut être auxiliaire, sans être un composant livré de l'asset.
  Il doit être visible, fermé, correctement orienté et avec échelle appliquée.
  La simulation complète exige un mannequin déclaré. Seul un essai libre local
  peut déclarer son absence avec une raison explicite.
- La collection de collision contient uniquement les objets déclarés. Le groupe
  `A3D.SeamSelfExclusion` exclut de l'autocollision les triangles au voisinage
  immédiat des coutures ; il n'exclut pas le contact avec le mannequin. Les noms
  **et les poids** des groupes font partie du contrôle du contexte.
- Chaque tentative recrée un cache court sans cache disque. Les frames sont
  évaluées explicitement, avec déplacement, écart de couture, qualité finale
  et pénétration mesurée. Un retour API sans mouvement effectif est un échec.

Les paramètres, la pose du mannequin, le mesh, les pins, la version Blender et
la phase lient le résultat local au candidat complet. Leur changement impose
un nouvel essai technique. Il ne révoque pas le board si ses données restent
identiques. Après deux échecs complets, un nouvel essai local réussi est requis.
Les échecs et progrès restent dans `.a3d/blender/sewing/attempt-*`.

Pour un échec avant l'essai du vêtement, suivre [le diagnostic des probes](probe-diagnostics.md).
Lire le stade d'exécution : probe FAIL ne signifie pas vêtement exécuté.
Un nouveau FAIL local invalide la qualification courante pour full ; les preuves
historiques restent conservées et un nouvel essai local PASS est requis.

Après une erreur, utiliser `restore_checkpoint` avant de poursuivre. Si la
recette de maillage, de placement ou de coutures a changé, reconstruire un
nouveau mesh dérivé avec `garment(..., rebuild=true)`. Le précédent est archivé
dans la scène, avec sa géométrie intacte ; seuls les meshes de simulation non
acceptés sont remplaçables. Ne pas retoucher le mapping pour contourner le contrôle.

## Scripts personnalisés et limites

### Sens d'enroulement cylindrique

Chaque placement `mode="cylinder"` accepte `mirror_u`, booléen facultatif, `false`
par défaut. Avec `true`, l'angle devient `-(u-origin_u)/radius_cm`. Le rayon reste
positif ; la hauteur locale, les contours, le rest 2D et les identifiants des
coutures sont conservés. Avec une rotation `[90,0,0]`, une position `[0,0,149]` et
une origine `[0,0]`, cela donne `(-r*sin(u/r), -r*cos(u/r), 149+v)`.

L'option est réservée au cylindre. Elle fait partie du hash des placements : sa
modification exige un nouveau maillage dérivé et un nouvel essai local, sans
réapprobation du découpage inchangé. Les contrôles de déformation, sens des coutures,
collisions et déplacement restent actifs. Un sens représentable ou des tangentes
admissibles ne prouvent pas un placement correct du col ou une simulation stable.

### Exécution personnalisée

Préférer les opérations natives ci-dessus. Un `run_script` de purpose `simulate`
doit aussi fournir un plan avec `sewing_recipe` et `phase`, respecter les mêmes
paramètres et avoir un essai local correspondant. Une recréation du modifier
avec d'autres paramètres, un script sans évaluation terminée ou une couture
hors tolérance sont refusés. Ce mécanisme reste du Python de confiance, sans
bac à sable ni limiteur de temps. Il ne produit pas le reçu natif nécessaire à
`freeze_sewn` ; utiliser `simulate_sewn` pour ce parcours.

Les contrôles de pénétration mesurent les sommets contre les surfaces de
collision ; ils ne constituent pas une preuve exhaustive d'absence de croisement
entre triangles. L'examen des pixels, du fitting et du mouvement reste nécessaire.
Les profils matière, les placements complexes, le bake d'animation, les UV, la
retopologie de jeu et l'import Unreal restent à qualifier sur l'asset réel.
Ne pas relancer automatiquement de longues variantes ou changer de pipeline
après un refus technique : diagnostiquer le petit cas concerné.

Avant de varier les profils, suivre [le fitting mesuré](measured-fitting.md). Une fermeture provisoire est un maintien local jetable, pas une couture permanente. Retirer les attaches et refaire local avant full/freeze.
