# Champ de surface 3D portable

`a3d.material_surface_field` compile et mesure un champ C libre, affine par face d'un porteur **fourni**. Il ne crée ni grille, enrichissement, solveur ou maillage physique. Aucun caller, schéma partagé, contrat d'admission ou parcours Blender/Cloth ne consomme son format. L'ancien contrat de cage et `material_sample_carrier` restent inchangés.

Le discriminant est `MATERIAL_SURFACE_FIELD_V1`. Tous les résultats et reçus portent `purpose=TEST_ONLY`, `qualification=NONE`, `physical_mesh=false`, `is_installable=false`. `PASS_TEST_ONLY` concerne seulement les mesures locales déclarées. Aucun `READY`, PASS de vêtement, fitting ou acceptation de contraintes 3D n'est émis.

## Interfaces

```python
compile_material_surface_field(
    source, carrier, reference, coordinates_cm, *, samples=None, marks=None,
    relations=None, targets=None, previous_coordinates_cm=None, limits=None,
    budgets=None, deadline=None, clock=time.monotonic)

evaluate_material_field(compiled, requests=None, *,
    budgets=None, deadline=None, clock=time.monotonic)

observe_material_surface_field(compiled, *,
    budgets=None, deadline=None, clock=time.monotonic)

validate_material_surface_field(compiled, *,
    budgets=None, deadline=None, clock=time.monotonic)
```

`validate_material_surface_field` retourne l'observation contrôlée, avec violations et `local_field_checks`, sans modifier son reçu ni introduire une étape d'admission. Les consumers recompilent leurs entrées et vérifient leurs empreintes. Les flags, patches et qualifications d'un payload fourni ne servent jamais de preuve.

## Entrées explicites

`source` et `carrier` utilisent le contrat UV de [material-sample-carrier.md](material-sample-carrier.md) : `id`, `uv_cm`, `vertex_ids`, `face_ids`, `triangles`, éventuellement `edges`. Ils représentent chacun un disque matériel complet, sans trou, chevauchement, contact non conforme ou identité dupliquée. UV natifs et chaînes rationnelles canoniques restent exacts ; aucune tolérance ULP UV, arrondi ou fusion de proximité n'est ajouté.

`reference` est un objet indépendant :

```json
{
  "mesh": {
    "id": "fresh-reference",
    "uv_cm": [[0, 0], [1, 0], [1, 1], [0, 1]],
    "vertex_ids": ["r0", "r1", "r2", "r3"],
    "face_ids": ["rf0", "rf1"],
    "triangles": [[0, 1, 2], [0, 2, 3]]
  },
  "coordinates_cm": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
}
```

Le champ S_fresh conserve la triangulation, les cassures et les positions 3D de cette référence. Il n'est pas remplacé par des valeurs aux seuls nœuds de C. Le caller doit fournir le **vrai** champ frais avant injection, avec ses bindings et sa provenance métier. Cette unité vérifie la géométrie fournie et ses empreintes ; elle ne certifie pas que le caller a sélectionné le bon corps ou le bon candidat.

`coordinates_cm` contient une ligne 3D par nœud du porteur. Les coordonnées 3D et targets sont des nombres natifs finis, exactement représentables en binaire64 ; les entiers non représentables et chaînes rationnelles 3D sont refusés. Leur valeur binaire exacte est convertie en rationnel pour les calculs. UV et identités matérielles exactes restent distincts des coordonnées 3D IEEE calculées.

`previous_coordinates_cm`, si fourni, décrit le champ précédent sur **ce même porteur**. Il sert seulement au pas ; S_fresh demeure la référence du déplacement total. Son absence donne `step_assessed=false`, sans preuve de pas inventée. Un porteur précédent différent exige un futur contrat supplémentaire et n'est pas accepté par cette interface.

Samples, crans, relations et propriétaires externes reprennent intégralement le contrat UV. Deux samples de même UV gardent des IDs distincts ; le point `0.49999975746439695` ne devient jamais le cran 0,5. Les orientations sont conservées. Une `closure` ou `detachable` n'est pas promue en couture permanente. Les références externes restent des références bornées : leur géométrie et égalité 3D ne sont pas contrôlées par cette unité.

