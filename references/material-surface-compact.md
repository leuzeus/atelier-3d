# Stockage compact exact du champ fourni

`a3d.material_surface_compact` prépare le format séparé
`MATERIAL_SURFACE_FIELD_COMPACT_V1`. Il conserve le champ fourni et sa référence
fraîche complète. Il ne construit ni nouveau porteur, maillage physique,
optimiseur ou référence de remplacement. Les consommateurs
`MATERIAL_SURFACE_FIELD_V1` restent inchangés et refusent ce discriminant.

Tous les résultats portent `purpose=TEST_ONLY`, `qualification=NONE`,
`physical_mesh=false` et `is_installable=false`. La validation porte sur le
stockage exact et sa reconstruction, pas sur la métrique, les contraintes 3D,
les contacts, Cloth, l'enfilage ou le fitting.
Le packing porte `status=COMPILED_TEST_ONLY` sous son discriminant compact
distinct ; ce statut n'attribue aucune qualification.

## Interface interne et origine du budget

Le caller doit créer le budget du champ **avant la capture**, conserver le
même objet pendant la compilation, le packing et une éventuelle validation.
Le module exige l'instance native `material_surface_field._Budget`, avec ses
caps inchangés. Il n'instancie ni budget ni horloge, n'étend aucun plafond et
ne modifie aucune fonction ou classe du core.

```python
pack_material_surface_state(
    state, *, originals, before, budget, input_hashes=None, provenance=None)

validate_material_surface_compact(
    compact, *, originals, before, budget)

expand_material_surface_compact_geometry(
    compact, *, originals, before, budget)
```

Pour le packing, `originals` vaut
`[data, provenance, budget_declaration, deadline]`. Le caller capture cette
liste avec `_capture` puis exécute l'actuel `_compile` sur `captured[0]`, sans
changer ses mathématiques ni ses gardes. `state` est cette sortie interne
fraîche, sous le même ledger ; le packer n'admet pas un état arbitraire fourni
par un client comme preuve. `before` est l'empreinte de cette capture.
Les hashes optionnels doivent égaler ceux des entrées du compilateur actuel.

Le point d'intégration d'un futur caller ROOT est donc après `_compile`, à la
place de `_base` et de son finalizer. Aucun caller public ou parcours de
production n'est ajouté ici. L'ancienne API peut continuer à produire V1.

Une consommation ultérieure capture
`[compact, budget_declaration, deadline]` avec `_snapshot` et `_hash` sous le
ledger déjà fourni, sans nouvelle instance ni nouvel instant de départ. Les
deux consumers recompilent toutes les entrées avec `_compile`. Chaque contrôle
de domaine, paire, support et rationnel est donc débité à nouveau, sans remise
à zéro. Une recompilation après la compilation peut épuiser les paires,
rationnels, inputs ou le délai ; ce refus demeure `INCOMPLETE`.

## Représentation fermée

`inputs` conserve intégralement la source, le porteur, la référence et toutes
ses UV/faces/positions, C, le champ précédent, samples, crans, relations,
targets et limites. Aucune réduction de S_fresh n'est effectuée. Une source
réelle de 743 sommets et 1098 faces resterait de cette taille ; cette unité
**n'a pas compilé ni testé cette source réelle**.

Les bindings des sommets source, samples, observations de targets,
propriétaires, crans, types de raccord et références externes restent présents.
`geometry` contient exactement trois tableaux :

| Tableau | Record |
|---|---|
| `source_carrier` | `[source_face_id, carrier_face_id, uv_polygon_cm, area_cm2]` |
| `reference_carrier` | `[reference_face_id, carrier_face_id, uv_polygon_cm, area_cm2]` |
| `source_reference_carrier` | `[source_parent_index, reference_parent_index, uv_polygon_cm, area_cm2]` |

Les deux indices parents sont des entiers explicites dans leurs tableaux
respectifs ; leurs IDs de face carrier doivent être identiques. Ils restituent
les trois IDs de faces exacts. Les IDs des coins sont retrouvés dans les
triangles complets des entrées et les poids barycentriques sont recalculés
exactement depuis ces triangles et les UV rationnels. Aucun ID, vertex ou DOF
physique n'est créé par une table de stockage.

Les UV/aires dérivées sont les chaînes canoniques `str(Fraction)` du builder
existant. Les inputs natifs restent natifs et exacts : aucun passage par float,
arrondi UV, epsilon, weld de proximité ou fusion de fractions n'est ajouté.
Les fractions proches de 0,5 et les samples de même UV mais d'IDs différents
restent distincts.

