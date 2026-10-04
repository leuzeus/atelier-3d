# Programme d'automatisation Atelier 3D

Plan approuvé par l'utilisateur le 3 octobre 2026. Base : branche
`codex/garment-automation-v1`, commit `8dfeac77c3b1bc3b11a4dbe6401eb2b1bb0a54ea`,
version 0.7.0-rc.2. Le programme est suivi ici pendant l'implémentation.

## Objectif et acceptation

Produire un parcours reproductible depuis les références et les données
approuvées jusqu'à une scène Blender animable, puis publier et installer une
seule préversion finale. Les calculs, corrections et enchaînements vivent dans
le runtime ; ils ne dépendent pas d'ajustements géométriques successifs par IA.

L'acceptation produit porte sur 15 pièces textiles et une boucle rigide, sur une
seule cible principale à 180 cm choisie après revue de ses mensurations. Les
fonctions génériques sont testées sur les deux bases du catalogue. Le dossier
approuvé vise Blender animation : marche, flexion des coudes, élévation des bras
et liberté des pans. Aucun moteur supplémentaire n'est imposé.

Originaux, patrons, découpage, typage des raccords et critères restent conservés.
Toute modification de conception forme une variante distincte à examiner.
Windows/Python/Blender natifs ; aucun WSL. Les travaux générés restent sur G:.
L'acceptation anatomique et artistique et les changements de conception sont
des décisions humaines réelles, liées aux fichiers examinés.

## Architecture et interfaces approuvées

Réutiliser SQLite, le planificateur, les packages, le dispatcher Blender, les
checkpoints, contrôles métriques et contacts, et le moniteur de convergence.

| Interface proposée | Responsabilité |
| --- | --- |
| `studio_prepare_body_target` | Préparer la création native d'une variante depuis une sélection et des cibles explicites |
| `studio_compile_production_dossier` | Compiler références, rôles, bords, couches, coutures et mesures approuvés |
| `studio_create_run` | Enregistrer programme et budgets vêtement, ComfyUI, matière, mouvement ou export |
| `studio_next_run_step` | Réconcilier le dernier résultat et préparer/effectuer la prochaine étape admissible |
| `studio_run_status` | Lire progression, preuves, défauts, pièces restantes et prochaine action |
| `studio_request_run_stop` | Arrêt contrôlé avec conservation des observations |
| `studio_prepare_workflow_variant` | Variante ComfyUI traçable, paramètres, diff et compatibilité |
| `studio_reconcile_comfy_job` | Réconcilier une soumission incertaine sur preuve non ambiguë |

Chaque unité lie run/groupe/étape/tentative, code et entrées exacts, corps/pose,
recette, dépendances, budgets, checkpoint, sorties et raison d'arrêt. État
d'exécution et qualification restent distincts. Les résultats renvoient le reçu
complet et la prochaine action admissible.

La reprise V1 se fait aux frontières : après interruption Cloth, restaurer
l'entrée et rejouer l'étape. Aucun redémarrage dynamique intermédiaire n'est
promis sans preuve des vitesses, caches et état physique restaurés.

Avant chaque appel `execute_blender_code`, présenter le code/opération exacts et
attendre l'autorisation utilisateur prévue. Le transport automatisé ne l'accorde
pas et ne contourne aucun refus hôte. Des arguments modifiés préparent une
nouvelle action. Les essais natifs de développement sont isolés et ne touchent
jamais une instance ou une scène personnelle.

## Lots et progression

| Lot | Livrable | Critère de sortie | État |
| --- | --- | --- | --- |
| L0 | Identités, runtime, dépendances, journal, diagnostics et temps | Bilan généré depuis preuves, historique identifié | EN_COURS |
| L1 | Ingestion, compilation des rôles/bords/couches/crans/coutures et packages | Déterminisme, 15 textiles + boucle, lacunes localisées, aucune relation inventée | EN_COURS |
| L2 | Mannequin préparé systématiquement et remesuré | Deux variantes 180 cm réouvrables, revue et cible principale choisie | EN_COURS |
| L3 | Cage anatomique et contrôles corporels bornés | Résidus mesurés, régions protégées, refus des cibles impossibles | A_REALISER |
| L4 | Guides col, devant intérieur, capuche, empiècements et épaules | Couverture source complète, métrique et contacts contrôlés | A_REALISER |
| L5 | Corrections rigides puis relaxation contrainte séparée | Réduction codée des défauts ; READY seulement aux gates finales inchangées | A_REALISER |
| L6 | Exécuteur de groupes/étapes et reprise | Couches, ceinture unique, raccords et interruptions sans doublon | A_REALISER |
| L7 | Enfilage, fiches mesurées, banc matière et fitting | Vêtement complet admis sur cible principale ; appuis transitoires retirés | A_REALISER |
| L8 | Clips et colliders animés | Clips complets, contacts/métrique/raccords/liberté des pans puis revue | A_REALISER |
| L9 | Templates/variantes et cycle ComfyUI persistant | Cas réel sans double job, réconciliation d'incertitude, compatibilité | A_REALISER |
| L10 | Rendus, finition/UV/LOD, export et réimport | Scène animable réouverte, ressources/clips valides et revue réelle | A_REALISER |
| L11 | Qualification, documentation, package, publication et installation | Préversion finale exacte et runtime connecté vérifié | A_REALISER |