Les targets optionnels ont `id`, `sample_id`, `target_cm`, `role`. `sample_id` doit exister. `role` est `physical_stop` ou `numerical_target` ; aucune cible n'est créée implicitement. Les résidus rationnels et ceux de la conversion binaire64 sont enregistrés. Un stop fourni avec résidu non nul fait échouer les contrôles locaux. Un résidu numérique est observé, sans tolérance de contrainte ou qualification implicite. Aucun pin n'est ajouté ; cette unité n'a pas de contrat d'optimisation de pins.

## Domaines et supports

Le builder UV inchangé est exécuté pour source ↔ porteur et référence ↔ porteur, avec le même budget et la même échéance. Il contrôle à nouveau winding, manifold, aire, recouvrement et toutes les identités. Les deux mappings complets prouvent la même couverture matérielle.

Une intersection supplémentaire source ↔ référence ↔ porteur conserve trois IDs de faces, polygone rationnel, aire et supports barycentriques dans chaque triangulation. Sa couverture est prouvée sur chaque patch source ↔ porteur. Les patches fins sont des domaines de mesure et d'intégration ; ils ne créent pas de petites arêtes entre degrés de liberté ni de faces physiques.

Si le domaine ou les bindings IEEE UV fournis diffèrent de la source exacte, le builder refuse. Il n'applique aucune translation, alias de sample, canonicalisation de voisin ou approximation silencieuse de la référence. Une nouvelle proposition numérique sourcée appartient à une autre unité.

Les deux windings cohérents sont supportés. Un winding différent entre source, porteur et référence est refusé. Un support sur une arête est admis uniquement lorsque toutes les faces candidates donnent une même ligne sparse d'interpolation sur les IDs globaux du mesh concerné.

## Évaluation

Sans `requests`, l'évaluateur retourne les samples déjà déclarés. Une requête contient un `id` de requête unique et **exactement un** des champs :

- `sample_id` : identité matérielle existante ;
- `source_vertex_id` : sommet matériel existant ;
- `uv_cm` : UV exact explicitement fourni, avec ses supports source, porteur et référence contrôlés.

Les positions retournées comprennent `coordinates_exact_cm`, la conversion `coordinates_cm` binaire64 et son erreur exacte par composante. La référence est évaluée avec ses propres cassures. Les résultats ne modifient ni samples, source ni carrier. La conversion finale est une observation distincte, jamais une assertion que tout triplet interpolé serait mathématiquement représentable en IEEE.

## Mesures et limites

Les limites de métrique par défaut sont `min_stretch=0.9`, `max_stretch=1.1`, déplacement total `8 cm`, pas `0.5 cm`. Les profils peuvent seulement les resserrer. Ces valeurs sont interprétées comme leurs **valeurs binaires exactes** déclarées, sans ajout de marge.

La Jacobienne J de C est constante par triangle porteur. Le Gram `G=JᵀJ` est rationnel exact. Les contrôles de `G−L²I` et `U²I−G` vérifient les deux diagonales et le déterminant pour la semi-définition positive. Aucune tolérance CG, moyenne d'étirement ou racine carrée arrondie ne décide ces comparaisons. Une rotation exacte conserve la métrique ; un collapse ou un écart d'un ULP hors limite échoue.

Sur chaque patch référence ↔ C, `C−S_fresh` est affine. La norme convexe est bornée par les coins du patch ; leur distance **au carré rationnelle** est comparée au carré de 8 cm, sans `8+epsilon`. La même règle contrôle le pas depuis le champ précédent avec 0,5 cm, sans remettre le total à zéro. Les coins de cassure de S_fresh sont donc contrôlés même lorsqu'ils ne sont ni sample ni nœud porteur.

La conversion IEEE est aussi mesurée à ces coins et ses distances observées doivent passer les limites. Ceci ne prouve pas une enveloppe continue du **champ arrondi en chaque UV** ni le comportement de l'interpolateur natif : `binary64_distance_scope` l'indique explicitement. Le contrôle global décrit ici porte sur les champs affines rationnels fournis. Toute adaptation native et son erreur demandent des contrôles séparés.

