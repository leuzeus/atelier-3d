# Raccords permanents dans la correction métrique des guides

`a3d.guide_metric_solver.recover_guide_metric` peut résoudre ensemble les pièces
explicitement sélectionnées, en conservant leurs raccords permanents. Il produit
une proposition géométrique séparée. Il ne modifie ni les patrons, ni les UV,
ni les faces, ni les coutures source, ni les coordonnées fournies en entrée.

## Entrées explicites

Les arguments existants conservent leur rôle. L'option `seam_ids` est une liste
unique d'identifiants présents dans `payload.seams`. Une liste non vide exige
`max_initial_seam_gap_cm`, fini et positif ou nul. Les deux pièces de chaque
raccord doivent appartenir à `piece_ids`. La V1 refuse un raccord vers une
pièce non sélectionnée.

Chaque raccord doit être permanent et contenir des paires de sommets réels,
ordonnées sur les bords natifs nommés de ses deux pièces. Le noyau vérifie
l'appartenance aux panneaux, l'incidence des faces et la couverture complète
de ces bords. Un nom absent n'est récupéré que si un seul bord natif correspond
exactement à la chaîne déclarée. Une association ambiguë est refusée. Aucune
distance de proximité ne crée une relation.

Chaque pièce doit conserver au moins un appui explicite. Les extrémités des
`protected_edges`, les `protected_indices` et les pins existants restent fixes.
Une cohorte transitive contenant plusieurs appuis de coordonnées différentes
est refusée, même si son écart reste inférieur au budget de raccord.

Le compilateur de préparation transmet la sélection complète d'un rapport de
couplage sourcé : torse, col et devant intérieur peuvent ainsi être corrigés
ensemble. Il vérifie le hash des cages, les pièces et toutes les relations
permanentes internes. Les épaules et les ancres des autres rôles doivent nommer
de vrais bords source. Le budget d'alignement initial est la somme conservatrice
des gardes binary32 existantes des panneaux ; il ne devient pas une tolérance
finale de couture. Le contrat exige les identifiants de coutures et ce budget
ensemble. Sans rapport de couplage, la sélection précédente du torse est conservée.

## Correction calculée

Les paires permanentes forment des cohortes transitives. Le diamètre initial
de chaque cohorte est comparé au budget explicite. Une cohorte libre est
alignée sur la moyenne de ses positions initiales ; une cohorte fixe reprend
exactement son appui. Cet alignement doit respecter le budget global de
déplacement et le contrôle de non-effondrement pendant la trajectoire linéaire.

La résolution locale/globale réunit ensuite les inconnues de chaque cohorte
dans un seul degré de liberté par axe. Les contributions de toutes ses faces
s'additionnent dans le système de gradient conjugué préconditionné. Les sommets
intérieurs restent des inconnues distinctes : la correction peut ainsi se
répartir dans les pièces sans ouvrir les raccords. Il n'y a aucune soudure ni
consolidation de topologie.

Les budgets de temps, d'itérations, de pas et de déplacement, la conservation
du meilleur candidat, l'arrêt sur stagnation et les contrôles métriques finaux
restent applicables. L'absence de `seam_ids` conserve le mode indépendant.

## Précontrôle des appuis impossibles

Pour chaque bord protégé, la longueur de sa polyligne UV source est mesurée
sur les faces réellement liées à la pièce. La distance entre ses extrémités
fixes divisée par cette longueur est une borne inférieure du stretch requis.
Si cette borne dépasse `quality.max_stretch`, aucune optimisation ne peut
satisfaire ces contraintes avec les mêmes appuis.

`fixed_stop_stretch_margin` est une marge numérique explicite, finie, comprise
entre zéro et `1e-6`, de valeur par défaut zéro. Elle ne modifie jamais les
limites des contrôles métriques finaux. Le précontrôle produit
`fixed_stop_bounds` avec les identités source, les appuis, leurs coordonnées,
la longueur de matière, la corde et la borne calculée. Une impossibilité donne
`NEEDS_CORRECTION`, `FIXED_SOURCE_STOP_BOUND_EXCEEDS_METRIC`, zéro itération et
aucun historique d'optimisation. L'absence d'impossibilité n'est pas une preuve
que la récupération réussira.

## Portée des résultats

`SOURCE_METRIC_RECOVERED` signifie uniquement que le candidat passe les
contrôles métriques existants. Chaque résultat conserve `qualification: NONE`,
`contacts: NOT_ASSESSED`, `simulation: NOT_EXECUTED` et `fitting: NOT_EXECUTED`.
Le placement, les contacts, Cloth, le fitting et la revue visuelle exigent
leurs propres contrôles sur le candidat exact.

L'égalité exacte des cohortes est garantie pendant la récupération métrique.
La recherche de contacts suivante utilise son mécanisme existant et son gate
d'écart de couture déclaré ; elle ne réutilise pas les inconnues communes de ce
noyau. Son résultat doit être contrôlé séparément. La réussite du noyau ne
garantit donc pas une égalité exacte après toute correction de contact.

Les tests de deux et trois panneaux vérifient une diminution réelle de la
distorsion, les raccords exactement égaux après relaxation, la propagation
aux intérieurs, les appuis et pièces non sélectionnées inchangés, les refus
de relations invalides et les budgets. Ils constituent des preuves de fonction
sur des fixtures synthétiques. Aucun essai natif du vêtement principal n'est
qualifié par ces tests.
