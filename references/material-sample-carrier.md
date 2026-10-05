# Porteur UV et échantillons matériels distincts

`a3d.material_sample_carrier` fournit un contrat portable local par domaine matériel. Aucun caller, schéma partagé, validateur historique, solveur ou parcours Cloth ne consomme ce format. Son discriminant est `MATERIAL_SAMPLE_CARRIER_V1` ; chaque résultat et reçu portent `purpose=TEST_ONLY`, `qualification=NONE`, `physical_mesh=false` et `is_installable=false`.

`uv_qualification=EXACT_DOMAIN_COVERAGE_AND_SAMPLE_SUPPORT` est émis uniquement après les contrôles complets de ce module. Il signifie que le porteur et la source couvrent exactement le même domaine UV une fois et que leurs échantillons possèdent des supports explicites. Il ne qualifie aucune métrique matière en volume, contrainte 3D, couture physique, placement ou fitting.

## Interfaces locales

```python
build_material_sample_carrier(
    source, carrier, samples, *, marks=None, relations=None,
    budgets=None, deadline=None, clock=time.monotonic)

build_rectangular_material_carrier(
    source, corner_vertex_ids, *, columns, rows,
    budgets=None, deadline=None, clock=time.monotonic)
```

Le premier builder reçoit son porteur séparément. Il n'en choisit ni n'en adapte la géométrie. Le second propose seulement une grille de test : quatre coins source ordonnés, un nombre de colonnes et de rangées explicites, orthogonalité et quatrième coin exacts, puis preuve complète d'égalité des domaines. Il accepte un rectangle tourné dont la géométrie exacte est démontrable ; un trapèze, une enveloppe rectangulaire approximative ou une source incomplète sont refusés. Aucune grille de production n'est inventée.

## Entrées et identités

Les objets `source` et `carrier` ont les mêmes champs explicites :

```json
{
  "id": "collar",
  "uv_cm": [[0, 0], [4, 0], [4, 2], [0, 2]],
  "vertex_ids": ["v0", "v1", "v2", "v3"],
  "triangles": [[0, 1, 2], [0, 2, 3]],
  "face_ids": ["f0", "f1"],
  "edges": {"bottom": ["v0", "v1"]}
}
```

`edges` est facultatif lorsque aucune relation n'est fournie. Un bord nommé suit les segments réels de la frontière du domaine. Les indices de triangles sont des références explicites aux sommets ; les IDs de sommets et de faces sont uniques dans leurs espaces respectifs. Le domaine doit être un disque triangulé connexe, manifold, sans trou, recouvrement positif, contact non conforme, sommet inutilisé ou UV exactement dupliqués. Les domaines avec trous et les collections de domaines sont refusés par cette version locale.

Chaque échantillon est une identité distincte et un support source existant :

```json
{
  "id": "collar-inner-right-mid",
  "source_face_id": "f0",
  "source_barycentric_weights": ["1/2", "1/2", "0"]
}
```

Les poids sont non négatifs et leur somme vaut exactement 1. `source_vertex_id` peut préciser un coin source ; son UV doit correspondre exactement. `metadata` peut conserver une provenance JSON bornée, sans interprétation géométrique implicite. Toutes les identités des sommets source reçoivent aussi un support dans `source_vertex_bindings`, sans création d'échantillons fictifs.

Les nombres natifs `int` et `float` et les chaînes rationnelles canoniques telles que `1/2` sont admis. Un `float` représente sa valeur binaire exacte, pas un décimal réarrondi. Les booléens, valeurs non finies, rationnels non canoniques et conteneurs non natifs sont refusés. Les fractions de couture proches restent distinctes, même lorsque deux échantillons partagent exactement un UV. Aucun seuil spatial, weld, arrondi ou alias vers le voisin n'existe dans ce contrat.

## Intersections et ambiguïtés

Une face du porteur peut traverser plusieurs faces source. Chaque intersection conserve le polygone UV rationnel, son aire exacte, les deux IDs de faces, leurs IDs de sommets et les supports barycentriques de ses points dans les deux triangles. La couverture est vérifiée par face dans les deux sens. Les anciens validateurs qui exigent un support source unique par face restent inchangés et ne doivent pas accepter implicitement ce format.

Un échantillon sur une arête ou un sommet peut avoir plusieurs triangles porteurs candidats. Ils sont admis seulement si leurs poids non nuls donnent exactement la même ligne d'interpolation sur les IDs globaux des sommets. Le reçu conserve toutes les faces équivalentes ; la face représentante est choisie par ID stable. Des lignes différentes constituent une ambiguïté et sont refusées.

