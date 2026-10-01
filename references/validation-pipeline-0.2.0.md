# Validation de la correction pipeline / board — 0.2.0

Date : 1 octobre 2026. Source : checkout de développement du plugin.

Les journaux et artefacts `work/` cités ci-dessous sont locaux et ne sont pas distribués. Voir [la validation actuelle](../VALIDATION.md) et la CI publique pour les contrôles reproductibles.

Le défaut observé était un écart entre le workflow enregistré (projet resté ANALYZED, routes textiles non résolues, pas de packages) et une production Blender procédurale exécutée à côté. La correction porte sur le runtime, les hooks, les contrats, les outils et leurs instructions.

## Comportement livré

- Proposition de pipeline par composant conservée dans les preuves, raisons et alternatives exposées, décision humaine liée à la proposition exacte avant application de la route.
- Dossier technique obligatoire : gabarit, mensurations, matières, dimensions, pièces, assemblages, hypothèses, silhouette, mobilité et livraison.
- Board SVG généré après les données : vues orthographiques, décomposition du vêtement, patrons 2D issus des packages pour PATTERN_SEWN. Repères de coutures, droit-fil et dimensions proviennent des données vérifiées ; le dossier HTML développe les détails.
- Le board est conçu depuis les références originales : origine, preuves et liens de chaque vue/pièce sont obligatoires. Les originaux sont inclus. `mesh-render` est refusé comme base des vues du board de préparation.
- L'approbation humaine du découpage lie `construction-board`. Ni la génération du board ni une autorisation générale de produire ne l'approuvent automatiquement.
- Un changement du dossier, des originaux, des vues, du board, des packages ou des routes invalide l'admission.
- Les transitions de production, Comfy et les opérations Blender répètent l'admission. Le hook bloque les appels Blender directs et les lancements externes connus dans un projet identifié. L'opération contrôlée vérifie à nouveau les conditions dans Blender et conserve le checkpoint.
- Les projets historiques ne sont pas transformés en faux projets approuvés. L'état et les fichiers du projet historique ont été préservés.

## PASS

- Suite complète : **91 tests**, 0 échec, 0 erreur, 0 saut (`work/pipeline-guards-tests.log`). Tests de contrats, état, jobs, protocoles, nouvelles règles et commandes de hooks Windows dans cmd et PowerShell.
- Essai natif Blender en tâche de fond : `work/pipeline-blender-smoke-ref/native-smoke-result.json`. Construction effective de 4 panneaux synthétiques, 16 sommets, 8 faces, 6 arêtes de couture et modifier Cloth activé. Refus du doublon et de la preuve modifiée avant mutation. Le test utilise une scène indépendante.
- Board de test SVG rasterisé et pixels ouverts : `work/pipeline-guards-reference-visual/board-preview.png`. Les zones grises sont des références synthétiques explicitement étiquetées, pas une robe de production.
- Projet historique : admission refusée à ANALYZED en l’absence de revue construction. État canonique inchangé ; preuve privée conservée localement.
- Diagnostic documentaire exporté en PDF et PNG puis examiné visuellement. Empreinte du fichier Blender original inchangée ; référence privée non distribuée.

## NON EXÉCUTÉ / limites

- Nouveau vêtement de production construit depuis un découpage réel approuvé, drapé complet, validation native Unreal : non exécutés dans cette correction.
- Une traçabilité vérifiée ne prouve pas automatiquement la fidélité artistique de l'image générée aux originaux. C'est précisément l'objet de la revue humaine.
- Les hooks requièrent la confiance native de Codex. Le rattachement d'un chat hors projet utilise `session_id` quand l'hôte le fournit. Les outils répètent leur admission indépendamment du hook.
- Aucun hook ne constitue un bac à sable universel pour tous les programmes externes. Les scripts de simulation/finition restent du Python de confiance ; leurs entrées, stade, composants, hash et checkpoint sont contrôlés, pas toute leur sémantique.
- L'image de board portable est en SVG ; le runtime du plugin ne dépend d'aucun rasteriseur tiers. Le PNG de test a été rendu avec le runtime documentaire disponible sur cette machine.

## Fichiers clés

`a3d/planning.py`, `a3d/guard.py`, `a3d/store.py`, `a3d/tools.py`, `blender/operations.py`, `hooks/handler.py`, `schemas/construction.schema.json`, `templates/construction-dossier.json`, `tests/test_pipeline_guards.py` et `references/construction-review.md`.
