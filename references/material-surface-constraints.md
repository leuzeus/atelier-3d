# Contraintes interpolées de surfaces matérielles

`a3d.material_surface_constraints` revalide des champs fournis, puis compile des lignes sparse exactes par identité de domaine et de nœud porteur. Il ne déplace aucun nœud, ne crée aucun porteur ou pin et n’optimise aucun vêtement. Aucun caller, schéma partagé ou parcours de production ne consomme son format.

Le discriminant est `MATERIAL_SURFACE_CONSTRAINTS_V1`. Tous les résultats sont `TEST_ONLY / NONE`, non physiques et non installables. Une compatibilité linéaire ne qualifie pas la métrique du champ, ses barres, ses traces, le drapé ou le fitting. La dépendance `material_surface_field` V3 a été stabilisée et relue avant les essais finaux de cette unité ; ses inputs et empreintes sont à nouveau contrôlés à chaque appel.

## Interface et données

```python
compile_material_surface_constraints(
    fields, relations, physical_stops, numerical_targets, *,
    certify_hard=True, budgets=None, deadline=None, clock=time.monotonic)
```

`fields` est un objet `{source_id: compiled_field}`. Son ID doit être l’ID matériel réel de `compiled_field.inputs.source` : aucun alias de domaine. Chaque champ est recompilé une fois pendant cet appel, avec contrôle UV complet, supports, positions, S_fresh entier, limites et empreintes du contrat de champ. Les flags reçus, patches mis en cache et qualifications fournies ne servent pas de preuve. Une triangulation de référence n’est jamais remplacée par une approximation aux seuls nœuds porteurs.

Les `relations` sont explicites :

```json
{
  "id": "join",
  "kind": "permanent",
  "orientation": "forward",
  "owners": [
    {"domain_id": "left", "edge_id": "bottom", "source_sha256": "SHA256",
     "samples": [{"sample_id": "start", "fraction": "0"},
                 {"sample_id": "end", "fraction": "1"}]},
    {"domain_id": "right", "edge_id": "bottom", "source_sha256": "SHA256",
     "samples": [{"sample_id": "start", "fraction": "0"},
                 {"sample_id": "end", "fraction": "1"}]}
  ]
}
```

Les deux domaines doivent être fournis. Les empreintes portent sur leurs sources matérielles réelles. La relation doit déjà figurer dans la déclaration locale de chacun des champs, avec le même type, orientation et partition. Les chaînes/segments/paramètres des références externes sont comparés à l’autre source réellement fournie. Une déclaration externe bornée ne devient donc pas une égalité 3D par simple confiance dans son flag.

Les partitions vont exactement de 0 à 1, dans l’ordre de la chaîne de bord indiquée. `reverse` inverse le parcours du second propriétaire. Aucun sample, fraction, relation ou bord n’est inventé. Deux coutures permanentes ne peuvent occuper la même portion de bord. Une relation permanente entre deux domaines fournis ne peut être omise. Les autres relations non compilées sont indiquées explicitement avec leur portée externe ou non permanente. Les fractions restent des paramètres déclarés : aucune mesure d’arc physique ou de longueur de bord n’est déduite.

Une `closure` ou `detachable` conserve son type et ses identités sans produire de lignes HARD. Aucun cran n’est déplacé ou fusionné. Les samples `.49999975746439695` et `.5` restent deux identités et deux supports rationnels distincts.

## Rôles des lignes

Chaque ligne a un `row_id` structuré, un rôle, des coefficients triés `(domain_id, node_id, weight)`, un second membre 3D exact, ses bindings matériels et le résidu du champ actuellement fourni.

- **Couture permanente — HARD** : `A_a*C_a − A_b*C_b = 0`, pour chaque paire explicitement fournie. Les coefficients proviennent des supports barycentriques exacts des deux samples réels.
- **Arrêt physique — HARD** : un input `{id, domain_id, sample_id}`. Le second membre est évalué dans le champ frais complet S_fresh à l’UV matériel exact. Aucun `target_cm` de substitution n’est accepté. Cela conserve la référence ; cela ne prouve pas que le caller a choisi les bons arrêts du produit.
- **Cible numérique — SOFT_OBSERVATION** : un input `{id, domain_id, sample_id, target_cm}` avec triplet IEEE fini explicite. Sa valeur binaire exacte et ses résidus rationnels/IEEE sont observés. Elle n’est jamais ajoutée à l’élimination HARD, même si son résidu est nul ou très grand. Le float `1/3` reste sa valeur IEEE, distincte de l’UV rationnel `1/3`.

