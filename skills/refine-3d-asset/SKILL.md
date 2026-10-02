---
name: refine-3d-asset
description: Corriger un asset Blender reconstruit en topologie, raccords, silhouette, UV ou matériaux à partir de preuves visuelles.
---

# refine-3d-asset

Pour un échec de montage textile, restaurer puis utiliser [le diagnostic de prépositionnement](../../references/sewing-placement.md) avant un nouvel essai Cloth. Ajuster localement la recette de placement/support sans réécrire les patrons approuvés ni relâcher les seuils ; rebuild conserve l'ancien mesh. Ne pas annoncer un fitting réparé à partir d'une fixture ou d'un rapport sans avertissement.

Pour cadrer un mesh existant, utiliser le parcours contrôlé `frame_view` puis
capturer VIEW_3D, sans code de géométrie direct ni changement implicite de
visibilité. Les échecs Cloth conservés s'inspectent par `inspect_sewing_failure` ;
leurs mesures FAIL n'accordent aucune acceptation. Voir le
[protocole](../../references/viewport-diagnostics.md).

Comparer les rendus neutres aux références avant la correction. Définir une correction bornée par composant et créer un checkpoint avec blender/operations.py. Conserver les IDs, la provenance et les relations. Vérifier la correction par un nouveau rendu aux mêmes caméras et mesurer la géométrie concernée. Ne pas relancer les reconstructions indépendantes réussies. Si une correction invalide une pièce acceptée, conserver l'historique et créer une nouvelle révision de projet/package ; ne pas réécrire un état COMPLETE.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

Avant BEHAVIOR_AUTHORING, produire refinement-validation selon stage-validation.schema.json, stage REFINING, avec geometry/scale/orientation/separation et leurs check_evidence. Sauvegarder une copie immuable de la scène et une revue silhouette-review selon visual-review.schema.json ; présenter ses rendus contre les références, puis enregistrer l’accord réel dans le gate silhouette. Voir le [protocole des preuves](../../references/lifecycle-guards.md).
