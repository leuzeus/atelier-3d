# Correspondance locale depuis un bord corporel source

`a3d.surface_path_continuation.trace_surface_paths` est un noyau portable de
diagnostic. Il suit une branche de surface depuis une arête source explicite,
dans un domaine de faces et une direction déclarés. Il ne déplace ni le corps,
ni une cage, ni un patron. Son résultat ne qualifie ni une réserve, ni les
contacts, ni le fitting.

Le point recherché n'est pas choisi au plus proche. La graine identifie une
arête, une fraction strictement intérieure et toutes ses faces incidentes
appartenant au domaine. Le segment projeté entre cette graine et la cible
exacte traverse successivement les triangles adjacents. Une branche sortante
unique et transverse est nécessaire à chaque passage. Les prédicats de
projection et de traversée utilisent les rationnels des coordonnées binaires,
sans fusion d'événements par une tolérance physique.

## Contrat interne

La géométrie fournit les sommets en centimètres, les triangles indexés, leur
propriétaire source et les régions des faces. La politique contient exactement :

```json
{
  "method": "SEEDED_SURFACE_PATH_LIFT_V1",
  "source_region_ids": [1],
  "direction_world": [0, 1, 0],
  "min_cosine": 0.000000001,
  "max_seconds": 120,
  "max_events": 100000
}
```

Chaque requête fournit `request_id`, `seed_edge_vertex_ids`, `seed_fraction`,
`seed_face_ids` et `target_world_cm`. Ces champs doivent être dérivés de
références authentifiées par l'appelant. Le noyau contrôle leur cohérence
géométrique ; il n'authentifie pas leur origine native ni leur relation à une
couture textile. Les empreintes lient le résultat aux tableaux, aux requêtes,
à la politique et au code exacts. Le nombre d'événements borne le travail,
pas une distance anatomique.

### Graines exactement aux sommets — V2

La méthode explicite `SEEDED_SURFACE_PATH_LIFT_V2` conserve les mêmes champs et
autorise aussi les fractions exactement égales à `0` ou `1`. Le sommet est alors
respectivement `seed_edge_vertex_ids[0]` ou `seed_edge_vertex_ids[1]`. L'arête
source déclarée doit toujours exister. Aucune fraction voisine n'est arrondie ou
rapprochée d'une extrémité.

Pour cette graine de sommet, `seed_face_ids` doit contenir **toutes les faces
source incidentes au sommet dans les régions autorisées**, en indices entiers
distincts, avec une limite de 256 faces. Les seules incidences de l'arête ne
suffisent pas. L'appelant dérive cette liste depuis la géométrie native
authentifiée ; le noyau la compare à l'étoile reconstruite depuis les triangles.

Avant de sélectionner une sortie, le noyau vérifie :

- l'étoile native entière, y compris les triangles hors du domaine, est manifold
  et connexe ; aucune région exclue ne peut masquer une branche non manifold ;
- la restriction aux régions autorisées est connexe et tous ses triangles sont
  transverses dans la direction déclarée ;
- un seul triangle autorisé contient un intervalle strictement positif du trajet
  projeté sortant du sommet.

Une étoile de bord en éventail est permise. Un trajet le long de deux triangles
sortants reste ambigu et est refusé. L'ordre des faces ou la proximité de la
cible ne choisit jamais une branche. Les parcours d'étoiles consomment le même
budget cumulé que la construction et les autres requêtes du lot.

Le rapport de graine ajoute `seed_kind: NATIVE_VERTEX`, `vertex_id`, les indices
des étoiles native et autorisée, et leur portée. Le champ
`all_native_incident_source_faces` désigne alors l'étoile entière du sommet.
La version de politique et les requêtes sont couvertes par les empreintes.

Pour une fraction strictement intérieure, V2 applique le contrat d'arête V1,
avec au plus deux faces incidentes. V1 conserve son refus des extrémités et son
comportement historique. L'API interne `Surface.trace` garde également ce
défaut ; l'extension exige `allow_vertex_seed=True`.

Les bornes sont explicites : 100 000 sommets, 200 000 triangles et faces source,
128 régions, 4 096 requêtes, 120 secondes et 2 000 000 événements au maximum.
Les coordonnées et directions sont finies et bornées à ±1 000 000 cm ou unités
de direction. Les régions appartiennent aux labels source fournis. La
préparation de la géométrie et les requêtes partagent les budgets temporel et
de travail. Une réponse partielle conserve les traces calculées et le nombre
de requêtes non traitées.

## Refus et portée

Les graines exactement à un sommet restent non supportées en V1 ; V2 les
traite sous le contrat d'étoile ci-dessus. Les chemins de longueur projetée
nulle restent non supportés dans les deux versions. Un pli, un passage rasant, une
branche ambiguë, une étoile non manifold ou une sortie du domaine produit
un refus. Une arrivée sur une arête peut identifier le point sans certifier
son cône de normales. Une expiration au dernier calcul ne peut produire un
succès de lot ; l'éventuel point terminal est conservé comme provisoire.

La normalisation des directions et des normales évite les sous-flux des
petites valeurs. La surface conserve une copie de ses entrées ; les normales
retournées ne donnent pas accès aux caches mutables. Les tests couvrent aussi
les nappes proches, les subdivisions coplanaires, le domaine borné et les
empreintes de cibles modifiées.

Ce noyau n'est pas encore raccordé au dispatcher des guides ni à une nouvelle
opération MCP. Il prépare le raccord d'un producteur de correspondances depuis
les coutures source et les trajets corporels. Les 174 levées du diagnostic
d'encolure portent sur des cibles de frontière proposées, pas sur le placement
actuel du torse. Une correspondance intérieure des panneaux et une correction
conjointe respectant métrique, attaches et contacts restent nécessaires.
