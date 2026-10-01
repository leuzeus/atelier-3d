# Vérification du board de fabrication — 0.4.0

Date : 1 octobre 2026. Correction dans le checkout de développement du plugin.

Les journaux et artefacts `work/` cités ci-dessous sont locaux et ne sont pas distribués. Voir [la validation actuelle](../VALIDATION.md) et la CI publique pour les contrôles reproductibles.

## Comportement livré

- Trois volets conservés : vues orthographiques, vue éclatée, patrons 2D de fabrication.
- Vue éclatée préparée pour **Codex Image intégré**, avec originaux, inventaire exact des pièces, dimensions, matières et caractéristiques. `studio_prepare_exploded_view` produit la demande ; `studio_register_exploded_view` enregistre le PNG réellement obtenu et sa référence d'appel. Ces outils ne lancent pas le moteur d'image eux-mêmes.
- Les noms exacts sont ajoutés avec traits de rappel sur la vue éclatée. Une nomenclature liée aux mêmes IDs donne les matières, dimensions et caractéristiques. Les patrons reprennent les mêmes IDs.
- Contours de coupe et de couture distincts, plis/milieu, double flèche de droit-fil, marges, quantités et instructions de coupe ; crans appariés selon les coutures et leur orientation.
- Échelle commune entre tous les patrons, avec réglette. Les vues orthographiques ont un cadrage déclaré et une hauteur commune ; les images conservent leurs proportions.
- Rapports mesurés sur les pixels originaux et proposés, couvrant face/profil/dos/éclaté. Un écart supérieur à la tolérance déclarée bloque le board.
- Les anciens boards approuvés dépourvus de ces données ne passent pas automatiquement le nouveau contrat. Une nouvelle image et une nouvelle décision humaine sont nécessaires.
- Correction de l'encodage de descriptions françaises détériorées dans certains fichiers 0.3.0 ; tous les fichiers modifiés sont lus/écrits explicitement en UTF-8.

## PASS

- Suite complète : **133 tests**, 0 erreur, 0 échec, 0 saut (`work/fabrication-tests-final.log`).
- Après le dernier ajout des positions de libellés : **56 tests ciblés** des boards, contrats, hooks et protocole (`work/fabrication-targeted-final.log`).
- Refus des métadonnées de fabrication absentes, marges dessinées insuffisantes, contours auto-intersectés, plis hors pièce, repères manquants/inversés, proportions incohérentes, libellés manquants, données modifiées après demande et provenance Comfy substituée à Codex Image.
- Vérification numérique du rapport 2:1 entre deux patrons de tailles différentes dans le SVG : leurs dimensions relatives sont conservées.
- Rendu SVG rasterisé et pixels examinés : `work/fabrication-board-preview.png` (2400 × 2294). Les aplats gris et pièces rectangulaires sont des fixtures, explicitement titrées SYNTHETIC TEST ONLY. Un chevauchement initial des labels de couture a été corrigé ; noms, légende, plis, droit-fil et crans sont visibles.
- Régression Blender 5.2.2 LTS : assemblage de pièce importée et panneaux existants, blocage après erreur et restauration passent avec les nouveaux dossiers de test. Preuve `work/native-lifecycle-c7f3f755be5a48a9954640ac16dda21b/result.json` et journal `work/fabrication-blender-regression.log`.

## Non exécuté / limites

- **Aucune nouvelle image de production n'a été générée avec Codex Image dans cet audit du plugin.** Le parcours de génération et d'enregistrement est livré ; le fournisseur est simulé dans les tests avec une référence explicitement synthétique.
- Le board réel du vêtement, ses patrons définitifs et sa validation humaine restent à produire. Les anciens modèles ne sont pas qualifiés rétroactivement.
- Les hashes et la référence d'appel déclarée n'authentifient pas seuls une exécution externe. Ne pas inventer de reçu Codex Image ni de décision humaine.
- Les contrôles de proportions supposent des points correctement relevés par l'opérateur. La fidélité artistique et l'exactitude sémantique de ces mesures nécessitent l'examen des pixels.
- Les contrôles des marges/contours utilisent des échantillons géométriques. Ce board de revue pour production 3D n'est pas une certification de patronage textile ou une impression de coupe 1:1.
- Génération GPU Comfy, simulation complète du vêtement, fitting réel, rig et import Unreal non exécutés.

Le [contrat de fabrication](fabrication-board.md) documente la préparation et la revue. La vérification de la copie installée est conservée sous `work/installed-0.4.0-verification.json` après installation native ; le rechargement du MCP attaché au chat est un contrôle distinct.
