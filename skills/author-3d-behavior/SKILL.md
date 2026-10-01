---
name: author-3d-behavior
description: Configurer dans Blender les comportements nécessaires à un asset 3D, notamment rig, articulation ou simulation textile.
---

# author-3d-behavior

Déduire les besoins du profil de destination et du graphe de mobilité. Vérifier les capacités du Blender connecté avant toute exécution. Créer un checkpoint, puis construire les contraintes/rig/collisions appropriés au modèle réel. Tester les poses extrêmes, la séparation des articulations et la déformation. Utiliser material.schema.json et simulation.schema.json pour les données applicables. Les scripts V0.1 ne génèrent pas automatiquement un rig de personnage, un bake cloth complet ni de lip-sync : les réaliser avec Blender MCP si demandés et les déclarer NOT_EXECUTED sinon. Aucune acceptation implicite.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

L’entrée dans cette étape exige la silhouette revue sur la copie exacte. Documenter les essais rig/weighting/clearance dans behavior-validation (stage-validation.schema.json, stage BEHAVIOR_AUTHORING) avant VALIDATING lorsque le profil les exige. Pour une simulation de reconstruction cousue, utiliser simulate_sewn avec recette, phase, essai local puis complet ; les scripts spécialisés exigent également sewing_recipe et phase dans simulation_plan. Ne pas simuler à nouveau une pièce déjà acceptée. Voir le [contrat des étapes](../../references/lifecycle-guards.md).

Pour PATTERN_SEWN, suivre [la recette native de toile](../../references/sewn-toile.md) après approbation du board : contours source conservés, maillage dérivé, mannequin auxiliaire vérifié, essais gravité/couture/contact puis sous-ensemble local, simulation complète bornée et consolidation des seules coutures permanentes. Préparer les données techniques pour l’utilisateur ; ne pas lui imposer un nouveau formulaire ni faire réapprouver un board inchangé pour ajuster la physique. Après deux échecs complets, diagnostiquer le petit cas et refaire l’essai local. Examiner les rendus avant toute conclusion artistique.
