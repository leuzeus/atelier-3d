# Contrôles des étapes de production — 0.5.0

Ces contrôles prolongent la [revue de construction](construction-review.md). Ils s'exécutent dans Studio et dans le dispatcher Blender, même si l'agent oublie une instruction de skill. Ils vérifient les fichiers, leur identité et la progression ; ils ne prouvent pas la justesse artistique du contenu ni l'authenticité d'une déclaration humaine.

| Étape | Preuve nécessaire pour poursuivre |
| --- | --- |
| Génération de références | Image originale PNG enregistrée comme preuve, upload `purpose=source`, paramètre `source` obligatoire. Le graphe SD1.5 encode cette image ; chaque job conserve sa provenance. Montrer le résultat avant son acceptation. |
| Reconstruction | Rapport `reconstruction.schema.json`, tous les contrôles requis PASS avec `check_evidence`, sortie exacte et revue `visual-review.schema.json` de purpose `reconstruction`. Le rapport accepté et ses fichiers sont revérifiés à l'assemblage. |
| Assemblage | Enregistrer `assembly-plan`, le faire approuver dans le gate `assembly`. Tous les composants, leurs sorties acceptées, relations, chemin/hash de la scène et du checkpoint doivent correspondre au plan. |
| Entrée en finition | `assembly-result` émis par l'assemblage, lié au plan et à une copie immuable du résultat. Un simple brief ne remplace pas l'exécution. |
| Entrée en comportement | `refinement-validation` au format `stage-validation.schema.json`, stage `REFINING`, contrôles geometry/scale/orientation/separation avec leurs preuves. Gate `silhouette` lié à `silhouette-review`, purpose `silhouette`, images comparées aux références et copie exacte de la scène courante. |
| Entrée en validation | Pour un profil exigeant rig/weighting/clearance, `behavior-validation`, stage `BEHAVIOR_AUTHORING`, documente ces contrôles sur la scène courante. |
| Livraison COMPLETE | Rapport `final-validation`, contrôles propres à la destination, chaque fichier de preuve intact ; gate `final` lié au rapport ET à sa revue visuelle, purpose `final`, portant sur tous les fichiers livrés. Les preuves d'assemblage et de silhouette sont revérifiées. Aucun job actif/incertain. |

## Capturer une revue visuelle

Pendant la production, `frame_view` cadre un candidat visible de la copie de
travail sans mutation de géométrie ni acceptation. `inspect_sewing_failure`
conserve FAIL et pending tout en donnant accès aux positions, mappings et tracés
historiques d'un essai évalué. Voir [le protocole de diagnostic](viewport-diagnostics.md).

Sauvegarder la copie Blender de travail, puis en faire une copie byte pour byte dans un chemin unique sous `.a3d/outputs`. Ne pas utiliser le fichier de travail mutable comme archive de revue. Ouvrir les rendus PNG et les références originales côte à côte ; relever les écarts et demander la décision humaine aux jalons prévus.

Dans `visual-review.schema.json`, renseigner `asset_id`, `purpose`, `artifacts` (chemins/hashes de ces copies), `images` (rendus PNG), `reference_evidence_keys` (images du gate references) et `notes`. La revue reconstruction/final doit référencer exactement les sorties du rapport associé. À l'entrée en comportement, le hash de la copie revue doit correspondre au fichier de travail courant. Les modifications de comportement ultérieures conservent la copie revue et nécessitent une nouvelle revue finale de leurs sorties.

Dans les rapports de reconstruction, d'étape et de livraison, `check_evidence` associe chaque nom de contrôle à `{path, sha256}`. Les clés doivent correspondre exactement à celles de `checks`. Les fichiers doivent contenir les mesures, observations ou tests effectivement réalisés, avec les candidats concernés ; ne jamais créer un fichier factice pour obtenir PASS. Une même preuve peut justifier plusieurs contrôles pertinents. Les données synthétiques de `tests/` ne sont jamais des preuves d'un asset réel.

## Assemblage et récupération

`assembly.schema.json` exige `working_sha256` et `checkpoint_sha256`. Utiliser `mode=import` pour GLB/OBJ/PLY/STL ; `mode=existing` est réservé aux panneaux PATTERN_SEWN déjà construits dans cette copie de travail, avec le hash du package attaché à leurs meshes. Ce mode évite de réimporter et doubler les panneaux. Le plan conserve les relations de l'asset et indique tous les composants une seule fois.

Chaque mutation contrôlée écrit un checkpoint et une opération en cours dans SQLite. Si elle échoue ou est interrompue, les mutations et transitions suivantes sont refusées. Inspecter, puis demander `studio_blender_operation` avec `operation=restore_checkpoint`, `arguments={}` et transmettre son code exact à Blender. La restauration conserve l'ancienne scène sur disque, ouvre le checkpoint et crée une nouvelle copie de travail. Une restauration d'assemblage invalide son reçu ; préparer et faire revoir le plan pour le nouveau fichier de travail. Si Blender a été reconnecté à une autre scène, réouvrir explicitement la copie de travail du projet avant cette restauration.

Pour `run_script` avec `purpose=simulate`, fournir également `simulation_plan`, chemin relatif vers `simulation.schema.json`. Déclarer `max_frames`, intervalle, qualité, composant et collisions. Le plan référence aussi `sewing_recipe` et `phase`. Le dispatcher exige un essai local natif correspondant, applique les paramètres de la recette et vérifie le résultat physique ; une reconstruction déjà acceptée reste immuable. Il n'effectue pas de bake implicite. Les scripts restent du Python de confiance : ce contrat n'est ni un limiteur de temps d'exécution ni un bac à sable contre un script malveillant.

## Compatibilité et limites

Les anciens rapports sans ces preuves restent lisibles mais ne permettent plus de franchir les jalons renforcés. Conserver les historiques, compléter les preuves réellement disponibles et recueillir les décisions manquantes. Ne pas inventer d'approbation ni modifier SQLite pour contourner un refus. Pour modifier une reconstruction déjà acceptée, créer une nouvelle révision du projet.

Un fichier haché et un label PASS ne prouvent pas une silhouette fidèle, un patron réalisable, une simulation stable ou un bon import Unreal. Le contrôle humain et les tests réels du projet restent indispensables. Les hooks nécessitent la confiance native Codex ; les outils externes non contrôlés ne constituent pas une surface hermétiquement bloquée.

Pour la reconstruction textile, suivre [la recette native](sewn-toile.md) : `garment`, `inspect_sewing_placement`, revue du montage initial, `simulate_sewn` local puis full, `freeze_sewn`. L'inspection vérifie la copie, le package, la recette, le repos, les supports et les colliders sans écrire de fichier ni pending ; elle ne libère aucun échec. Chaque tentative native archive aussi ses mesures initiales. Les réglages techniques restent séparés des décisions humaines de conception.

Pour un ancien import dont le reçu unique a été perdu, `verify_legacy_import`
contrôle la preuve dans un checkpoint avant toute migration, sans créer d'opération
en attente. Les nouveaux reçus `garment` sont immuables et séparés par composant,
avec le SHA du package. Voir [la récupération des reçus](blender-continuity.md).
