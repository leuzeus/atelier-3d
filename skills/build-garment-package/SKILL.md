---
name: build-garment-package
description: Créer et vérifier un package de vêtement .garmentpkg avec patrons SVG polygonaux, panneaux maillés et coutures explicites.
---

# build-garment-package

Avant chaque appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter l'opération préparée, le projet cible et ses effets attendus ; demander explicitement l'autorisation de l'utilisateur et attendre sa réponse affirmative. La préparation du code et les validations du pipeline ne valent pas autorisation d'exécution. Un refus ou une absence de réponse empêche l'appel. Si l'opération ou ses arguments changent, demander l'autorisation pour la nouvelle action. Respecter tout blocage de Codex ou du projet. Voir [le protocole Blender](../../references/blender.md).

Après le maillage dérivé, suivre [la revue de prépositionnement](../../references/sewing-placement.md) avant Cloth : `inspect_sewing_placement`, mesures des coutures/supports/colliders et rendu initial. Documenter le placement natif par panneau et sa correspondance aux bords source. Corriger la recette dérivée avec rebuild sans réécrire le package approuvé. Un rapport sans avertissement n'est pas une preuve de fitting ni un PASS local.

Lire [le contrat de package](../../references/packages.md). Utiliser garment.schema.json ; les sommets 2D en centimètres doivent correspondre exactement aux polygons de pattern.svg. Définir faces, bords de couture, orientation et placement initial de chaque panneau. Les bords nommés suivent le contour et peuvent avoir des nombres de sommets différents ; le maillage dérivé utilise une correspondance par longueur d’arc. Déclarer le type de chaque couture : permanent, closure ou detachable. La V0.1 accepte des polygones explicites ; échantillonner et vérifier les courbes avant import. Vérifier les patrons visuellement et techniquement. Construire via studio_build_package, valider et lier via studio_bind_package. La fixture assassin-garment est synthétique, pas une preuve de drapé validé.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

Le board de préparation est construit à partir des images de référence originales fournies par l’utilisateur, avant modélisation. Ne jamais utiliser le mesh produit comme sa propre référence de conception. Le dossier doit fournir `source_references` (preuves des originaux et origine dans la conversation), `source_evidence_keys` pour chaque vue et pièce, et `reference_notes` pour les indices observés ou extrapolés. Les références sources doivent être celles examinées dans le gate references. Elles sont intégrées au board et au dossier. Le type mesh-render est refusé pour les vues de ce board. Un board documentaire créé après la 3D est un diagnostic séparé et ne remplace jamais cette validation.

Pour le board à valider, appliquer le [contrat des trois volets](../../references/fabrication-board.md). La vue éclatée du volet 2 est générée avec Codex Image intégré à partir des originaux et de la demande retournée par studio_prepare_exploded_view ; conserver la sortie réelle via studio_register_exploded_view, puis placer les repères sur les pièces visibles. Le compositeur ajoute leurs noms et caractéristiques exacts. Le volet 3 utilise les contours du package avec coupe, couture, plis/milieu, droit-fil et crans appariés à une échelle commune. Mesurer les proportions contre les images sources, ouvrir le résultat, puis attendre l'approbation humaine du découpage. Une vue éclatée indisponible ou erronée ne doit pas être remplacée discrètement par un autre backend.

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
