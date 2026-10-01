---
name: author-3d-behavior
description: Configurer dans Blender les comportements nécessaires à un asset 3D, notamment rig, articulation ou simulation textile.
---

# author-3d-behavior

Déduire les besoins du profil de destination et du graphe de mobilité. Vérifier les capacités du Blender connecté avant toute exécution. Créer un checkpoint, puis construire les contraintes/rig/collisions appropriés au modèle réel. Tester les poses extrêmes, la séparation des articulations et la déformation. Utiliser material.schema.json et simulation.schema.json pour les données applicables. Les scripts V0.1 ne génèrent pas automatiquement un rig de personnage, un bake cloth complet ni de lip-sync : les réaliser avec Blender MCP si demandés et les déclarer NOT_EXECUTED sinon. Aucune acceptation implicite.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

L’entrée dans cette étape exige la silhouette revue sur la copie exacte. Documenter les essais rig/weighting/clearance dans behavior-validation (stage-validation.schema.json, stage BEHAVIOR_AUTHORING) avant VALIDATING lorsque le profil les exige. Pour une simulation de reconstruction cousue, fournir simulation_plan à run_script, avec max_frames et colliders explicites ; ne pas simuler à nouveau une pièce déjà acceptée. Voir le [contrat des étapes](../../references/lifecycle-guards.md).