## Budgets et horloge

La première lecture de l'horloge précède la capture des budgets, des inputs et leurs empreintes. Le parcours des conteneurs, copie, hachage, contrôle UV, clipping, supports, métriques, conversion, contrôles finaux et retour partagent l'échéance coopérative `min(start+max_seconds, deadline)`. `max_seconds` ne dépasse jamais 60 s. L'horloge fournie doit être finie, monotone et **sans effets de bord**. Les mutations détectées pendant les phases sont refusées.

Un programme doit fournir sa même échéance absolue, créée avant ses phases et limitée à ses 300 s globaux. `deadline=None` est un essai local de 60 s, sans preuve de budget global ni droit de réinitialiser une exécution. Aucune durée historique ne reconstruit une échéance live. Les entrées déjà expirées et l'expiration pendant capture, clipping, métriques ou contrôles de retour refusent le résultat.

Le dernier contrôle de délai suit aussi la dernière empreinte de préservation.
Le temps consommé par cette empreinte est inclus ; une échéance atteinte
pendant ce travail refuse compilation, évaluation, observation et validation.
L'horloge reste une lecture monotone sans mutation des entrées.

Caps explicites : nombres de sommets/faces source, référence et porteur, samples/targets/queries, propriétaires de relation et crans, comparaisons de paires, intersections UV et triple refinement, coins contrôlés, faces mesurées, nœuds/bytes input/output, bits rationnels et checkpoints d'opérations rationnelles du nouveau module. Le builder UV garde ses caps et gardes de précision ; ses opérations élémentaires sont bornées par ses caps de géométrie/comparaisons, pas comptées une à une dans le compteur du nouveau module. La double validation du porteur consomme deux fois ses sommets/faces et comparaisons dans les compteurs partagés ; ce coût est déclaré dans le reçu.

Les caps de sortie portent sur **l'objet retourné entier, reçu compris**. `work.output_nodes` compte une fois chaque valeur JSON, conteneurs inclus ; les clés ne sont pas des nœuds. `work.output_bytes` est le nombre exact d'octets de sa sérialisation JSON compacte UTF-8 (`ensure_ascii=false`, séparateurs virgule/deux-points, nombres finis). Les compteurs et budgets présents dans le reçu sont eux aussi compris. Le compteur d'octets est stabilisé avec sa propre représentation décimale ; les passes de mesure restent sous la même échéance et ne facturent pas plusieurs fois le même résultat. Aucun cap n'est relevé. La valeur `elapsed_seconds` est relevée avant la mesure finale de sortie ; cette mesure et les contrôles de préservation/échéance qui la suivent restent chronométrés et peuvent encore refuser le retour.

`BUDGET_EXHAUSTED` et `DEADLINE_EXHAUSTED` portent `status=INCOMPLETE`, `qualification=NONE`. Une preuve non terminée ne reçoit pas de qualification UV ou 3D. Les autres refus sont localisés : domaines, identités, supports, nombres, mutations, profils ou contrat invalides. Les reçus lient toutes les données, les positions de référence/candidat/précédent, les limites et les fichiers source du module et du builder UV vus pendant l'appel. Ces empreintes de code ne prouvent pas une installation ou un serveur connecté.

## Limites de cette unité

Le module ne prouve ni rang/compatibilité d'un système de contraintes, ni trace des 12 barres du replay actuel, ni égalité de toutes les cohortes, ni fidélité anatomique du champ fourni. Il ne vérifie pas le trajet continu entre deux champs, les intersections 3D, contacts, normales natives, maillage physique, Cloth, enfilage, fitting ou revue artistique. Ces champs restent `NOT_QUALIFIED` / `NOT_ASSESSED`.

Les critères physiques et validateurs historiques restent inchangés. Un échec de ce champ ou porteur ne démontre pas l'impossibilité d'un patron ou vêtement. Aucun test du replay actuel ou des six cages n'est exécuté pour cette unité ; les témoins sont des carrés portables synthétiques, explicitement non produit.
