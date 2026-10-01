# Blender MCP externe

Ne pas réimplémenter ni installer Blender MCP pendant une production. Découvrir ses outils disponibles et vérifier la scène avant d'agir. Le package fournit blender/operations.py à exécuter dans Blender via l'outil Python officiel ; ce fichier n'est pas un serveur MCP Blender.

Pour une opération, appeler `studio_blender_operation` avec le projet, le nom d'opération et ses arguments. Transmettre le champ `code` exactement à `execute_blender_code`. Le hook reconnaît ce point d'entrée et le dispatcher répète l'admission dans Blender. Les opérations disponibles sont prepare, resume, inspect, frame_view, inspect_sewing_failure, verify_legacy_import, garment, simulate_sewn, freeze_sewn, assemble, run_script et restore_checkpoint. Le code direct de reconstruction est refusé dans un projet rattaché. Lire les [contrôles de progression et de récupération](lifecycle-guards.md).

Pour cadrer les pixels, utiliser `frame_view` avec l'ID du composant et le nom
exact retourné par l'inspection, puis capturer `VIEW_3D`. Ne pas appeler la
navigation directe pour changer implicitement sélection/visibilité. Après un
échec Cloth, `inspect_sewing_failure` lit le diagnostic de la tentative, avec
projections et positions évaluées ; il ne fait pas passer l'essai. Lire le
[protocole de cadrage et diagnostic](viewport-diagnostics.md).

`run_script` sert à simulate (RECONSTRUCTING, composants cousus déjà présents), refine (REFINING), behavior (BEHAVIOR_AUTHORING), validate/export (VALIDATING). Il exige purpose, path, sha256 et component_ids ; il vérifie la copie de travail et crée un checkpoint. Behavior et export exigent également la décision silhouette liée à silhouette-review. Simulate exige aussi simulation_plan, sewing_recipe, phase et un essai local natif correspondant. Ses paramètres et sa réponse physique sont vérifiés ; préférer simulate_sewn pour le parcours standard. Ce mécanisme ne constitue pas un bac à sable de Python.

prepare sauvegarde la scène courante dans un nouveau .blend sous .a3d/blender, y compris si la scène était modifiée. Il ne recharge aucun fichier et ne sauvegarde pas sur l'original. checkpoint sauvegarde une copie avant mutation. working vérifie que le fichier connecté est la copie attendue.

Pour une session existante, `resume` avec `arguments={}` crée un checkpoint de la
scène connectée, y compris ses changements non enregistrés. Le chemin de travail,
le fichier de travail sur disque, `session.json` et les décisions restent inchangés.
Une scène étrangère, une opération en échec ou un projet COMPLETE sont refusés.
Ne pas effacer la session ni provoquer une mutation échouée pour obtenir cette copie.
Le [protocole de continuité](blender-continuity.md) décrit aussi la mise à jour du
dispatcher et la migration contrôlée des panneaux 0.4.0.

`verify_legacy_import(package_dir, checkpoint_receipt)` contrôle l'objet initial
dans un checkpoint historique lorsque le reçu d'import a été remplacé par celui
d'un autre composant. Il ne démarre pas une mutation. Après résultat vérifié,
`garment` accepte `legacy_checkpoint_receipt` pour la récupération native ; suivre
le protocole et conserver les arguments de diagnostic d'un mesh densifié.
Chaque nouvelle opération `garment` produit un reçu immuable associé au composant
et au package, avec un chemin/SHA retournés et un lien dans l'objet Blender.

assemble importe les meshes admis, crée un parent par composant, conserve leurs IDs et applique rotation/échelle/recalage d'anchor. anchor_local est exprimé en unités Blender après import ; anchor_world_cm et position_cm sont en cm. Aucune fusion automatique. Le plan fixe les relations identiques à asset.json.

`garment(package_dir, recipe_path)` dérive le maillage des panneaux sans changer les contours approuvés. `rebuild=true` archive une précédente simulation non acceptée avant de créer sa nouvelle variante. `simulate_sewn` évalue une recette bornée, d'abord locale puis complète ; `freeze_sewn` consolide exclusivement les paires permanentes. Suivre [le parcours de toile cousue](sewn-toile.md). `inspect` mesure le mesh de base et les colliders auxiliaires évalués ; il ne certifie ni le rig ni l'apparence.

Les hooks apportent contexte et vérifications ciblées, mais ne rendent pas l'exécution Python Blender sûre par eux-mêmes. Une exception après mutation bloque les opérations suivantes jusqu'à restore_checkpoint. Le fichier de travail échoué reste conservé ; la restauration crée une nouvelle copie.