Plusieurs identités distinctes au même support restent des lignes distinctes, même si elles sont redondantes. Une ligne dont les coefficients s’annulent demeure présente avec sa provenance. Aucun pin implicite n’est ajouté. Les contraintes métier liées à la scène, au découpage approuvé et aux arrêts source restent à établir par un adaptateur séparé.

## Certificat linéaire borné

Les colonnes sont triées par `(domain_id, node_id)` et comprennent tous les nœuds des porteurs fournis. Les lignes HARD sont triées par leur identité structurée. L’élimination de Gauss-Jordan est rationnelle exacte, avec choix du premier pivot non nul et contrôle de taille/précision/coût/échéance. Aucune tolérance numérique ou ULP n’est ajoutée.

Le certificat contient `rank_A`, `rank_augmented`, colonnes pivots, matrice augmentée réduite et combinaisons des lignes originales. Un conflit est montré par une combinaison avec membre gauche nul et membre droit non nul, localisée aux IDs de lignes concernées. `INCOMPATIBLE_EXPLICIT_HARD_ROWS` concerne uniquement le modèle linéaire et les arrêts explicitement fournis ; `pattern_impossibility=false` reste explicite.

`COMPATIBLE_EXACT_LINEAR_MODEL` signifie seulement qu’il existe une solution linéaire aux lignes HARD. Le champ C actuellement fourni peut encore avoir des résidus : `provided_field_satisfies_hard` l’indique séparément. Aucune solution optimale, métrique admissible, représentation des douze barres ou faisabilité des cibles SOFT n’est déduite. `certify_hard=false` donne `NOT_REQUESTED`, sans rang inventé.

## Horloge, coûts et préservation

La première lecture d’horloge précède l’inspection des budgets, la capture et les empreintes. Toutes les révalidations, supports, copies bornées, assemblages, éliminations, certificats et contrôles de sortie utilisent la même deadline coopérative `min(start+max_seconds, caller_deadline)`, phase ≤60s. Le programme appelant doit fournir sa deadline absolue commune ; aucune phase ne récupère 300s ni un budget par domaine. L’horloge doit être finie, monotone et sans effets de bord.

Les caps géométriques du champ sont conservés et cumulés entre domaines. Chaque champ est revalidé une fois, avec ses deux contrôles UV habituels : un couple de domaines de quatre nœuds consomme huit sommets source, huit sommets de référence et seize sommets porteurs, sans remise à zéro. La référence totale 8cm et le champ précédent du pas .5cm restent présents et empreintés ; le compilateur ne recontrôle ni ne réinitialise leurs distances.

Caps supplémentaires par appel : huit domaines, 64 relations, 64 stops physiques, 256 cibles SOFT, 256 lignes HARD, 256 nœuds inconnus, 10 000 coefficients, 65 536 entrées matricielles, 200 000 opérations d’élimination, 50 000 termes de certificat. Ils peuvent être resserrés. La matrice assemblée et la copie des trois colonnes résiduelles pour le rang augmenté sont comptées ; la matrice RREF conserve le même stockage. Les opérations rationnelles et leur précision restent également sous les caps partagés du champ. Les calculs d’élimination, y compris les combinaisons de provenance, sont facturés dans le même compteur ; un résultat partiel reste `INCOMPLETE / NONE`.

Les limites de sortie portent sur l’objet complet, reçu compris, selon le contrat corrigé du champ. Les données fournies, les champs copiés et les sorties n’ont pas d’alias mutable. Les empreintes du compilateur et des dépendances sont liées au reçu ; une empreinte de code n’est ni une preuve d’installation, ni une acceptation produit.

## Limites

Les douze barres actuelles, traces, longueurs, rang d’un futur système enrichi, mouvement entre champs, contacts, métrique, Cloth, fitting et art restent non évalués. Les essais de cette unité utilisent seulement de petits domaines portables fournis. Ils ne transfèrent aucun PASS aux six cages du produit et ne concluent pas à l’impossibilité du patron depuis un modèle auxiliaire.
