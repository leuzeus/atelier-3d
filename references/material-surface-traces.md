# Observation continue des traces matérielles

`a3d.material_surface_traces` observe des champs complets **fournis** le long de chemins UV explicites. Son discriminant est `MATERIAL_SURFACE_TRACES_V1`. Les sorties sont `TEST_ONLY / NONE`, non physiques et non installables. Aucun caller de production, solveur, Blender, Cloth ou fitting ne consomme ce contrat.

```python
observe_material_surface_traces(fields, traces, bars=None, *, context,
    budgets=None, deadline=None, clock=time.monotonic)
```

`fields` est un objet par ID matériel réel de champs `MATERIAL_SURFACE_FIELD_V1` déjà compilés. Chaque champ est **recompilé une fois** dans cet appel ; ses flags, patches et ancien statut ne servent pas de preuve. Source, porteur, référence fraîche entière, candidat, précédent éventuel, limites et empreintes sont revalidés. Les métriques de surface et la compatibilité des contraintes ne sont pas évaluées par cet observateur.

## Chemins et provenance

```json
{
  "id": "collar-path",
  "domain_id": "collar",
  "source_sha256": "empreinte-de-la-source-exacte-du-champ",
  "vertices": [
    {"id": "start", "source_vertex_id": "original-corner"},
    {"id": "mid", "sample_id": "material-mid", "fraction": "1/2"},
    {"id": "end", "uv_cm": [4, 0], "target_cm": [1.3333333333333333, 0, 0]}
  ]
}
```

Une trace fournit un ID unique, son domaine, l'empreinte JSON canonique de **sa source matérielle exacte** et au moins deux sommets ordonnés. Chaque sommet a un ID distinct et exactement un binding `sample_id`, `source_vertex_id` ou `uv_cm`. Les UV sont des nombres natifs finis ou des chaînes rationnelles canoniques. Leurs valeurs binaires sont exactes, sans epsilon, ULP favorable ou arrondi de proximité.

Une fraction optionnelle reste un paramètre déclaré dans [0,1], pas une mesure d'arc. Les voisins de 0,5 restent distincts. Deux IDs de même UV restent également distincts : un segment UV nul conserve ses deux identités et sa mesure nulle. Aucun sommet physique, weld ou pin n'est créé. Un `target_cm` fourni est un triplet IEEE fini, observé comme `SOFT_OBSERVATION` avec résidu rationnel et résidu après conversion binaire64 ; il ne produit aucune ligne HARD.

`edge_id`, facultatif, lie le chemin à un vrai bord nommé de la source. `orientation` vaut `forward` ou `reverse`. L'ordre doit suivre la chaîne déclarée. Une corde qui saute un coin géométrique du bord refuse `MISSING_SOURCE_CORNER` ; aucune nouvelle coordonnée ou relation n'est inventée. Sans `edge_id`, le chemin est une polyligne UV fournie dont la couverture dans le domaine source est contrôlée, sans qualification d'une relation métier implicite.

`context` contient obligatoirement les cinq champs `source_package_sha256`, `body_sha256`, `pose_sha256`, `recipe_sha256`, `generator_sha256` : chacun est une empreinte SHA256 déclarée ou explicitement `null`. `metadata` borné est facultatif. Les valeurs sont liées au reçu et toute modification change l'identité de l'observation. Leur provenance externe n'est pas vérifiée par le module : `context_validation=CALLER_DECLARED_IDENTITIES_ONLY`, avec liste des identités nulles. Le module ne certifie pas un corps accepté, une pose ou une recette provider depuis cette déclaration.

## Toute la restriction affine est observée

Chaque segment est clippé rationnellement contre toutes les faces source, référence et porteur. L'union exacte des paramètres de rencontre fournit les cassures, même entre les samples. Pour chaque intervalle, un support existe sur toute sa longueur dans chacun des trois domaines. La couverture complète de [0,1] est vérifiée ; endpoints dedans et passage dehors ne suffisent pas.

Les points d'événement gardent les supports source, porteur et référence, les valeurs exactes de C/S_fresh/previous et leurs erreurs de conversion IEEE. Les morceaux gardent leurs paramètres, toutes les faces couvrantes et les supports au milieu. Tangences et sommets ne créent pas de morceau de longueur positive supplémentaire. Une trace sur une arête partagée n'est pas comptée deux fois : les faces candidates doivent donner le même support sparse global, selon le contrat UV existant. Les deux windings cohérents sont supportés.

Les champs C, S_fresh et précédent sont mesurés séparément. Les douze barres et les six traces d'un candidat ne sont pas supposées exister par leur nombre : le caller doit les déclarer exactement. Une barre contient `id`, `trace_id`, `start_vertex_id` et `end_vertex_id`, dans l'ordre de la trace. Sa corde entre endpoints et la longueur continue de sa restriction sont retournées séparément. `source_length_cm`, positif et IEEE fini, permet d'observer un intervalle de résidu de corde ; aucune qualification de longueur source ou de matière n'en découle.

## Encadrement des normes et bandes explicites

