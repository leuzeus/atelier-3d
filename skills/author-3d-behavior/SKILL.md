---
name: author-3d-behavior
description: Configurer dans Blender les comportements nécessaires à un asset 3D, notamment rig, articulation ou simulation textile.
---

# author-3d-behavior

Avant chaque appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter l'opération préparée, le projet cible et ses effets attendus ; demander explicitement l'autorisation de l'utilisateur et attendre sa réponse affirmative. La préparation du code et les validations du pipeline ne valent pas autorisation d'exécution. Un refus ou une absence de réponse empêche l'appel. Si l'opération ou ses arguments changent, demander l'autorisation pour la nouvelle action. Respecter tout blocage de Codex ou du projet. Voir [le protocole Blender](../../references/blender.md).

Déduire les besoins du profil de destination et du graphe de mobilité. Vérifier les capacités du Blender connecté avant toute exécution. Créer un checkpoint, puis construire les contraintes/rig/collisions appropriés au modèle réel. Tester les poses extrêmes, la séparation des articulations et la déformation. Utiliser material.schema.json et simulation.schema.json pour les données applicables. Les scripts V0.1 ne génèrent pas automatiquement un rig de personnage, un bake cloth complet ni de lip-sync : les réaliser avec Blender MCP si demandés et les déclarer NOT_EXECUTED sinon. Aucune acceptation implicite.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

L’entrée dans cette étape exige la silhouette revue sur la copie exacte. Documenter les essais rig/weighting/clearance dans behavior-validation (stage-validation.schema.json, stage BEHAVIOR_AUTHORING) avant VALIDATING lorsque le profil les exige. Pour une simulation de reconstruction cousue, utiliser simulate_sewn avec recette, phase, essai local puis complet ; les scripts spécialisés exigent également sewing_recipe et phase dans simulation_plan. Ne pas simuler à nouveau une pièce déjà acceptée. Voir le [contrat des étapes](../../references/lifecycle-guards.md).

Pour PATTERN_SEWN, suivre [la recette native de toile](../../references/sewn-toile.md) après approbation du board : contours source conservés, maillage dérivé, mannequin auxiliaire vérifié, essais gravité/couture/contact puis sous-ensemble local, simulation complète bornée et consolidation des seules coutures permanentes. Préparer les données techniques pour l’utilisateur ; ne pas lui imposer un nouveau formulaire ni faire réapprouver un board inchangé pour ajuster la physique. Après deux échecs complets, diagnostiquer le petit cas et refaire l’essai local. Examiner les rendus avant toute conclusion artistique.


Pour les vêtements, suivre [les préparations de fitting et profils régionaux](../../references/fitting-preparation.md).
Le board décrit l'intention de matière/renfort et de plis par patron depuis les
références originales ; quelques profils partagés restent des hypothèses.
Calibrer dans Blender après pose commune qualifiée, sans coefficient arbitraire
par panneau ni chaîne/trame indépendante promise par un backend qui ne la simule
pas. Préparer les données techniques sans formulaire utilisateur. Une modification
de recette physique requalifie ses preuves techniques ; elle ne réclame pas de
nouvelle approbation d'un découpage inchangé. Les opérations natives
`prepare_fitting_envelope` et `prepare_fitting_pose` préservent la scène live ;
la mutation de stage et le local/full gardent leurs admissions et checkpoints.
