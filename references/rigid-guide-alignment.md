# Seed rigide des guides depuis les raccords source

Le module privé `a3d/rigid_guide_alignment.py` prépare une meilleure proposition du devant intérieur, sans modifier le découpage, les UV, les crans, les types de raccord ou le corps. Son résultat conserve `qualification=NONE`. Les résidus, même nuls, ne valident ni placement, ni contacts, ni Cloth ou fitting.

## Sélection et intégration

Le dispatcher transmet explicitement les rôles compilés au coupler. Les candidats ont le rôle `inner_front` ; leurs partenaires ont le rôle `front`. L’inventaire attendu provient de **tout le graphe source approuvé**, avant la sélection des témoins. Tous les liens permanents applicables et tous leurs partenaires doivent être présents. Aucun identifiant de pièce ou de couture propre à un vêtement ne décide du placement.

Après préparation des cages et des homologues, le helper réutilise les chaînes source et leurs partitions pour vérifier que chaque contrôle requis existe et correspond à son identité exacte. Il ne reconstruit pas une cage, ne cherche pas un voisin spatial et n’ajoute aucun point. L’orientation forward/reverse reste celle du raccord approuvé.

Le fit utilise les positions originales des partenaires du torse comme cibles immuables. Il transporte tous les contrôles originaux de la pièce mobile une seule fois. Les liens permanents vers d’autres rôles restent visibles dans `remaining_permanent_relation_ids` ; la portée est alors `PARTIAL_RIGID_SEED_APPLIED`. Fermetures et liens détachables sont exclus et conservent leur type.

Le col reçoit un diagnostic `COLLAR_ALIGNMENT_NOT_IMPLEMENTED`. Une transformation rigide globale ne suffit pas à corriger les guides actuels de l’encolure ; aucune rotation automatique du col n’est appliquée. Le dispatcher retourne `PARTIAL_GUIDES` lorsqu’un diagnostic d’alignement ou une portée partielle demeure, tout en conservant les guides examinables.

Les appels directs à `couple_source_seams(..., semantics=None)` conservent le chemin et le reçu historiques. Ils n’activent pas ce module.

## Noyau numérique borné

La transformation a la forme `q + R·(p−p₀)` : rotation propre, `det R=+1`, sans échelle ou réflexion, autour des centroïdes pondérés. Les poids sont les intervalles de longueur matérielle source. Leur normalisation et celle des coordonnées centrées empêchent les débordements évitables et limitent l’influence du repère mondial.

Les matrices de Gram normalisées des deux nuages donnent une borne inférieure conservatrice du rang, par les intervalles de leurs mineurs principaux. Une valeur dans l’incertitude d’arrondi ne certifie pas un rang. Le rang doit atteindre deux ; aucun solveur itératif supplémentaire n’est utilisé pour cette vérification.

La matrice symétrique Horn 4×4 normalisée est traitée par Jacobi avec sélection déterministe du plus grand élément hors diagonale et **64 rotations au maximum par fit**. La convergence se juge à l’échelle normalisée de la matrice et à l’epsilon IEEE binary64. L’intervalle d’incertitude des valeurs propres additionne une borne de Gershgorin des éléments hors diagonale et une borne conservatrice d’arrondi des mises à jour. Si les intervalles des deux valeurs propres principales se recouvrent, l’orientation est ambiguë et le seed est refusé.

Le reçu donne le rang, les mineurs et leurs incertitudes, le nombre de rotations, l’off-diagonale restante, la borne d’incertitude spectrale, le déterminant, le résidu d’orthogonalité et les gaps avant/après. Ces marges numériques ne sont **pas des tolérances produit**. Les gates de métrique et de géométrie restent inchangés.

Le helper partage l’objet budget et l’horloge du coupler. Il ne recharge pas les mêmes contrôles dans le budget et n’obtient pas de nouveau délai. Rang insuffisant, correspondances incomplètes, données non finies, sous-flux d’un poids ou non-convergence donnent une raison explicite, sans mouvement de seed pour la pièce concernée. L’épuisement de temps ou l’inversion de l’horloge interrompt la préparation par l’erreur du budget existant. Aucun retry automatique n’est ajouté.

## Couplage, déplacements et identités

La moyenne des cohortes utilise ensuite les propositions alignées ; elle peut encore les déformer. Le reçu garde séparément :

- `max_target_correction_cm`, déplacement absolu entre le guide original et le résultat couplé ;
- `postseed_target_correction_cm`, déplacement entre la proposition alignée et le résultat couplé ;
- le déplacement du seed, les gaps originaux, les gaps alignés et les gaps après moyenne.

Ces valeurs empêchent de masquer une grande translation/rotation par un faible résidu de couplage. Une moyenne qui ferme un gap ne constitue pas une admission de métrique.

Les bindings actifs lient les rôles, le code du noyau, les cages initiales, les données source et la recette. Le générateur de politique inclut le nouveau module dans `CODE_SOURCES` ; le profil, la pose, la géométrie corporelle et la compilation restent liés par la politique existante. Changer une de ces dépendances invalide les guides et les preuves affectées.

## Vérification et portée

Les tests ciblés couvrent transformation connue, déterminant/distances, repère tourné et translaté, invariance à l’ordre et aux noms, ambiguïtés de rang et de réflexion, données non finies, échelle cible incompatible, partenaires et partitions manquants, liens de fermeture, scope partiel du col, budget partagé et sortie sans retry sur non-convergence. Les reçus doivent se rejouer en JSON de manière déterministe et les entrées rester immuables.

Le replay local distinct `program-rigid-guide-alignment-v1` utilise les cages V intégrées et le coupler SOURCE57 gelé comme comparateur. Le rapport SOURCE53/V9 antérieur demeure historique. Les métriques du replay portent sur des triangles de cages auxiliaires ; elles ne qualifient pas le maillage textile régulier à 15°, le fitting, les contacts ou le vêtement complet.

Le script portable historique `portable_production_preparation_diagnostic.py` ne transmet pas de sélection/recette de couplage et n’exerce donc pas cette nouvelle branche. Ajouter le noyau à ses références de code ne transforme pas ce script en preuve d’alignement. Le nouveau replay transmet les paramètres de couplage et la recette explicitement.