## Relations et crans

Une relation conserve `id`, `kind` (`permanent`, `closure` ou `detachable`), `orientation` (`forward` ou `reverse`) et exactement deux `owners` :

```json
{
  "id": "collar-inner-right",
  "kind": "permanent",
  "orientation": "forward",
  "owners": [
    {"source_id": "collar", "edge_id": "bottom", "samples": [
      {"sample_id": "start", "fraction": "0"},
      {"sample_id": "end", "fraction": "1"}
    ]},
    {"source_id": "inner-front", "edge_id": "neck-right",
     "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
     "source_vertex_ids": ["external0", "external1"], "samples": [
      {"sample_id": "external-start", "fraction": "0",
       "source_segment_vertex_ids": ["external0", "external1"], "source_segment_parameter": "0"},
      {"sample_id": "external-end", "fraction": "1",
       "source_segment_vertex_ids": ["external0", "external1"], "source_segment_parameter": "1"}
    ]}
  ]
}
```

Les partitions des deux propriétaires sont identiques, strictement croissantes de 0 à 1. Le propriétaire local suit ses vrais points source dans l'ordre du bord nommé ; l'orientation inverse s'applique au second propriétaire. Un même segment local ne peut appartenir à deux relations permanentes. Le builder ne complète pas une partition manquante et ne transforme aucune fermeture en couture permanente.

Un propriétaire externe doit nommer son empreinte source, son bord, sa chaîne de sommets, ses samples et ses paramètres de segments. Les IDs, plages [0,1], extrémités et ordre sont contrôlés. Sa géométrie et l'existence fournisseur de son empreinte ne sont pas vérifiées par ce builder local : le reçu le classe `BOUNDED_SOURCE_REFERENCE_ONLY`, `geometry_checked=false`, `equality_3d_checked=false`. Une composition multi-domaines devra vérifier ces références contre les sources correspondantes.

Un cran contient `id`, `relation_id`, `fraction`, `symbol` (`notch` ou `double-notch`) et `owners`, chaque propriétaire ayant `owner_index` et `sample_id`. Il se lie au bord local réel de la relation. Le sample du cran peut rester distinct des samples de la partition de couture : un cran à `1/2` n'est jamais remplacé par une fraction proche. Son ID et son symbole sont conservés ; deux propriétaires d'un cran de fermeture restent séparés.

Les fractions normalisées fournies restent des identités déclarées. Le module contrôle leurs bornes, leur ordre et les supports UV, mais ne mesure pas la longueur d'arc pour qualifier leur valeur. Il expose `normalized_arc_measurement=DECLARED_FRACTIONS_ONLY_NOT_MEASURED`. L'acceptation des positions de crans selon une mesure d'arc appartient à une étape distincte.

## Budgets, immutabilité et qualification

Les entrées JSON sont bornées avant leur empreinte et copiées sans alias mutable. Les empreintes des références sont comparées après copie, validation et avant retour ; une mutation observée refuse le résultat. Les copies dans le résultat sont indépendantes des références reçues. Les IDs, UV et faces fournis restent présents sans modification dans le reçu.

Les plafonds par défaut sont 4 000 sommets et 8 000 triangles par maillage, 10 000 samples, 20 000 propriétaires de crans et de relations, 250 000 comparaisons géométriques, 50 000 patches, 200 000 nœuds JSON, une représentation JSON majorée à 8 Mio et 4 096 bits par nombre rationnel. Les budgets fournis sont explicites, positifs et limités par les caps du module. Le travail projeté est refusé avant de dépasser le budget de comparaisons ; les compteurs consommés sont conservés dans le reçu.

La durée maximale est de 60 secondes. `deadline` est une échéance absolue monotone ; l'échéance effective est le minimum entre celle-ci et `start + max_seconds`. Des contrôles coopératifs couvrent copie, topologie, clipping, couverture, supports, relations, crans, encodage et retour. Un délai épuisé, une horloge non finie ou reculant, un domaine différent ou une ambiguïté refuse le résultat, sans qualification partielle implicite.

Un porteur UV qui traverse une cassure du champ de cibles source ne reproduit pas automatiquement toutes ses positions par un champ affine unique. Les nœuds des douze barres de la courbe et les samples de couture remplissent des rôles différents. Ce module conserve le mapping sans prouver la représentabilité de ce champ ou la faisabilité des contraintes interpolées 3D. Ces états restent `NOT_QUALIFIED`. Aucun recover, contact, maillage physique, Cloth, mouvement ou fitting n'est exécuté.
