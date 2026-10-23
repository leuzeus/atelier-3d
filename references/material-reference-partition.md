# Références UV exactes et certificats de partition

`MATERIAL_REFERENCE_PARTITION_V1` est un **nouveau format portable** de construction UV. Il conserve tous les seeds rationnels, les partitions aux sections V, leurs parents/enfants et les identités matérielles. Il prépare des données auxiliaires `TEST_ONLY`, `qualification=NONE`, sans scène installable.

Cette unité ne modifie aucun guide existant, validator de cage, schéma public, caller ou solveur. Elle ne produit ni position 3D, ni S_fresh, ni couplage de coutures. La métrique, les contraintes interpolées, les douze barres, les traces, les contacts, Cloth, le fitting et la revue artistique restent non évalués.

## Interfaces

```python
prepare_material_reference_partition(
    sources, sections, subdivisions, binding,
    material_samples=None, budgets=None, deadline=None, clock=time.monotonic,
)
verify_material_reference_partition(
    compiled, budgets=None, deadline=None, clock=time.monotonic,
)
```

Une source est un disque triangulaire fourni explicitement : `id`, `uv_cm`, `triangles`, `vertex_ids`, `face_ids`, éventuellement `edges`. Les nombres natifs finis sont interprétés comme leurs valeurs binaires exactes ; les chaînes rationnelles doivent être canoniques. Il n'existe aucune tolérance UV ni promotion d'un point de guide arrondi en support source.

Chaque petite source subit les contrôles de topologie, liens de sommets, winding **et les intersections exhaustives de toutes ses paires de triangles**. Les contacts doivent être conformes aux véritables sommets/arêtes partagés. Un préflight refuse les paires qui ne tiennent pas dans le ledger global, même si les tailles source passent. Euler/winding ou un flag fourni ne constituent pas un certificat accepté.

`subdivisions` est un entier explicite entre 2 et 16. Chaque seed est calculé par `Σ Fraction(source_uv) × poids_entier / subdivisions`, pour tous les points, avec identités des sommets source. Les domaines, faces et sommets sont ordonnés par leurs IDs ; permuter les tableaux source, les faces ou les sections conserve les tables géométriques et leurs identités. Le SHA des entrées brutes change lorsque leurs octets changent.

Une section est `{id, domain_id, v_cm}`. Le clipping V garde ses coordonnées rationnelles jusqu'à la sortie ; les valeurs proches restent différentes. Des sections distinctes au même V exact conservent leurs IDs dans les entrées, même si elles définissent une seule ligne géométrique. Une section hors du domaine V source est refusée.

## Échantillons et insertions

Un échantillon possède `id`, `domain_id`, `role`, `support`, et éventuellement `metadata` ou une `relation_ref={id,kind,orientation}`. Les trois rôles sont :

- `material_sample` : identité matérielle et UV exact, sans insertion dans le maillage ;
- `notch` : cran distinct, sans conversion implicite en nœud ;
- `reference_node` : demande explicite d'insertion dans la référence UV.

Les supports admis sont exclusivement :

- `{kind: source_vertex, vertex_id}` : sommet original existant ;
- `{kind: source_segment, vertex_ids: [a,b], fraction}` : arête originale existante, avec fraction locale exacte entre 0 et 1 et ordre explicite ;
- `{kind: source_face, face_id, weights: [[vertex_id,weight],...]}` : face originale et poids non négatifs dont la somme vaut exactement 1.

Les poids et les IDs sont revalidés. Les UV libres/arrondis, références absentes, fractions hors segment et faux barycentriques sont refusés. Un point inséré sur une arête coupe toutes ses faces propriétaires ; une insertion intérieure subdivise sa vraie face. Les parents retirés de la triangulation active restent dans `triangle_archive` et `insertion_steps`, avec les enfants et la même aire exacte. Aucun triangle source n'est supprimé ou remplacé par une référence grossière.

Les crans proches, par exemple une fraction `.49999975746439695` et `1/2`, restent des échantillons distincts. Un nœud matériel géométriquement identique est partagé uniquement par égalité rationnelle et égalité de son support source ; ce partage exact n'efface aucune identité d'échantillon. Il n'y a aucun weld de proximité. Une `closure` ou une attache `detachable` reste une référence déclarée ; aucune relation, égalité 3D, couture ou pin n'est créée.

## Tables globales et certificat

La sortie conserve `global_nodes`, `seed_parents`, `section_cells`, `insertion_steps`, `triangle_archive`, `global_triangles` et `work_views`. Les vues par face source sont des fenêtres de traitement qui référencent les tables entières ; elles ne sont ni des patrons ni des coutures. Les tables actives couvrent la source, tandis que l'archive conserve l'histoire de leurs subdivisions.

Les cellules proviennent d'un clipping rationnel déterministe des vrais parents uniformes. La construction contrôle la somme des aires signées des enfants et leur orientation. Le certificat conserve les parents, leurs coordonnées/supports et tous leurs enfants. Le vérificateur revalide exhaustivement les petites sources, **reconstruit** les seeds/cellules/insertions et compare toutes les tables, identités et champs ; il ne fait pas confiance à un statut ou au reçu fourni.

Il s'agit d'un certificat spécifique à cette construction. Le module n'accepte pas une triangulation dense arbitraire grâce à une preuve Euler/winding générique. Les contrôles des anciens formats ne sont pas remplacés.

## Identités et portée de l'invalidation

