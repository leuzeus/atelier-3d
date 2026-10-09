# Crans source et maillage physique dérivé

Un cran du dossier désigne une position sur un arc source, avec son ID, son
symbole, sa pièce et son côté de couture. Cette position matérielle ne requiert
pas un sommet Cloth. La préparation régulière conserve le cran et ses UV source
sans imposer sa fraction comme échantillon physique supplémentaire.

## Identité source et priorité des vrais sommets

`prepare_boundaries` reconnaît un sommet source uniquement par l'égalité exacte
de la fraction avec son abscisse curviligne normalisée. Sa provenance
`SOURCE_VERTEX` et ses coordonnées d'origine restent prioritaires si une
interpolation ultérieure atteint la même clé de stockage existante. Deux IDs de
sommets source distincts à cette clé provoquent un refus ; ils ne sont pas
fusionnés. Les règles existantes des clés, de leur arrondi et des partenaires de
couture restent les mêmes.

Tous les vrais coins et les extrémités nommées restent protégés. La préparation
régulière protège aussi explicitement l'origine du contour cyclique, déjà exigée
par son postcontrôle de coins, même lorsque ce point est une subdivision droite.
La préparation historique sans résolution régulière conserve ses paramètres.

Chaque contour expose `sample_provenance`, indexé comme `polygon`. Une entrée
identifie soit le vrai `source_vertex`, soit le `source_chain` et le
`source_parameter` interpolés, avec sa clé de périmètre et son indice local.

## Liaison d'un cran

Le rapport `regular_preparation_sampling` déclare
`source_notch_binding_version: 1`,
`source_notch_policy: MATERIAL_REFERENCE_WITHOUT_REQUIRED_PHYSICAL_VERTEX` et
`notch_index_space: PIECE_BOUNDARY_LOCAL`.

Chaque ligne de `source_notches` conserve le `source_mark` complet, le symbole,
l'ID, la pièce, le côté, la fraction locale exacte, le bord et la chaîne source,
leur empreinte, et `source_uv_cm`. La fraction commune utilise l'orientation
déclarée ; les positions explicites des deux côtés ne sont pas arrondies pour les
rendre identiques.

Deux liaisons sont possibles :

- `BOUNDARY_VERTEX` : un sommet physique existant porte exactement les UV et la
  position source du cran. Le rapport fournit `boundary_vertex` et
  `physical_common_parameter`. Les anciens champs `common_sample` et
  `derived_boundary_vertex` existent uniquement dans ce cas.
- `BOUNDARY_SEGMENT` : le rapport donne les deux `boundary_vertices`, leurs
  `physical_common_parameters` et les `weights` d'interpolation sur l'arc de
  couture orienté. Il ne crée aucune particule, paire de couture ou contrainte.

Ces indices appartiennent **au contour local de la pièce**, avant triangulation.
Ils ne sont pas des indices globaux de Cloth. Dans un payload natif construit par
`blender.sewing.build_mesh`, la conversion explicite est
`payload['panels'][piece]['boundary'][local_index]`, qui contient déjà la
correspondance native et le décalage de la pièce. Une liaison de segment doit
convertir ses deux extrémités ; utiliser directement ses indices locaux comme
indices globaux est incorrect.

`reconstructed_uv_cm` et `numeric_reconstruction_residual_cm` décrivent le calcul
avec les nombres flottants. Le résidu est une observation et ne définit aucune
tolérance ni gate. L'identité du cran reste `source_uv_cm` recalculée depuis l'arc
original. Une ligne enregistrée peut être contrôlée par re-dérivation ; des UV,
poids, propriétaires ou provenances réécrits sont refusés.

Une couture unaire conserve deux liaisons distinctes pour ses deux côtés. La
position d'un cran unaire inversé sans côtés explicites reste ambiguë hors du
milieu exact, comme auparavant.

## Vérification et portée

Les tests portables couvrent les voisins flottants d'un vrai coin, les conflits
d'identité, les crans sur des coins exacts ou entre sommets, l'origine cyclique,
les côtés unaires, les liaisons JSON réécrites et l'immuabilité des entrées. Les
contraintes physiques explicitement requises restent protégées et une arête
source réellement trop courte reste un échec de qualité.

Le replay pur des deux packages réels, original et variante de manches acceptée,
contrôle tous les coins source et les fractions originales sans écrire les
packages, le dossier ou MAIN. Cette vérification ne mesure ni triangulation
Blender, ni contact, ni Cloth, ni fitting. L'ancien refus natif et son audit
restent historiques ; seule une nouvelle exécution isolée peut établir l'effet
natif de ce correctif. Aucune qualification du vêtement n'est accordée ici.

Replay pur ciblé du 4 octobre 2026, après le correctif :

| Entrée | Sommets de contour | Coins source exacts | Arêtes < 0,001 cm | Crans sous-bras |
| --- | ---: | ---: | ---: | --- |
| Package original | 2 216 | 249 | 0 | 4 liaisons `BOUNDARY_SEGMENT` |
| Variante de manches acceptée | 2 236 | 253 | 0 | 4 liaisons `BOUNDARY_SEGMENT` |

Les contours et correspondances physiques sont identiques avec ou sans le
dossier de crans. Les quatre fractions locales et les quatre UV source restent
exactes dans chaque cas. Sur ces quatre crans sous-bras, le résidu maximal d'interpolation observé vaut
`7.32410687763558e-15 cm` pour l'original et `5.329070518200751e-15 cm` pour la
variante. Il n'est pas utilisé pour accepter un écart d'identité.

Le dossier de replay de la variante est une copie en mémoire du dossier original
avec les seules lignes de manches remplacées par celles du dossier candidat.
Les six fichiers lus gardent leurs SHA avant/après ; aucune base canonique n'est
ouverte ou écrite :

| Source | SHA-256 préservé |
| --- | --- |
| Package original | `a51a8c782fa908a11dad6d69fb8a488df6df12d67af580798c70d5f5cbbc0253` |
| Package de la variante acceptée | `771eddd4dec57f4c938d8b16932ee0a3757c9cc9b5c73ea8675bf2a2f9742bad` |
| Dossier original | `80acf6fb94c43f4179202add23d968c0fede22f1ec56abe73904049964670a40` |
| Dossier candidat | `7d98d25c6fb9e253b2c30be7ec3281e3840e8902cb4a2f216a06427d5da748fd` |
| Recette native-source-v8 | `d964146818a95b16df4165524bd8e3106f0e28292b4704a7e9dd827508e04584` |
| Configuration native-source-v8 | `8c413bcafd62bc0a4a727c2aadecc6b540be89fb352e19b42653113372137bc3` |

La sélection suivante compte 100 tests portables PASS après revue indépendante.
Elle inclut le refus des champs de sommet physique obsolètes dans une liaison
de segment relue depuis JSON. Cette sélection vérifie les sources
et le contrat de préparation ; elle ne qualifie pas une simulation native :

```text
python -B -m unittest tests.test_pattern_preparation tests.test_pattern_preparation_corners tests.test_self_seam_midpoint_notches tests.test_material_notch_sides tests.test_shared_seam_sampling tests.test_sewing tests.test_source_uv_witnesses tests.test_source_notch_bindings
```
