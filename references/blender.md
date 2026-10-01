# Blender MCP externe

Ne pas réimplémenter ni installer Blender MCP pendant une production. Découvrir ses outils disponibles et vérifier la scène avant d'agir. Le package fournit blender/operations.py à exécuter dans Blender via l'outil Python officiel ; ce fichier n'est pas un serveur MCP Blender.

Pour une opération, appeler `studio_blender_operation` avec le projet, le nom d'opération et ses arguments. Transmettre le champ `code` exactement à `execute_blender_code`. Le hook reconnaît ce point d'entrée et le dispatcher répète l'admission dans Blender. Les opérations disponibles sont prepare, inspect, garment, assemble, run_script et restore_checkpoint. Le code direct de reconstruction est refusé dans un projet rattaché. Lire les [contrôles de progression et de récupération](lifecycle-guards.md).

`run_script` sert à simulate (RECONSTRUCTING, composants cousus déjà présents), refine (REFINING), behavior (BEHAVIOR_AUTHORING), validate/export (VALIDATING). Il exige purpose, path, sha256 et component_ids ; il vérifie la copie de travail et crée un checkpoint. Behavior et export exigent également la décision silhouette liée à silhouette-review. Simulate exige aussi simulation_plan et un budget max_frames. Ce mécanisme ne constitue pas un bac à sable de Python.

prepare sauvegarde la scène courante dans un nouveau .blend sous .a3d/blender, y compris si la scène était modifiée. Il ne recharge aucun fichier et ne sauvegarde pas sur l'original. checkpoint sauvegarde une copie avant mutation. working vérifie que le fichier connecté est la copie attendue.

assemble importe les meshes admis, crée un parent par composant, conserve leurs IDs et applique rotation/échelle/recalage d'anchor. anchor_local est exprimé en unités Blender après import ; anchor_world_cm et position_cm sont en cm. Aucune fusion automatique. Le plan fixe les relations identiques à asset.json.

garment construit le maillage des panneaux et les ressorts de couture. Préparer séparément le mannequin de collision, le placement fin, la densité de maillage et le budget de simulation. Le bake n'est pas lancé par cette fonction. inspect produit des mesures sur le mesh de base ; il ne certifie ni les modifiers évalués, ni le rig, ni l'apparence.

Les hooks apportent contexte et vérifications ciblées, mais ne rendent pas l'exécution Python Blender sûre par eux-mêmes. Une exception après mutation bloque les opérations suivantes jusqu'à restore_checkpoint. Le fichier de travail échoué reste conservé ; la restauration crée une nouvelle copie.