`binding` exige `candidate_id`, `run_id`, `predecessor_candidate_id`, `predecessor_run_id`, `source_sha256`, `recipe_sha256`, `body_sha256`, `code_sha256`. Les deux IDs nouveaux doivent différer des prédécesseurs lorsqu'ils sont fournis. `source_sha256` est le SHA du JSON compact canonique des **meshes source effectivement fournis**, pas le SHA binaire d'un `.garmentpkg`. Le lien au package approuvé doit être vérifié et enregistré par le caller ; le témoin du col le fait séparément.

`code_sha256` doit correspondre au module actif. Les dépendances de capture/comptabilité sont aussi empreintées et recontrôlées ; elles font partie du certificat. Les identités recette/corps restent des références déclarées : ce module ne lit pas leur géométrie et ne les qualifie pas. Il ne crée pas de run SQLite ni ne vérifie un historique canonique ; l'intégrateur futur devra enregistrer ces bindings.

La sortie porte `NEW_CANDIDATE_AND_RUN_ONLY_NO_EXISTING_S_FRESH_REPLACEMENT_OR_BUDGET_RESET`. Elle ne remplace pas S_fresh d'un ancien run, ne réattribue pas ses 8 cm ou son temps restant, et n'importe aucun PASS antérieur. La création du nouveau champ 3D, sa référence fraîche avant injection et ses contrôles seront des opérations distinctes. L'acceptation humaine des sources et du corps reste une décision source ; elle ne devient pas une preuve de fitting.

## Limites déclarées pour ce nouveau format

Les limites globales diffèrent explicitement des limites locales 4 000/8 000 de `MATERIAL_SURFACE_FIELD_V1`, qui demeurent inchangées. L'enveloppe de construction provient du générateur `source_seam_coupling` :

| Budget global | Défaut | Plafond autorisé |
|---|---:|---:|
| Points source | 20 000 | 20 000 |
| Faces source | 20 000 | 20 000 |
| Nœuds de référence créés | 70 000 | 70 000 |
| Triangles produits, parents compris | 131 072 | 131 072 |
| Sections / échantillons | 10 000 chacun | 10 000 chacun |
| Paires source et recherches d'insertion | 250 000 | 2 000 000 |
| Opérations rationnelles | 300 000 | **5 000 000, propre à ce nouveau format** |
| Précision rationnelle | 4 096 bits | 4 096 bits |
| Valeurs natives parcourues en capture/revalidation | 500 000 | 500 000 |
| Valeurs de la sortie entière | 500 000 | 500 000 |
| Entrée / sortie JSON compact UTF-8 | 8 MiB chacune | 8 MiB chacune |
| Durée d'une opération | 60 s | 60 s |

Les nœuds et triangles produits sont comptés cumulativement : retirer un parent de la table active ne rembourse pas son coût. Tous les domaines/vues partagent le même ledger. Les rationnels et leurs intermédiaires calculés sont bornés ; les paires des sources sont préflight-refusées si elles excèdent le budget. La capture des trois fichiers de code est séparément bornée à 1 MiB par fichier et demeure sous la même horloge.

L'échéance absolue commence avant copie/hash ; elle est `min(start + max_seconds, caller_deadline)`. Tous les contrôles, le clipping, la reconstruction du certificat, la sortie complète avec reçu et le tout dernier hash passent sous cette même échéance. Aucune expiration ne renvoie un résultat qualifié. La dépendance de comptabilité V3 inclut les valeurs et octets du reçu dans la sortie complète. Son champ `receipt.elapsed_seconds` est un snapshot antérieur à la sérialisation complète finale : `receipt_elapsed_scope` le précise ; le contrôle de l'échéance terminale reste effectué après celle-ci. Le témoin enregistre aussi la durée réelle externe de l'appel.

Chaque interface est une opération bornée. Un caller qui prépare puis lance une seconde vérification dans une même unité doit passer la même échéance et déduire explicitement le travail déjà consommé de son enveloppe globale ; un reçu fourni ne donne aucune permission de recréer un budget. Le vérificateur charge sa reconstruction et sa traversée supplémentaires. Les caps autorisés ne prouvent pas qu'un cas donné s'achève avant l'échéance.

Les échecs lèvent `StudioError` avec `REFUSED` ou `INCOMPLETE`, une raison et `qualification=NONE`. Une sortie trop volumineuse est refusée ; ses plafonds ne sont pas augmentés automatiquement pour traiter les six domaines.

## Preuves de cette première unité

Les fixtures vérifient notamment n=8 avec clipping interne, aire/frontière/supports exacts, permutation, rotation/échelle, deux windings, faux parents/poids/faces, disparition/duplication de faces, chevauchement malgré un disque combinatoire, insertions sur arête/intérieur, crans proches, mutation, caps et expiration après le dernier hash.

Le témoin réel traite **uniquement le col** du package `771eddd4…` : source 15 sommets/13 faces, n=8, deux sections correspondant aux extrémités originales, 477 nœuds, 832 triangles et 13 vues. Ses 751 samples incluent huit crans ; aucun n'est promu en nœud. L'aire rationnelle est égale au patron original. Les 367 087 opérations rationnelles observées dépassent le défaut 300 000 ; le témoin déclare donc expressément le plafond de 5 000 000. Le clipping interne est prouvé sur les fixtures, pas déduit des seules sections d'extrémité de ce col.

Ce témoin n'est pas la reconstruction du guide courant à 743 contrôles : il conserve les supports des 743 contrôles comme samples et démontre le nouveau canal source exact. Il ne produit ni cible 3D, ni S_fresh, ni surface récupérée, ni qualification textile. Les cinq autres tableaux réels et les futurs couplage/exécuteur restent non exécutés dans cette unité.