L0 précède les autres lots. L1/L2 ouvrent L4 puis L5 ; L6 consomme le placement
admis ; L7 précède L8. ComfyUI avance en parallèle après le socle/les entrées.
Rendus et bancs de coupons peuvent avancer sans prétendre qualifier le vêtement.
La livraison finale attend les critères techniques et revues prévus.

## Décisions techniques

- Corps : stature uniforme existante, pieds ancrés, mesures absentes non ciblées.
  Cage sourcée pour tours ; rapport largeur/profondeur conservé si seule la
  circonférence change. Contrôles de membres/épaules seulement avec repères
  fiables. Sommets/repères/rig dérivé restent cohérents.
- Optimisation corporelle : sections mesurées, Jacobien par différences finies,
  système amorti avec pivotage, recherche de pas bornée, arrêt réussite/budget/
  stagnation. Une cible n'est jamais choisie pour faire artificiellement rentrer
  le corps dans le patron.
- Placement : noyau rigide et relaxation distincts ; copie exploratoire non
  admise tant que contacts/métriques échouent. Source/topologie/pins/budgets
  protégés ; aucun seuil final relâché.
- Groupes : mapping groupes/composants/pièces/faces source après consolidation.
  Fermeture/détachable ne deviennent pas couture permanente. Couches internes
  figées et groupes conjoints explicites pour liaisons traversantes.
- Mouvement : collider évalué par frame/sous-frame, identité rig/poids/Action
  contrôlée. Couverture insuffisante = INCOMPLETE. Convergence seulement pendant
  détente terminale, jamais à la place de l'évaluation du clip entier.
- Image : passage conversationnel au générateur intégré conservé ; automate
  préparation, résultat exact, provenance et board autour de ce passage.
- Exports : profil Blender animation pour cette acceptation ; autres profils
  génériques testés par réimport, moteur seulement si destination/version réelles.

## Tests et preuves

Tests ciblés après chaque modification, intégration affectée puis suite complète
et contrats pour candidat intégré. Cas obligatoires : références périmées et
invalidation précise ; stature/cadre tourné/régions protégées/réouverture ;
compilation indépendante de l'ordre et doubles coutures refusées ; guides
complets et cas impossible ; ceinture unique/couches/détachables ; interruptions
avant/pendant/après mutation sans doublon ; matière à conditions fixes et budgets ;
collider animé traversant entre images et Action/poids changés ; Comfy interruption,
nœud absent et soumission incertaine ; fichiers/ressources/runtime incorrects.

Les essais Blender/Comfy lourds sont séquencés. Les fixtures génériques portent
sur deux bases ; une seule qualification complète de vêtement est exigée.

L'acceptation finale demande les 15 textiles + boucle, placement/enfilage admis,
essais et drapé réellement exécutés, fitting actuel, mouvements et scène réouverte.
Vues face/profil/dos/trois-quarts et vidéos : épaules/taille/ourlet/capuche, deux
pointes du dos, manches fines, manchettes externes, devant intérieur en retrait,
continuité autour ceinture. Une image ou un label PASS n'est pas une décision.
Les preuves de coupons, stature ou préparation gardent leur portée.

## Exécution, commits et livraison

Coordinateur + trois agents au maximum ; propriété exclusive des modules. Le
coordinateur possède interfaces, état canonique, admission et intégration.
Agents anatomie, textile et orchestration ; revue indépendante à chaque jalon
en libérant une place. Commits atomiques après tests pertinents. Les corrections
rejouent seulement les contrôles invalidés et conservent les tentatives.

Ultra est le niveau demandé pour les travaux complexes lorsqu'il est disponible
pour le modèle/client ; son activation ne remplace aucune preuve native.
Temps/reprises/refus/interventions sont mesurés, aucun gain n'est inventé.

PR de branche isolée actualisée sur candidat final. Prochaine version libre
`0.7.0-rc.N`, sans tag remplacé, une publication finale après qualification/revue.
Vérifier tag/commit/archive/empreintes/cache/runtime connecté après rechargement ;
confiance native hooks reste gérée par Codex.

## Décisions et découvertes

- 2026-10-03 : utilisateur approuve tout le programme, une cible principale et
  tests génériques deux bases, une seule préversion finale.
- 2026-10-03 : source initiale vérifiée propre sur `8dfeac77`. Réutiliser la branche
  existante, sans changement de source ou de scènes de production.
- 2026-10-03 : `studio_doctor` du chat observe maintenant 0.7.0-rc.2 et ses 25
  schémas. L'ancien défaut de connexion 0.6.9 reste historique ; cette nouvelle
  observation ne qualifie pas les hooks ni le fitting.

## Résultats et limites

Implémentation démarrée. Aucune nouvelle acceptation de vêtement ni publication
finale. Le défaut historique du haut du torse ne constitue pas une nouvelle
mesure sur la cible principale. La cible principale et l'acceptation anatomique
restent à enregistrer sur les variantes effectivement examinées.
