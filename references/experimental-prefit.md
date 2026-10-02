# Prépositionnement expérimental — 0.6.0

Cette option sert à tester un rapprochement initial de panneaux avant Cloth.
Elle est désactivée par défaut et s'exécute dans `garment` / `rebuild`, sur la
copie de travail, après les contrôles du package et du board approuvé.
Elle ne remplace ni le contrôle des dimensions/aisance ni l'essai local physique.

Le solveur géométrique conserve les distances du patron comme objectif local,
avec des références explicites et des contacts sur les colliders déclarés.
Les partenaires permanents partagent des variables internes du solveur ; les
indices du mesh demeurent distincts. Aucun contour, rest 2D, bord nommé,
correspondance, pin, fermeture ou lien amovible n'est réécrit ou soudé.
NumPy est utilisé uniquement dans le Python fourni par Blender.

Ajouter `experimental_prefit` à une copie de la recette, en adaptant les noms
aux pièces et coutures réellement présentes :

```json
{
  "experimental_prefit": {
    "experimental": true,
    "source_ref": "analyse:essai-de-rapprochement-01",
    "seam_ids": ["couture-epaule"],
    "reference_pieces": ["col"],
    "fixed_edges": [
      {"piece": "devant", "edge": "hem", "exclude_joined_vertices": true}
    ],
    "iterations": 30,
    "clearance_cm": 0.5,
    "max_displacement_cm": 30,
    "min_fraction": 0.125,
    "max_backtracks": 3
  }
}
```

Chaque composante connexe sélectionnée exige une pièce de référence. Les
repères fixes contradictoires sont refusés. L'exclusion des sommets partenaires
d'un bord fixe doit être déclarée explicitement. `source_ref` documente
l'hypothèse ; ce texte n'est pas une preuve de mesure ni une approbation humaine.
Seules des coutures source `permanent` sont admissibles. Le budget de déplacement
ne peut dépasser celui de la recette physique. Le solveur calcule une cible,
puis applique une fraction bornée ; chaque refus divise cette fraction par deux,
dans le nombre maximal déclaré, sans descendre sous `min_fraction`.

Le placement initial doit déjà passer les contrôles natifs. Chaque candidat
est vérifié avec les mêmes seuils d'angles, déformation, direction des coutures,
contacts, rest et pins. En cas d'échec, le candidat revient à son placement
initial ; l'opération reste refusée et son diagnostic est conservé. Utiliser
`restore_checkpoint` avant une nouvelle mutation après un échec guardé.

Le reçu `garment` et son mapping exposent `experimental_prefit` :
`PREPOSITIONED_NOT_SIMULATED`, fraction appliquée, déplacement maximal,
écarts de couture avant/après, historique géométrique, refus intermédiaires
et identité des colliders. `accepted=false`, `simulation=NOT_EXECUTED` et
`visual_validation=NOT_EXECUTED` demeurent explicites. Un écart peut augmenter
sur une couture : inspecter les mesures et les pixels avant l'essai local.
Le binding de recette inclut l'option ; la modifier exige un rebuild et de
nouveaux essais. Les règles de local/full/freeze restent applicables.

Le cas réel isolé présente encore un échec Cloth après prépositionnement.
La livraison permet son expérimentation ; elle ne certifie pas la robe.

## Raffinement du maillage dérivé

`mesh.quality_refinement` est aussi optionnel :

```json
{"target_min_angle_degrees": 4, "max_passes": 16, "max_added_vertices": 2000}
```

Il ajoute des points à la triangulation dérivée sans déplacer ni supprimer les
ancrages du contour. La cible doit dépasser le seuil d'acceptation existant.
Les budgets de passes, ajouts et sommets globaux provoquent un refus lorsqu'une
cible est inaccessible ; ils ne changent pas la coupe. L'option change le
binding du mesh. La masse totale ou densité prescrite est conservée ; une
résolution différente change la masse et force natives par sommet.

## Diagnostics finaux

Après une évaluation Cloth complète, un refus de qualité conserve
`final_quality` et `final_checks` avec les violations mesurables de qualité,
la pénétration et l'écart maximal des coutures. Le premier refus reste celui
du contrôle initialement prioritaire. Un arrêt avant la dernière image peut
laisser ces contrôles finaux absents : ne pas inventer un résultat final.
