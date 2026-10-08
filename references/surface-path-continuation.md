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

Les bornes sont explicites : 100 000 sommets, 200 000 triangles et faces source,
128 régions, 4 096 requêtes, 120 secondes et 2 000 000 événements au maximum.
Les coordonnées et directions sont finies et bornées à ±1 000 000 cm ou unités
de direction. Les régions appartiennent aux labels source fournis. La
préparation de la géométrie et les requêtes partagent les budgets temporel et
de travail. Une réponse partielle conserve les traces calculées et le nombre
de requêtes non traitées.

## Refus et portée

Les graines exactement à un sommet et les chemins de longueur projetée nulle
restent non supportés dans cette version. Un pli, un passage rasant, une
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
