# Référence partagée pour la récupération métrique

`a3d.guide_metric_solver.recover_guide_metric` accepte deux paramètres optionnels :

```python
recover_guide_metric(..., displacement_reference=None, deadline=None)
```

Cette API prépare un candidat géométrique. Elle ne contrôle pas les contacts, ne simule pas Cloth et n'accepte ni placement, ni fitting, ni vêtement.

La référence de déplacement représente le guide frais **avant** une correction antérieure, par exemple l'injection d'une courbe. Elle contient exactement un point 3D fini par sommet du même payload source. L'entrée, l'alignement sémantique, chaque proposition et le candidat retourné restent dans `max_displacement_cm` depuis cette référence. Un budget déjà consommé n'est pas remis à zéro.

Les coordonnées d'entrée ont un autre rôle : les indices de `protected_indices` peuvent porter les cibles d'une correction numérique déjà calculée et restent fixes à ces valeurs. Les cohortes permanentes propagent ce blocage à tous leurs membres. Ces contraintes ne deviennent pas des pins physiques. Tous les pins positifs existants et les extrémités des bords de `protected_edges` doivent au contraire correspondre exactement à la référence originale. Deux points fixes incompatibles dans une cohorte sont refusés.

`deadline` est une échéance absolue exprimée dans le même temps monotone que `clock`. La récupération utilise la limite la plus stricte entre cette échéance et `start + max_seconds`. Les nouveaux appels vérifient une horloge finie et non décroissante et contrôlent les frontières des préflights, les cohortes, les assemblages, les résidus, les PCG et les validations. Un appel terminé après l'échéance ne peut pas retourner `SOURCE_METRIC_RECOVERED`.

L'arrêt est coopératif : les évaluateurs de métrique et de trajectoire existants ne sont pas préemptés au milieu de leur appel. Les contrôles avant/après détectent leur dépassement. Un délai épuisé avant la préparation du meilleur état produit un `StudioError` de budget ; pendant l'optimisation il retourne le meilleur état antérieur, `NEEDS_CORRECTION` et `TIME_BUDGET`. La validation métrique finale reste exécutée comme observation complète, même après un arrêt ; son résultat ne rétablit aucune admission lorsque le délai est épuisé.

Les nouveaux appels mesurent le déplacement réel après calcul en binaire64 et refusent un pas supérieur à `max_step_cm`, sans marge epsilon. L'alignement initial doit aussi respecter cette limite et la référence globale. Les points sources, UV, topologie, coutures et entrées restent immuables.

Les reçus des nouveaux appels distinguent :

- `initial_candidate_sha256` : coordonnées d'entrée et contraintes numériques ;
- `displacement_reference_sha256` : référence globale conservée ;
- `initial_displacement_from_reference_cm`, `displacement_from_entry_cm` et `max_displacement_cm` ;
- `history[].actual_step_cm` pour les étapes acceptées ;
- `physical_fixed_indices` et `shared_deadline`, avec échéance effective, instant final, expiration et phase d'arrêt lorsque disponible.

Quand les deux nouveaux paramètres sont absents ou `None`, la récupération conserve les calculs, décisions, ordre d'appel de l'horloge et forme des reçus historiques. Les garde-fous plus stricts sont activés uniquement lorsqu'au moins une option est fournie. Les limites métriques finales ne changent pas.

Cette unité n'ajoute aucun champ aux profils de préparation ni aux interfaces serveur. Le caller doit déclarer son enveloppe globale et transmettre la même référence et la même échéance aux phases appropriées. La transmission des contraintes numériques au solveur de contact, la provenance du post-traitement des guides, le remapping natif et les décisions humaines restent des unités séparées.