Le validateur reconstruit le champ et compare **toutes** les valeurs du format
fermé, leurs types, parents, ordre, polygones, aires et données conservées.
Il refuse un poids ajouté, parent booléen/absent, patch manquant ou chaîne
rationnelle non canonique même si le hash du payload forgé a été recalculé.
Les flags ou le reçu d'un objet fourni ne remplacent pas cette reconstruction.

`provenance` vaut `None` en absence de déclaration. Sinon, son objet JSON
opaque est capturé dès l'origine, hashé et conservé intégralement avec
`provenance_scope=NON_ADMITTED_NOT_APPLIED_TO_COMPUTATION`. Un registre déclaré
SOFT/HARD, un corps, une pose ou recette dans cet objet reste une déclaration
du caller : le nom d'un champ ne crée pas une contrainte, un pin, une revue
humaine ou une acceptation. Les relations réellement appliquées par le builder
restent uniquement celles de ses entrées validées.

## Reçu et comptabilité cumulative

Le reçu lie les hashes source/référence/C/précédent/limites/samples/crans/
relations/targets, la provenance et **le SHA du nouveau module compact**.
`code_sha256` conserve séparément les SHA compact, field et UV. L'identité de
code V1 n'est jamais présentée comme celle du nouveau packer. Les fichiers
consommés sont relus avant retour ; une mutation refuse.

Le finalizer est local à ce nouveau format. Cette divergence est nécessaire :
le finalizer V1 affecte son compteur d'octets à la taille de son unique
résultat, ce qui ne constitue pas une comptabilité cumulative de plusieurs
sorties. Il n'est ni modifié ni monkeypatché ici.

- `receipt.output.nodes/bytes` mesure cet **objet complet**, reçu inclus.
- `receipt.work.output_nodes/output_bytes` conserve les coûts cumulés depuis
  l'origine du caller, y compris toutes les finalisations précédentes.
- Chaque valeur JSON, conteneurs inclus et clés exclues, est débitée une fois
  pendant l'encodage. Les nœuds déjà consommés restent consommés après refus.
- Les passes de dimensionnement JSON sont des inspections en streaming ; elles
  ne matérialisent pas plusieurs buffers JSON complets et ne facturent pas
  plusieurs fois le même résultat. Les deux compteurs décimaux d'octets sont
  stabilisés, puis la représentation complète est débitée une fois avant les
  contrôles finaux. Un échec tardif conserve ce débit. Un cap d'octets insuffisant
  refuse avant ce débit complet ; il ne rembourse aucun résultat antérieur.

Les plafonds existants restent inchangés : output 500000 valeurs et 8 MiB,
input par défaut 200000 valeurs avec son hard cap existant, Fraction 300000
opérations, paires déclarées dans le domaine existant et phase au plus 60 s.
Aucun plafond hard historique n'est augmenté. Les limites de sécurité du
champ peuvent seulement être resserrées selon les anciens contrats.
Un résultat qui tient sous output peut encore refuser à sa capture ou sa
recompilation sous les caps input/paires. Aucun gain réel ni fin sous 60 s
n'est promis.

Le comptage et toutes les captures, lectures de code, hashes, comparaisons,
sérialisations, préservations et dernier retour partagent le même délai.
Le dernier contrôle temporel suit le dernier hash de préservation.
`elapsed_seconds` est le checkpoint avant le dimensionnement final ; les
travaux suivants peuvent encore refuser. Les observations temporelles d'un
reçu fourni ne reconstruisent pas une origine live ou une preuve du passé.

Le validateur contrôle les hashes, sizes et bornes d'un reçu fourni. Il ne
reconstitue pas l'historique entier du ledger d'un autre processus et ne
transforme pas ses compteurs déclarés en attestation runtime. Son propre reçu
est issu du ledger effectivement fourni et contrôlé pendant cet appel.

## Expansion et travail restant

L'expansion est limitée aux fixtures et retourne
`MATERIAL_SURFACE_COMPACT_GEOMETRY_EXPANSION_TEST_V1`, avec
`v1_consumer_compatible=false`. Elle rederive les records verbose de géométrie
et facture l'objet complet et son reçu comme une nouvelle sortie. Elle peut
refuser même après un packing compact réussi. Elle ne retourne pas une
compilation V1 utilisable implicitement par ses consumers.

Un observer compact séparé reste à construire pour les mesures affines,
displacements/steps, traces continues et contraintes. Il devra réutiliser le
ledger et revalider le champ complet ; ce module ne calcule pas ces mesures et
ne valide aucune faisabilité du système HARD/SOFT. Il ne démontre ni résolution
des six cages, ni présence physique, ni contacts/Cloth/fitting. L'essai col
réel, son coût, les contraintes et la production restent `NOT_EXECUTED` /
`NOT_QUALIFIED` pour cette unité.
