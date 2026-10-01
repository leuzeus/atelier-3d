---
name: route-reconstruction
description: Choisir par composant entre patrons cousus PATTERN_SEWN et reconstruction multivue MULTIVIEW_PART.
---

# route-reconstruction

Appeler studio_route_component avec les signaux observés et leurs preuves. Une structure en panneaux cousus appelle PATTERN_SEWN ; un volume rigide ou articulé appelle MULTIVIEW_PART. Une matière ou structure cachée ambiguë demande une décision humaine ciblée. Enregistrer cette décision sous route.<component_id>, avec les éléments réellement examinés, puis studio_resolve_route. Chercher la fragmentation minimale qui résout l'occlusion et la séparabilité. Ne pas créer une décision humaine à partir du seul retour du routeur.

Après l'analyse, appeler `studio_propose_pipeline` : la proposition conservée doit donner une recommandation par composant, ses raisons, les alternatives et les livrables attendus. Tous les choix, même de confiance élevée, restent des propositions jusqu'à la décision humaine. La décision `route.<component_id>` doit porter sur la preuve `pipeline-proposal` exacte, puis `studio_resolve_route` applique ce choix. Aucun package ne peut imposer une autre méthode. Après création des packages, tout changement de route exige un nouveau projet de révision conservant l'ancien.

Lire [la revue de construction](../../references/construction-review.md). Un textile cousu doit aboutir à un board dérivé des patrons réels et à une validation humaine du découpage avant sa construction dans Blender.

Pour le board à valider, appliquer le [contrat des trois volets](../../references/fabrication-board.md). La vue éclatée du volet 2 est générée avec Codex Image intégré à partir des originaux et de la demande retournée par studio_prepare_exploded_view ; conserver la sortie réelle via studio_register_exploded_view, puis placer les repères sur les pièces visibles. Le compositeur ajoute leurs noms et caractéristiques exacts. Le volet 3 utilise les contours du package avec coupe, couture, plis/milieu, droit-fil et crans appariés à une échelle commune. Mesurer les proportions contre les images sources, ouvrir le résultat, puis attendre l'approbation humaine du découpage. Une vue éclatée indisponible ou erronée ne doit pas être remplacée discrètement par un autre backend.