Chaque carré de norme est rationnel exact. Un calcul binaire64 initial, mis à l'échelle pour les grands/petits carrés, propose un encadrement ; les deux carrés des bornes sont comparés **rationnellement** au carré exact, puis élargis jusqu'à une preuve ou un cap/délai. Les approximations ne décident pas ces comparaisons. Les bornes rationnelles des morceaux sont ajoutées exactement ; la conversion finale est dirigée et observée. Une norme n'est pas appelée rationnelle exacte quand sa racine est irrationnelle.

Sans `length_band`, le statut est `MEASURED_NO_ACCEPTANCE_BOUND`. Une bande explicite contient `quantity`, `lower_cm`, `upper_cm`, IEEE finis et ordonnés sans marge ajoutée. La quantité vaut `candidate_continuous_trace_length` pour une trace et `candidate_chord_length` pour une barre. L'encadrement entièrement inclus donne `WITHIN_DECLARED_BAND`, disjoint `OUTSIDE_DECLARED_BAND`, chevauchant `INDETERMINATE_BOUND_OVERLAP`. Ces statuts sont des observations, avec qualification `NONE` ; ils ne donnent pas un PASS produit. Un encadrement peut chevaucher une bande ponctuelle même si la longueur exacte est égale à son centre : aucune réussite n'est inventée.

`historical_observation` peut conserver un document JSON borné, lié au reçu. Il n'est **jamais** interprété comme une allowance de longueur continue. Les 12 cordes historiques, les 362 subdivisions et les six sommes gardent leurs portées ; leurs tolérances IEEE ne couvrent pas les cassures supplémentaires du champ. Le module ne les augmente pas avec ses erreurs de conversion, ne substitue pas `cg_tolerance` ou les limites d'étirement, et ne qualifie pas une égalité partenaire.

`partner_trace_id` doit nommer une trace fournie. Son contrôle continu reste `NOT_ASSESSED_NO_CONTINUOUS_TRANSPORT`. `require_continuous_partner=true` refuse `MISSING_TRANSPORT` : cette première API n'accepte ni ne fabrique un transport continu entre partenaires. Une future extension devra le déclarer et le faire relire.

## Une seule horloge et un seul ledger dans l'appel

L'observateur réutilise le budget du compilateur de contraintes, sans nouveau cap : domaine≤8 ; caps existants du champ/UV pour géométrie, paires, patches, queries, précision et opérations rationnelles, nœuds/octet input et output. Une première lecture d'horloge précède capture, copie et empreinte. Tous les domaines, révalidations, clipping, événements, supports, normes, rendus et contrôles finaux partagent `min(start+max_seconds, caller_deadline)`, phase≤60s. La deadline du programme doit être absolue et créée avant ses phases ; aucune durée historique ne la reconstitue.

Le clipping face↔segment consomme `pair_checks` et chaque intersection rencontrée `intersection_patches`. Tous les événements évalués, y compris les sommets déclarés et ceux ajoutés par les faces, consomment `queries` ; les contrôles de support au milieu des morceaux en consomment aussi. Les supports sont débités sur `patch_vertex_checks`. Le coût des opérations nouvelles utilise `fraction_operations` et `max_fraction_bits`. Les primitives UV réutilisées conservent leurs contrôles existants de géométrie/comparaisons/précision, sans prétendre compter toutes leurs opérations élémentaires dans le nouveau parcours.

Les champs sont revalidés une fois chacun avec leurs deux validations UV et triple refinement habituels ; leurs coûts s'ajoutent à ceux des traces. La capacité est vérifiée avant les groupes de paires et de queries connus. Aucun débit n'est rendu après un refus. L'exception porte `work`, `phase` et `absolute_deadline` quand le budget a été capturé ; les caps/délais donnent `INCOMPLETE / NONE`, les autres refus `REFUSED / NONE`. Aucune sortie tronquée n'est déclarée complète.

La sortie entière, reçu inclus, est bornée selon `_finish` V3 : nœuds JSON et octets compacts UTF-8 exacts, compteurs stabilisés, empreintes de préservation et dernière vérification de délai **après le dernier hash**. Les sorties et entrées ne partagent aucun alias mutable. Le reçu lie les domaines, les chemins, barres, contexte et code observateur/dépendances. Une modification de C/S_fresh/previous, des sources, corps/pose/recette/générateur, identités/chemins/fractions, limites ou code invalide les preuves dépendantes.

Les appels séparés au compilateur de contraintes et à cet observateur n'ont pas encore de ledger de programme commun : `cross_api_budget_qualification=NOT_QUALIFIED_WITHOUT_PROGRAM_EXECUTOR`. Fournir les mêmes caps à deux appels ne les rend pas partagés. Cette API ne remet ni déplacement de 8 cm ni pas de 0,5 cm à zéro ; elle conserve les données et limites du champ sans réévaluer ces contrôles de surface.

## Portée des essais

Les tests utilisent des petits champs fournis, dont le témoin √2+1 contre √5, un domaine concave, une référence à cassure indépendante, fractions voisines et cibles IEEE non rationnelles binaires. Le champ du témoin de cassure n'a pas une métrique matière admise ; les plafonds ne sont pas élargis pour lui. Les six cages réelles, les barres actuelles du vêtement complet, les contraintes/contacts/Cloth/fitting/mouvements et l'intégration de production restent non exécutés. Un refus auxiliaire n'indique pas une impossibilité de patron ou vêtement.
