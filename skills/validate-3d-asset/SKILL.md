---
name: validate-3d-asset
description: Valider un asset 3D selon sa destination et distinguer résultat technique, comparaison visuelle et acceptation humaine.
---

# validate-3d-asset

Le cadrage natif `frame_view` aide à capturer les pixels d'un candidat identifié,
sans le modifier. Les diagnostics `inspect_sewing_failure` restent FAIL et
historiques, même après restauration ; ne jamais les utiliser comme preuve PASS.
Lire le [protocole de cadrage/diagnostic](../../references/viewport-diagnostics.md).

Lire [la validation de production](../../references/validation.md). Inspecter la géométrie dans Blender et ouvrir les rendus. Pour chaque reconstruction, conserver un rapport reconstruction.schema.json lié au hash du package et du mesh ; studio_accept_reconstruction exige tous les checks PASS. Construire ensuite validation.schema.json : profil, contrôles nécessaires, fichiers et hashes, preuve visuelle. Enregistrer final-validation, montrer les rendus à l'utilisateur et enregistrer sa décision final liée au rapport exact. studio_transition COMPLETE refuse les fichiers modifiés, les jobs encore actifs ou les contrôles manquants. Ne pas fabriquer des PASS pour satisfaire la machine d'état.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

Chaque checks doit avoir une entrée check_evidence vérifiable. Renseigner visual-review.schema.json avec fichiers candidats, rendus PNG et clés des références approuvées. La décision final doit inclure final-validation ET sa visual_review_evidence. Le profil game exige target_import ; un vêtement ou une pièce articulée exige aussi rig/weighting/clearance. Lire les [contrôles des étapes](../../references/lifecycle-guards.md) et ne pas déclarer un test moteur non exécuté PASS.

Pour le board à valider, appliquer le [contrat des trois volets](../../references/fabrication-board.md). La vue éclatée du volet 2 est générée avec Codex Image intégré à partir des originaux et de la demande retournée par studio_prepare_exploded_view ; conserver la sortie réelle via studio_register_exploded_view, puis placer les repères sur les pièces visibles. Le compositeur ajoute leurs noms et caractéristiques exacts. Le volet 3 utilise les contours du package avec coupe, couture, plis/milieu, droit-fil et crans appariés à une échelle commune. Mesurer les proportions contre les images sources, ouvrir le résultat, puis attendre l'approbation humaine du découpage. Une vue éclatée indisponible ou erronée ne doit pas être remplacée discrètement par un autre backend.

Pour PATTERN_SEWN, suivre [la recette native de toile](../../references/sewn-toile.md) après approbation du board : contours source conservés, maillage dérivé, mannequin auxiliaire vérifié, essais gravité/couture/contact puis sous-ensemble local, simulation complète bornée et consolidation des seules coutures permanentes. Préparer les données techniques pour l’utilisateur ; ne pas lui imposer un nouveau formulaire ni faire réapprouver un board inchangé pour ajuster la physique. Après deux échecs complets, diagnostiquer le petit cas et refaire l’essai local. Examiner les rendus avant toute conclusion artistique.
