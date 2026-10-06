# Programme d'automatisation Atelier 3D

Plan approuvé par l'utilisateur le 3 octobre 2026. Base : branche
`codex/garment-automation-v1`, commit `8dfeac77c3b1bc3b11a4dbe6401eb2b1bb0a54ea`,
version 0.7.0-rc.2. Le programme est suivi ici pendant l'implémentation.

**État courant du 5 octobre :** le build local distinct
`0.7.0-rc.2.dev.2026100506` est installé par le gestionnaire natif de Codex ;
ses 635 fichiers correspondent au stage préparé. Le code intégré exporté au
commit `b378b60510a50a3b55943551238db1a659fa99ac` a passé 1 642 tests en
216,364 s, aucun SKIP, et 14 contrats sous Python 3.11. Les 78 tests ciblés
passent sous Python 3.11 et 3.13 ; le descripteur historique réel est encore
authentifié en lecture seule, SQLite inchangée. Le redémarrage a effectivement
chargé `dev.2026100505`, diagnostic PASS et pipeline admis. La restauration
autorisée a ensuite échoué avant ouverture du checkpoint sur une archive dont
le chemin fait 290 caractères. Le nouveau correctif adapte uniquement les
accès Windows aux archives et à leurs lecteurs, sans changer les identités
enregistrées. Après installation de 0506, `studio_doctor` pointe encore vers
le cache remplacé `dev.2026100505` : rechargement requis avant sa vérification
et une nouvelle restauration explicitement autorisée. La restauration native
reste non terminée. La compilation publique V4 conserve son fitting incomplet.
Les correctifs source `8e7a73d`, `af78094` et `6545a41` ajoutés ensuite passent
79 tests ciblés sous chacun des deux Python ; ils sont maintenant intégrés au
candidat validé et installé ci-dessus. Les 1 592 tests historiques gardent leur
candidat propre. L'index UV essayé reste expérimental, désactivé en production, après
un résultat réel défavorable ; aucun gain de performance n'est qualifié.
Le statut historique de la planche reste `RECORDED_RECHECK_REQUIRED` ; aucune
nouvelle revue de coupe n'est déduite ou créée par l'installation.

Les 14 entrées exactes du corps accepté sont vérifiées et disponibles dans ce
projet. Les opérations publiques `prepare`, puis `start_clean_construction`,
ont été exécutées après leurs autorisations distinctes. La copie témoin et la
scène vide de construction sont conservées sur G:, avec reçu natif
`COMPLETED` et fichier précédent inchangé. Après autorisation de
`introduce_body_target`, le run `run.74b32ba8748a452a93e1983fa1664357`
est terminé et réconcilié. Le corps accepté est présent, sans transformation
anatomique, avec collision de 0,3 cm et checkpoint enregistré. Sa portée reste
`EXACT_BODY_CONTEXT_ONLY`, sans Cloth ou fitting. La compilation actuelle
couvre les 15 textiles et la boucle. Les guides et le raccordement natif des
entrées ont été préparés ; le candidat manteau exécuté reste refusé, avec
10/15 textiles et la boucle absente. Les sections du torse épuisent actuellement
leur budget ; la capacité et la couverture ouvertes restent indéterminées.
Le placement admis, le premier drapé et le fitting mesuré restent à réaliser.
La préversion finale et l'acceptation du vêtement complet restent ouvertes.

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

**Contrainte utilisateur du 5 octobre :** chaque script de production doit
être générique pour les vêtements. Les identités, géométries, relations,
repères, cibles et budgets viennent des contrats structurés ; aucun cas propre
au manteau courant n'est encodé comme méthode de production. Une méthode dont
le domaine ne peut pas être universel doit déclarer ses conditions, justifier
sa limite et refuser les données incompatibles. Les diagnostics et travaux
déjà autorisés continuent. Voir [le contrat de généralité](garment-automation-generality.md).

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
| L2 | Mannequin préparé systématiquement et remesuré | Deux variantes 180 cm réouvrables, revue et cible principale choisie | VALIDE_SUR_DEUX_BASES |
| L3 | Cage anatomique et contrôles corporels bornés | Résidus mesurés, régions protégées, refus des cibles impossibles | VALIDE_POITRINE_TAILLE_HANCHES |
| L4 | Guides col, devant intérieur, capuche, empiècements et épaules | Couverture source complète, métrique et contacts contrôlés | GUIDES_PARTIELS_SUR_COMPOSITION_APPROUVEE |
| L5 | Corrections rigides puis relaxation contrainte séparée | Réduction codée des défauts ; READY seulement aux gates finales inchangées | PLACEMENT_REFUSE_RECUPERATIONS_EN_COURS |
| L6 | Exécuteur de groupes/étapes et reprise | Couches, ceinture unique, raccords et interruptions sans doublon | COUPONS_NATIFS_V12_EXECUTES_VETEMENT_A_REALISER |
| L7 | Enfilage, fiches mesurées, banc matière et fitting | Vêtement complet admis sur cible principale ; appuis transitoires retirés | BANC_EXECUTE_ENFILAGE_PHYSIQUE_ET_FITTING_A_REALISER |
| L8 | Clips et colliders animés | Clips complets, contacts/métrique/raccords/liberté des pans puis revue | SIX_CLIPS_CORPORELS_EXECUTES_VETEMENT_A_REALISER |
| L9 | Templates/variantes et cycle ComfyUI persistant | Cas réel sans double job, réconciliation d'incertitude, compatibilité | CYCLE_REEL_ET_RECONCILIATION_EXECUTES |
| L10 | Rendus, finition/UV/LOD, export et réimport | Scène animable réouverte, ressources/clips valides et revue réelle | RENDU_EXPORT_SYNTHETIQUES_EXECUTES_VETEMENT_A_REALISER |
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

- 2026-10-04 : la borne nominale source des manches est 29 à 36 cm ; les
  sections mesurées au milieu des bras de la cible sont 37,439902 et
  37,476989 cm. Le rapport `limb-capacity-bounds-proposal-v2.json` conserve
  ce signal, l'hypothèse sans étirement et la correspondance portée non
  qualifiée. Les valeurs d'aisance restent à définir et les patrons inchangés.
- 2026-10-04 : correction des guides de manchettes par les bords source
  `wrist-free` et `sleeve-join`. Le bord libre était placé au-delà du poignet.
  La nouvelle orientation le place au poignet et développe la manchette vers
  le coude. Le contrôle natif du vêtement après cette correction reste requis.
- 2026-10-04 : l'essai isolé d'enfilage v2 révèle un retard d'une image de la
  prise pleinement contrainte à l'image 3 (0,0050006 cm, seuil 0,001 cm).
  L'Action native de cibles préparée avant Cloth dans v3 ne corrige pas ce
  retard. Les deux échecs sont conservés ; diagnostic de l'entrée et du cache
  en cours, aucune qualification d'enfilage accordée.
- 2026-10-04 : l'utilisateur signale un manteau trop près du corps et demande une
  classification du vêtement ainsi qu'une aisance plus explicite. Choix retenu :
  « Manteau ample : volume visible et liberté de mouvement ». Décision canonique
  `fit-silhouette.garment.coat`, fichier `coat-silhouette-decision-v1.json` du
  laboratoire principal. Cette décision ne définit pas les valeurs numériques
  et n'approuve ni changement du corps ni variante de patrons.
- 2026-10-04 : ajout du contrat `garment-fit` et de la comparaison source par
  composant/couche/section corporelle. `studio_compile_production_dossier` expose
  séparément compilation et précontrôle d'aisance. Catégorie sans seuil automatique,
  mouvement/couches/style explicites ; les tours ouverts exigent une mesure
  spatiale. La fiche principale v2 et le rapport compilé v1 restent
  `FIT_PREFLIGHT_INCOMPLETE` : huit chemins homologues et le recouvrement manquent.
  Les 84 chemins historiques de bords source ne constituent pas ces huit mesures.
- 2026-10-03 : utilisateur approuve tout le programme, une cible principale et
  tests génériques deux bases, une seule préversion finale.
- 2026-10-03 : source initiale vérifiée propre sur `8dfeac77`. Réutiliser la branche
  existante, sans changement de source ou de scènes de production.
- 2026-10-03 : `studio_doctor` du chat observe maintenant 0.7.0-rc.2 et ses 25
  schémas. L'ancien défaut de connexion 0.6.9 reste historique ; cette nouvelle
  observation ne qualifie pas les hooks ni le fitting.
- 2026-10-03 : choix humain de la cible principale `body.realistic-male`,
  stature 180 cm. Tours mesurés poitrine 110,15, taille 85,29, hanches 103,04 cm.
  La revue anatomique sur pixels a été acceptée le 4 octobre. Les 108 cm de poitrine vêtue
  du dossier ne sont pas une cible corporelle : compatibilité à examiner sur
  les chemins mesurés des patrons, sans réduction opportuniste du corps.
- Première unité native : `program-native-body-target-v1/receipt.json`, deux
  variantes à 180 cm exportées et réouvertes dans Blender 5.2.2. Portée géométrie
  uniquement ; les ajouts ultérieurs tête/journal nécessitent un nouvel essai.
- 2026-10-04 : revue humaine des quatre fichiers issus de
  `program-native-review-v1/receipt.json`, base masculine 180 cm. Réponse exacte :
  « Accepter ces proportions pour la cible ». Cette acceptation anatomique ne
  vaut pas acceptation du rig, de Cloth ou du fitting.
- Préparation/journal/tête natifs : `program-native-body-target-v2/receipt.json`
  PASS sur deux bases. Réouverture exacte et invariance de la scène source.
- Essais du mouvement v1/v2/v3/v4 FAIL conservés. Causes : contexte de sélection,
  édition du rig hors objet actif, diagonales de quads recalculées sous
  déformation, puis mapping de nouvelle opération manquant. Corrections ciblées
  effectuées ; pas de qualification transférée depuis ces campagnes.
- Revue indépendante du journal : deux fenêtres de double mutation/orphelin
  corrigées par début natif enregistré, événement canonique de résultat,
  réconciliation sans replay et conservation du checkpoint. Les tests couvrent
  rollback après fichier et interruption entre commit/finalisation.
- Installation actuelle confirmée par le gestionnaire natif : rc.2 activée,
  source locale sur G:. Le MCP connecté répond également rc.2. La source de
  développement reste séparée de cette installation jusqu'à livraison finale.
- 26 tests de jobs/variantes ComfyUI passent ; 45 tests ciblés de protocole,
  corps, journal et variantes passent. Ce sont des contrôles portables ; le
  cycle fournisseur réel et le vêtement complet ne sont pas qualifiés.

## Résultats et limites

- Corps paramétriques : `program-native-body-controls-v1` FAIL conservé pour
  rapport largeur/profondeur de hanche. Cause : sections traversant des sommets
  protégés, qui brisent une similitude radiale. Correction par contraintes
  remesurées aux plans source, sans modifier le seuil de validation. Campagne
  `program-native-body-controls-v2/receipt.json` PASS sur deux bases, uniquement
  poitrine/taille/hanches dans le domaine qualifié. La cible principale reste
  inchangée ; épaules et longueurs de membres non supportées sans contrôles source.
- Mouvement : `program-native-body-motion-v7/receipt.json` PASS pour les six
  clips corporels complets, 49 observations par clip et réouverture native.
  Aucun vêtement animé ni revue du rig humain déduit de cette preuve.
- Laboratoire principal : `program-production-main-v1`, même asset/dossier et
  mêmes quatre packages. Les six décisions humaines de références/découpage/routes
  sont préservées avec leurs fichiers exacts et leur provenance. Aucune base
  SQLite, scène candidate, qualification physique ou preuve d'exécution reprise.
  Cible masculine et quatre vues anatomiques acceptées enregistrées séparément.
- Compilation principale : 15 textiles + boucle, 32 relations source conservées,
  15 guides préparés. Sections cutanées supplémentaires restent des preuves
  distinctes des mensurations approuvées. Les contacts et le placement final
  ne sont pas encore admis.
- Journal : 28 tests ciblés de reprise passent, incluant crash brutal avant ou
  après le hook de checkpoint. Le début natif lie run/tentative/opération/arguments
  à la frontière exacte. Une restauration enregistrée reste exigée avant replay.
- ComfyUI : premier essai conserve un run invalidé par changement de code et
  son job réel. Le job a été réconcilié et sa sortie récupérée sans second envoi ;
  cette récupération fournisseur ne valide pas le run. Le cycle suivant est
  exécuté depuis une copie figée. Modèle absent refusé avant calcul.

- Cycle réel ComfyUI v2 : `program-native-comfy-v2/receipt.json`, une seule
  soumission réelle et une sortie vérifiée après injection d'une réponse perdue.
  Les preuves fournisseur authentifient la réconciliation ; aucun nouvel envoi
  automatique. Portée pipeline, sans acceptation des images produites.
- Reconstruction principale de la boucle : job
  `fe404758-57a4-45a1-9c76-7f6aa2eb5cd5`, run
  `run.d7845db6551c456aa3d3f68f8aaf3565` terminé, GLB de 993628 octets.
  SHA `292977e959d2c9cc3232da6b3021217305c6c5ab336e3623e4ed83da0b052ccc`.
  Inspection native, orientation, dimensions, ancres et revue restent séparées.
- Suite portable intégrée : copie figée `program-candidate-07`, 559 tests PASS,
  76,250 s. Les ajouts suivants nécessitent leurs tests ciblés puis la suite
  finale ; cette suite ne qualifie pas le vêtement.
- Reprise textile v4 : une unité terminée et enregistrée peut laisser le run
  RUNNING jusqu'à l'appel suivant du planificateur. Le fixture demande cet appel
  terminal. Le code n'invente pas de seconde exécution pour changer ce statut.
- Textile v5 : seuil de contact .05 cm refusé par Blender 5.2.2 avant Cloth.
  Probe natif `program-native-textile-parameters-v1/result.json` : minimum RNA
  .1 cm pour distance_min et self_distance_min ; .05 cm est clampé, .3 cm est
  réellement appliqué. Fixture corrigé à .3 cm, gates de contrôle conservées.
  Textile v6 atteint le groupe interne puis refuse le collider figé du groupe
  externe ; tentative conservée, identité/politique à corriger avant reprise.
- Export/finition : v1 échec sur mutation des listes par le loader natif ; v2
  échec de contexte UV temporaire ; v3 échec du sampler export exigeant des
  régions anatomiques sur les objets rigides. Corrections ciblées : listes
  isolées, contexte d'édition exact et sampler géométrique générique. Aucune
  qualification d'export transférée depuis ces échecs. Actions de shape keys
  désormais prises en charge comme source d'animation explicitement déclarée.
- Preuves d'export : le vérificateur exige le callback natif canonique et
  recalcule la comparaison géométrique mesurée. Un manifeste fourni par le
  client avec reimport=EXECUTED ne crée aucune preuve de réouverture.
- Introduction du corps : `program-native-main-body-context-v1/receipt.json`
  conserve la cible masculine approuvée dans la copie de travail du laboratoire.
  Les deux bases sont réouvertes dans `program-native-body-context-v1/receipt.json` ;
  réutilisation exacte et refus d'un collider modifié sont contrôlés.
- Placement L5 : `program-native-placement-correction-v2` réduit le défaut du
  coupon en sept itérations. Les supports protégés restent fixes et le cas
  impossible s'arrête sans admission. Portée coupon statique uniquement.
- Textile L6 : `program-native-textile-v8` termine les groupes ordonnés et la
  bande unique de ceinture. Le cas couplé est refusé faute de réponse Cloth
  mesurée ; ses témoins causaux initiaux sont refusés avant simulation par les
  contacts. La cause physique reste à établir, sans modifier les gates.
- Compilation principale : `program-native-main-template-diagnostic-v2/result.json`
  confirme l'égalité exacte des templates sous Python 3.11 et Blender/Python 3.13.
  La précision déclarée concerne seulement les valeurs calculées des seeds
  rigides et de l'audit ; les données source et critères restent exacts.
  L'essai `program-native-main-preparation-v3` conserve une erreur de création
  du répertoire avant mutation. La correction du binder prépare la reprise.
- Mouvement textile L8 : `program-native-garment-motion-v1/receipt.json` exécute
  Cloth sur les deux bases, réouvre les animations observées et détecte un
  obstacle traversant entre deux images. Portée TEST_ONLY ; les couches externes
  font l'objet d'une campagne distincte.
- Finition/export L10 : `program-native-asset-export-v4/receipt.json` réouvre le
  candidat synthétique avec UV, LOD, ressources et Action de shape keys. Cette
  preuve ne qualifie aucune livraison du vêtement principal.
- Boucle principale : `program-native-main-buckle-calibration-v1/receipt.json`
  mesure 7,19999969 × 6,80000037 × 0,70000002 cm après calibration codée sur une
  copie depuis les dimensions du dossier approuvé. Topologie source conservée,
  corps et patrons inchangés. Qualification DIMENSIONS_ONLY ; orientation,
  ancres, placement, animation et revue artistique restent à établir.

- Préparation principale v6, source figée 20 : les 15 pièces sont générées et
  rendues, mais les trois composants sont `NEEDS_CORRECTION`. Réserve de ceinture
  insuffisante (.1433 cm au lieu de .3), manteau pénétrant le haut du dos jusqu'à
  7.5087 cm avec déformation métrique, empiècement supérieur pénétrant jusqu'à
  1.8300 cm et triangles dérivés trop fins. Aucun Cloth principal exécuté.
  Diagnostics distinguent les guides déformés du manteau et la discrétisation
  dérivée capuche/empiècements ; aucun défaut de coupe n'est encore prouvé.
- Préparation principale v7, source figée24 : 494,20 s. Triangles fins de la
  capuche et des empiècements corrigés dans la triangulation native fraîche :
  angle source minimal 19,04°, métrique matière conservée. Les contacts restent
  refusés (−1,6929 cm au pire) et le solveur atteint son budget. Le manteau garde
  une compression minimale 0,5200 et un étirement maximal 1,3394 ; pénétration
  jusqu'à 7,2009 cm au devant gauche haut. Ceinture inchangée à .1433 cm de
  réserve. Les trois composants restent `NEEDS_CORRECTION`, sans Cloth.
  Les vues natives face/dos/trois-quarts ont été inspectées ; les épaules
  exposées et la capuche en panneaux ouverts restent des défauts de préparation.
- Suite portable sur la source figée24 : 669 tests passés en 86,33 s. Cette
  observation ne qualifie ni les modifications suivantes ni le vêtement.
- Mesures corporelles supplémentaires v2 : données natives déjà capturées,
  relues sans nouveau Blender ni changement du corps ou de SQLite. Haut du bras
  au milieu 37,44/37,48 cm ; poignet 17,40/17,44 cm. Sections d'épaule laissées
  non qualifiées faute de contour fermé dans le domaine source. Les enveloppes
  complètes de main projetées sont conservatrices, distinctes d'un tour
  anatomique et d'un passage physique. La campagne v1 conserve un défaut
  de sérialisation tuple/liste des plans ; v2 corrige la création des listes et
  réouvre le supplément avec comparaison stricte à une remesure canonique.
- Textile v11, source figée 22 : 33.109 s, groupes ordonnés, bande unique et groupe
  couplé exécutés. Montage avec réponse Cloth mesurée, consolidation de neuf
  unions, détente/drapé avec continuité permanente vérifiée. Mapping composant
  complet vérifié depuis les vrais reçus des groupes, contre-exemples refusés.
  La campagne v10 conserve un échec de capture de classe d'exception dans le
  driver du contre-exemple ; le helper refusait correctement le groupe manquant.
  Portée coupons mécaniques synthétiques, aucun fitting principal déduit.
- Banc matière v3 : six essais initiaux admis, un coupon cousu amortissement1
  converge réellement à 24 images ; quatre essais restent incomplets au budget,
  un essai de contact amortissement20 échoue en métrique. Les réglages de matière
  du vêtement principal ne sont pas qualifiés par ce comparatif.
- Mouvement textile v3 : deux bases, cinq images de coupons, couches observées
  et réouverture native, budget insuffisant et obstacle mobile contrôlés.
  Portée `TEST_ONLY`, distincte des mouvements du vêtement complet.
- Composition/export v3, source figée23 : 77,72 s, transport natif synchronisé corps et
  textile réévalué et réimporté. Les trois clips de transport réutilisent un seul
  essai physique de coupon ; ils ne représentent pas trois essais de mouvement.
- Vidéo v2 : cinq PNG réels puis `INCOMPLETE`, encodeur interrogé dans le domaine
  image. Blender5.2 requiert le domaine vidéo avant sélection FFmpeg ; correction
  préparée. La campagne vidéo v3, source figée23, exécute ensuite les deux modes
  de rendu : 30 PNG et six vidéos H264 relues, 70,57 s. Les images entières des
  trois clips de transport sont couvertes ; aucune revue artistique humaine
  n'est déduite de ce contrôle de média. Attachement rigide v1 conserve
  un crash natif pendant la sauvegarde de la scène du cube synthétique ; fixture
  corrigé pour écrire les objets source. La campagne v2, source figée23, passe
  en 7,29 s avec animation des ancres UV et réimportation du cube synthétique.
  L'attachement de la boucle principale reste non exécuté.

### Observations du 4 octobre 2026

- Intention humaine retenue : manteau ample, volume visible et liberté de
  mouvement. La classification `coat / relaxed / open_front / outer` est liée à
  la décision conservée. Les valeurs numériques d'aisance et les variantes de
  patrons restent à examiner ; le corps masculin accepté à 180 cm est conservé.
- Préparation principale v8, source figée 29 : 805,51 s. La récupération métrique
  du manteau exécute 47 itérations en 304,89 s, avec déplacement maximal 5,74 cm
  depuis le guide source dans le budget partagé 8 cm. Les déformations principales
  passent à [.92738,1.14142] ; la borne supérieure inchangée 1.1 reste dépassée.
  La recherche de contacts suivante n'est pas exécutée. Le manteau conserve 6823
  contacts et une pénétration maximale 8,1774 cm. Face/dos inspectés : haut du
  torse et épaules traversés. La ceinture reste à .1433 cm de réserve pour .3 cm
  demandé ; capuche/empiècements à −1,6929 cm. Aucun Cloth ni fitting exécuté.
- Admission physique revue indépendamment : le contexte d'aisance couvre les
  composants réellement mesurés et les packages réellement exécutés. Les groupes,
  essais existants, gel continu et scripts de simulation appliquent ces contrôles
  avant effets. Les expériences TEST_ONLY ne deviennent pas des qualifications
  de production. L'essai natif dédié `program-native-physics-admission-v1`
  (source figée 32) passe en 41,96 s : corps principal exact reconnu, changement
  de sommet, de région cutanée, de cache et reclassement en support refusés.
  Portée identité/admission uniquement, sans simulation ni fitting.
- Enfilage synthétique v3 : erreur de soutien .0050006008 cm à l'image 3 pour
  .001 cm permis. Un diagnostic natif de trois branches source 30 en 22,43 s
  confirme des entrées d'animation correctes mais un cache Cloth périmé et figé
  après l'image 2. Le corps, les sources et SQLite sont préservés. La correction
  des poids animés est séparée du fitting du vêtement.
- Enfilage synthétique v4, source 31 : refus avant la première observation en
  46,29 s, car Action/Key/slot divergent du driver préparé. Cette tentative
  conserve son reçu ; aucune confirmation de la correction physique n'en découle.

- Enfilage synthétique v5, source figée 32 : 97,12 s, cinq images réellement
  exécutées et réouverture native. Poids évalués de prise égaux à 1 aux images
  1–3, puis 0 aux images 4–5 ; erreurs sous le seuil inchangé .001 cm et caches
  non périmés. Actions séparées pour positions et masques, sans modification
  du maillage à chaque image. Budget deux images classé INCOMPLETE, instructions
  manquantes classées NEEDS_DATA. Portée TEST_ONLY_DRESSING_SOURCE_GRIP : la bande
  reste éloignée du corps ; aucun passage de vêtement principal démontré.
- Suite portable source figée 31 : 758 tests PASS en 93,78 s. Les modifications
  ultérieures et les essais natifs gardent leurs reçus distincts ; ces tests ne
  constituent aucune acceptation du manteau.
- Mesures diagnostiques : le parcours natif strict d'admission reste limité aux
  résultats COMPLETED et aux fichiers exacts. Un parcours OBSERVATION_ONLY peut
  relire un artefact intact d'une tentative RETURNED refusée ou incomplète. Les
  projections de travail périmées autorisées sont tracées séparément ; elles
  ne deviennent pas des preuves de placement, de physique ou de fitting.
- Proposition d'aisance ample préparée : poitrine +20 cm, taille +10 cm avant
  serrage de ceinture, hanches +18 cm, haut des bras +8 cm, poignets +7 cm et cou
  +6 cm, avec haut léger provisoire. Fiche `coat-ease-review-v2.md` et données
  `coat-ease-target-proposal-v1.json` dans la préparation principale. Valeurs
  proposées seulement ; aucun patron gradé ni chiffre accepté implicitement.

- Textile v12, source figée 32 : 35,16 s, groupes ordonnés, bande unique et
  groupe couplé exécutés. Les trois entrées advance/bundle/transition refusent
  chaque contexte GARMENT_CANDIDATE dépourvu de fiche d'aisance revue avant
  mutation native. Douze/six/six étapes conservent TEST_ONLY et les vérifications
  de continuité. Aucune qualification transférée au vêtement principal.
- Découverte de reprise documentaire : les anciens reçus de préparation v8
  référencent aussi les projections mutables de travail. La sélection explicite
  d'un artefact intact permet seulement le diagnostic, avec ces projections
  périmées tracées. Les futurs reçus de production devront conserver des
  projections archivées ou une séparation explicite des artefacts et vues
  courantes ; la qualification intégrale n'est pas rétablie par le diagnostic.

- Compilation publique de mesures v1 : 34,17 s, dossier couvrant 15 textiles
  et une boucle, six chemins proposés et deux manches encore refusées.
  Les points de bord UV source sont réconciliés avec leur arrondi binary32 exact
  sans modifier le maillage v8. Les courbes de manche restent non homologues :
  écart de partenaire de couture .08851/.08824 cm et extrémités de guide séparées
  de 1.1191/1.1198 cm. Ce diagnostic vise les guides, pas les coutures approuvées.
- Précision source UV native v3, source figée 35 : 3,80 s. Ancres exactes, faces,
  points intérieurs et orientation conservés pour les deux sens de contour.
  Les ancres réellement confondues par binary32 sont refusées. Les essais v1/v2
  conservent deux assertions de fixture corrigées, sans verdict transféré.
  Portée SOURCE_UV_ANCHORS_ONLY, aucune correction physique d'épaule déduite.
- Préparation d'enfilage capuche/empiècements : six méthodes et 1086 contrôles
  sourcés, avec unités permanente et détachable séparées. Configurations ouvertes
  explicites exigées ; pas de couture créée. Modes et trajectoires encore à
  déclarer, statut NEEDS_DATA, aucun passage principal exécuté.
- Archivage des projections de run : futurs reçus conservent les deux projections
  de travail reconnues dans des copies immuables liées à leur tentative et SHA.
  Les vues courantes restent séparées, même après modification ou disparition.
  Le résultat, les statuts et qualifications restent identiques. Les anciens
  reçus gardent leurs règles ; aucun orphelin sans enregistrement canonique ne
  crée de preuve. Revue indépendante et contrôles portables ciblés exécutés ;
  la campagne textile v13 contrôle le callback et sa réconciliation native.
  L'archivage de projections modifiées ou supprimées reste vérifié par les tests
  portables, sans prétendre qu'une telle mutation a eu lieu dans ce cas natif.

- Intégration source figée 36 : 461 fichiers, empreinte
  `61e4c56799ce8f721fc95c5f840e7d7a611783ffdf84eb1136fab8f7729ecc02`.
  795 tests portables PASS en 105,30 s ; 14 contrats de templates/fixtures et
  sept entrées actuelles validés avec PowerShell Test-Json. Groupes natifs v13
  PASS en 38,64 s : ordonnés, bande unique, couplés, refus de contexte de
  production manquant et réconciliation enregistrée sans nouvelle mutation.
  Ces cas synthétiques gardent TEST_ONLY et ne qualifient pas MAIN.
- Compilation publique MAIN v2 sur cette source : 34,16 s, six chemins proposés,
  deux manches refusées, FIT_PREFLIGHT_INCOMPLETE. Rapport
  `program-main-fit-public-measurements-v2/report.json`, SHA
  `3eb0e7c06cc676de4fbbbc073b3cc28064b15db48bf276fa42e6f308d63e7c05`.
  Le supplément corporel v7 et la fiche proposée v8 restent liés aux mêmes corps
  et patrons ; ni cibles numériques acceptées ni fitting exécuté.
- Politique de guides v2 : toutes les dépendances du générateur et les octets
  exacts de la politique sont contrôlés. Reconstruction complète non arrondie
  identique aux guides v8, zéro différence. Cette reproductibilité conserve les
  défauts observés ; elle ne corrige pas les épaules par elle-même.

- Candidat destiné à Git : distribution normalisée selon les attributs LF du
  dépôt, sans changement de logique. Les empreintes du code invalident les
  politiques et suppléments antérieurs concernés ; ils sont conservés.
  Source figée 37, identité
  `2bee3c9b90f19fe3c64dd71c01bbb590d861d6d6151eaf6a64947bb64d93ec3a` :
  795 tests PASS en 105,57 s ; groupes natifs v14 PASS en 40,09 s. La politique
  v3 restitue encore les guides v8 à l'identique. Compilation publique v3 en
  33,94 s, supplément corporel v8 et fiche proposée v9 : six chemins, deux
  manches refusées, fitting incomplet. Rapport SHA
  `fe623962e8533f39b1d517a506e3d1af84168a1c25ac4a03d82e4159eb00789e`.
  Le code intégré est enregistré dans le commit `12e3dc2` ; la documentation
  et les preuves de cette unité forment un commit séparé.

### Poursuite après accord numérique du 4 octobre 2026

La réponse « ok continue avec ca » accepte les valeurs de la fiche d’aisance
proposée et le haut léger sous le manteau. La décision canonique
`ease-design.garment.coat` référence la fiche, le dossier et le corps exacts.
Le mannequin reste inchangé. Cette décision de conception n’accorde pas la
revue des nouveaux patrons, l’homologie des chemins, l’admission physique d’une
fiche complète ni le fitting. La gate `fit-intent.garment.coat` reste absente.

Les guides de manches utilisent maintenant les intervalles matériels source
et leurs partenaires de couture, dans le contrat de cage barycentrique existant.
Le cylindre précédent supposait une largeur constante de 36 cm, alors que la
largeur source varie de 29 à 36 cm. Sur les 1 494 triangles UV natifs intacts de
chaque manche, les chemins obliques corrigés se ferment à moins de 10⁻⁸ cm.
Leur longueur de matière reste 35,04424 / 35,04695 cm, inférieure aux cibles
45,43990 / 45,47699 cm. La correction du guide ne crée pas cette matière.

Compilation publique MAIN v4 : 32,39 s, huit chemins proposés, dont les deux
manches auparavant refusées. SQLite, corps et packages sont préservés. Le
rapport reste `FIT_PREFLIGHT_INCOMPLETE` : les chemins sont des propositions,
la couverture du devant ouvert et la fiche complète restent à examiner.
Les pénétrations du haut du torse observées dans la préparation v8 restent
non corrigées par une nouvelle exécution native.

Le [suivi de cette unité](automation-ease-followup-20261004.md) conserve les
références exactes, la proposition de variante et la portée des contrôles.

Les cinq raccords internes du torse utilisent maintenant une cage source
commune ; les bords sont synchronisés par la moyenne des guides mesurés,
sans changement des patrons ou du corps. Les raccords externes, la métrique,
les contacts et la couverture du devant restent à contrôler. Une divergence
de structure du rapport après JSON a été corrigée avec une régression dédiée.
La proposition densifiée de manches conserve les vrais points matériels des
crans ; sa gradation nominale ne qualifie pas leur homologie anatomique.

Source figée 41 : 857 tests portables PASS en 129,21 s, 29 contrats JSON PASS,
groupes textiles natifs v15 PASS en 42,34 s. La préparation portable couvre
15 pièces et huit cages. La compilation MAIN v6 conserve cinq propositions
et refuse trois chemins du torse sur les anciennes coordonnées UV binary32.
Trois points sont proches d'une frontière d'arrondi : les paramètres source
de leurs coutures enregistrées permettent une reconstruction stricte, à
intégrer et vérifier séparément. Aucun seuil n'est élargi.

Le helper de témoins de couture est intégré et revu : paramètres orientés,
bords source, périmètre et arrondi natif exacts, sans recherche par proximité.
Le dernier cas inverse reproduit l'ordre de calcul du préparateur officiel.
Compilation MAIN v8 : sept propositions en 129,485 s ; poitrine encore refusée
sur un segment de l'ancien maillage qui ne conserve pas le vrai bord. Les
sources et SQLite restent inchangés pendant cette compilation.

L'utilisateur accepte les deux patrons de manches de la variante densifiée v2,
dans une décision liée à leur planche et package exacts. Les packages de
production et anciennes gates restent conservés ; physique et fiche complète
ne sont pas approuvées par cette décision. La prochaine unité de code couple
les attaches du devant intérieur et du col depuis les vrais liens source,
puis remesure avant de proposer les choix de couverture manquants.

Aucune nouvelle acceptation du vêtement ni publication finale. Construction,
enfilage physique, drapé, fitting complet, mouvements du vêtement et revue
artistique finale restent à exécuter sur le candidat exact.

### Couplage du devant intérieur et du col, et conservation des coins

Les six guides du manteau sont couplés par les 13 relations source internes ;
les quatre raccords externes des manches restent à traiter. La politique v8
déclare la sélection, la recette exacte et les budgets. Les corps et packages
de production restent inchangés. L'écart commun aux contrôles est nul, mais
la correction maximale atteint 10,52 cm : les contrôles métriques et de contact
demeurent requis, sans admission du placement ou de la couverture.

Le refus de poitrine a été localisé à un coin du dos omis sous l'ancienne borne
d'approximation de contour de 0,05 cm. La préparation régulière protège maintenant
tous les changements de direction exacts et propage leurs fractions aux
partenaires de couture. Un conflit de clé, de budget ou de qualité reste un
refus. L'ancien maillage reste intact et ne reçoit aucune mesure corrigée.

Source figée 45 : 900 tests portables PASS en 114,496 s, lancement 115,719 s.
Revue indépendante de 49 tests PASS. Cage source native v3 PASS en 6,219 s,
avec stockage et réouverture de six cages synthétiques/13 relations ; contour
source natif v1 PASS en 4,718 s, coin exact conservé dans la triangulation,
qualité et réouverture vérifiées. Portée `TEST_ONLY`, aucun Cloth principal.
Le schéma de la nouvelle politique v8 passe aussi PowerShell Test-Json.

Les nouvelles propositions sont conservées dans le suivi d'aisance. La revue
des deux manches reste acquise ; les autres décisions et qualifications
restent distinctes. La prochaine unité contrôle la métrique de la proposition
couplée et prépare sa correction bornée, puis la nouvelle préparation native.

La récupération commune est intégrée dans `d024819` : source 47, 922 tests
portables PASS et essai Blender statique à deux panneaux PASS avec réouverture.
Les appuis impossibles sont refusés avant optimisation. Le reçu
[métrique et cohortes](automation-metric-cohort-evidence-20261004.json) conserve
la portée logicielle et synthétique de ces résultats. L5 reste incomplet sur MAIN.
La prochaine correction traite la phase périodique du col et distingue repères
UV de placement et vrais appuis 3D dans la politique de récupération commune.

Cette correction est intégrée dans `fa08ffe` et `0c744c1` : source figée 48,
939 tests portables PASS, revue indépendante de 88 tests et 12 cas de contrat
par chacun des deux validateurs. Le cas natif statique v4 passe avec un seul
panneau ancré dans une composante cousue, puis sauvegarde et réouverture.
Le [reçu de phase et d'ancrage](automation-metric-anchor-evidence-20261004.json)
conserve les identités et la portée logicielle de cette unité.

MAIN v9 conserve les 13 raccords internes et passe les quatre bornes nécessaires
de longueur aux épaules. La récupération auxiliaire est cependant refusée avant
résultat : la triangulation source en éventail possède des segments et triangles
trop fins. Ce refus ne démontre pas une impossibilité des patrons ou du maillage
régulier. Une préparation native actuelle et ses contacts restent requis.

Le runtime installé `0.7.0-rc.2` lie le dispatcher à sa propre racine et ne charge
pas ces nouveaux modules. Les cas de développement isolés sont supportés,
sans acceptation produit transférable. Aucun contournement de hook ou changement
de runtime MAIN n'est effectué. Préparer le candidat et le package concret avant
de résoudre l'ordre d'installation locale et de qualification principale.

L'unité suivante est intégrée dans `d26268c`, `6919075` et `b6c7c1b` : arrêt
sur défaut UV immuable, composition pure des deux manches revues et
conditionnement de chaque candidat CDT avant comparaison. Source50 : 967
tests portables PASS en 111,096 s. La seule fixture native modifiée après cette
suite est exécutée séparément sur source51 : qualité, ancres et réouverture
contrôlées, ancien échec conservé. Le [reçu](automation-source-conditioning-evidence-20261004.json)
lie les octets aux contrôles réellement exécutés.

Le diagnostic source50 des six pièces indépendantes portait le minimum source
du col à 15,438170034° ; la déformation 3D restait hors limites après une
itération acceptée et un arrêt au budget temps. Son build complet était encore
refusé sur les anciennes manches. Cette preuve historique ne qualifie pas le
nouveau maillage complet source53 décrit ci-dessous.

### Crans matériels et admission canonique — source53

Les commits `4528424` et `b0873264` traitent le conflit d'échantillons et le
consommateur canonique de la variante. Un cran matériel devient une référence
à un sommet existant ou à un segment interpolé ; il n'impose plus une particule
physique supplémentaire. Les vrais coins source restent exacts et prioritaires.
La revue indépendante restitue les deux packages réels sans micro-arête sous
0,001 cm, avec 249 coins originaux et 253 coins dans la composition acceptée.

L'import public authentifie la décision humaine existante des deux manches,
la planche, les packages et toute la lignée de génération et d'approbation.
Un nouveau candidat canonique contient les 15 textiles et la boucle, au stade
RECONSTRUCTING. Seuls les deux patrons de manches acceptés changent ; dix
lignes incidentes non revues sont exclues. L'admission porte sur les entrées
de reconstruction, sans admission du placement, du fitting ou de permission
Blender. MAIN, ses bindings originaux et ses décisions restent conservés.

Source53 : 497 fichiers, identité
`acf950165513b1a2b29a7d99295de13b907d4020b7ec6785493968411d58353a` ;
1 012 tests portables PASS en 206,460 s, lancement 207,656 s. La CI du commit
`b08732641a342b8314ab765485cdcff013a5fb01`, run `37234999162`, passe tests et
build sous Windows/Python 3.11 et Linux/Python 3.13 ; contrats Windows PASS,
contrats Linux SKIP explicite. Cette portée reste logicielle.

Le diagnostic natif source53 construit les dix pièces originales en 39,525 s
et les dix pièces avec les deux manches acceptées en 38,905 s. Les payloads
sont produits, mais six pièces signalent NEEDS_CORRECTION sous le seuil régulier
de 15°. Le contrôle global de la recette exige seulement 2° ; sa réussite ne
remplace pas le contrôle régulier. Le sous-ensemble conserve exactement les
faces, coordonnées et UV du maillage complet. Son minimum source de 4,483886989°
sur le devant gauche entraîne METRIC_RECOVERY_IMMUTABLE_SOURCE_MESH_QUALITY,
sans itération ni démarrage de la correction des contacts. Le lancement dure
130,984 s, dont 121,679 s dans le diagnostic ; corps, sources et MAIN sont
préservés. Ce refus concerne des triangles dérivés réels, sans conclure que les
patrons sont impossibles ou modifier le seuil de 15°.

Le temps de l'import initial et les octets des bases parentes avant cet import
n'ont pas été enregistrés par le script initial. La réconciliation ultérieure
en lecture seule dure
7,516 s et conserve la base candidate. La revue préalable au diagnostic vérifie
ensuite trois bases réelles en lecture seule, sans changement de leurs octets.
Ces deux observations ne reconstituent pas une preuve initiale manquante.

Le [reçu de cette unité](automation-reviewed-pattern-evidence-20261004.json)
lie les preuves exactes et conserve leur portée. Le refus métrique anticipé
`336cdb6` est revu avec 68 tests ciblés ; il ne peut qu'accélérer un refus certain,
et le validateur final complet reste obligatoire. La proposition CDT autour
des courts segments protégés est revue avec 49 tests portables et enregistrée
dans `9febfb3`. Les essais intégrés de ces unités postérieures à source53 sont
identifiés séparément ci-dessous. Les présents ajouts documentaires suivent les
captures source53 et source54 ; ils n'étendent pas leurs résultats exécutés.

### Intégration suivante — source54

Source54 contient 501 fichiers, identité
`fe517779f1f19fecf91eca55297c2a2d47ff5c908f3ab1b7e9ff10e1870d23b0`.
La suite portable intégrée passe 1 040 tests en 177,628 s, lancement 178,719 s,
avec la copie figée inchangée. Elle inclut le refus anticipé et la proposition
locale CDT ; cette dernière conserve les coins et les mêmes budgets et critères.

La CI du commit `9febfb3a606d39d840140918ae8c1b62b3470312`, run
`37236866063`, passe tests et build sous Windows/Python 3.11 et Linux/Python
3.13 ; contrats Windows PASS et Linux SKIP. Cette preuve reste logicielle.

Le coupon natif de conditionnement v3 se sauvegarde et se rouvre exactement,
avec ancres source conservées. Carré et bande atteignent leurs cibles : angles
natifs minimums 23,793971234° et 15,874234372°. L'angle aigu est correctement
refusé. Le calcul dure 0,294 s, lancement 4,313 s. Portée SYNTHETIC/TEST_ONLY,
qualification NONE : aucun PASS transféré au maillage du manteau.

Le diagnostic réel source54 v4 dure 118,672 s, lancement 127,688 s. Les dix
pièces originales produisent un payload de 15 515 sommets et 28 794 triangles.
La variante des dix pièces est REFUSED dès le contrôle global de recette à 2° :
son minimum d'angle vaut 1,490237725°. Son payload refusé est conservé et n'est
pas utilisé. Sur le sous-ensemble original de six pièces, la récupération reste
arrêtée à zéro itération avec METRIC_RECOVERY_IMMUTABLE_SOURCE_MESH_QUALITY ;
la correction des contacts n'est pas démarrée. Le refus anticipé n'a donc pas
été exercé dans une récupération réelle et aucun gain global n'est établi.

Les 501 fichiers figés, les entrées, MAIN et le corps sont préservés. Le
précontrôle v4 vérifie le clone du diagnostic v3 et les identités ; il ne
réexécute pas l'authentification SQLite de la revue réelle v3. La revue détaillée
indépendante confirme les refus. De v3 à v4, les faces originales sous 15°
passent de 36 à 24, mais le minimum matériel tombe de 4,483887° à 2,560347° ;
la variante passe de 30 à 26 faces sous 15° et de 4,057463° à 1,490443°.
La baisse du nombre de défauts ne permet pas l'admission. Le rollback des
manches conserve leur baseline ; la nouvelle trajectoire de raffinement
s'arrête au premier essai. Le transport binary32 ne cause pas le franchissement
du seuil de 2°. Le fichier Blender est sauvegardé, sans essai de réouverture.
Les succès logiciels et des coupons ne prouvent pas la correction du maillage
réel : reprendre
l'investigation du conditionnement et des propositions CDT, puis rejouer les
contrôles dépendants avec les mêmes sources, appuis, corps et seuils.

Qualification NONE : physique, enfilage, drapé, fitting complet, mouvement du
vêtement, revue artistique, préversion finale et nouvelle installation restent
à réaliser. L5 et l'acceptation du manteau restent incomplets.

### Intégration suivante — restauration source56 et cages source57

La régression de l'expérience CDT est corrigée dans `a4aad9b` en restaurant
exactement le noyau source53. L'essai natif comparatif prépare les dix pièces
et leurs 24 relations, puis exécute neuf triangulations sur les deux manches
et le devant gauche. Les maillages, correspondances, historiques et traces
du candidat restauré sont identiques à source53. Les minimums restent
4,061237°, 4,057463° et 4,483887° : le critère régulier de 15° reste refusé.
La mesure dure 36,294 s, lancement 41,297 s ; sources et entrées sont conservées.

Le défaut majeur de représentation de la cage du dos est corrigé dans
`9f95efa`. Le raffinement source déclaré est partitionné aux hauteurs des
sections mesurées, puis la cage est conservée par le second consommateur
après contrôle du domaine, des coins, des faces source, des bords et de la
topologie. Au témoin exact du dos, les étirements principaux passent de
`[0,015424 ; 0,903090]` à `[0,995835 ; 1,002274]`. L'écart maximal à l'arc
direct vaut 0,00183330 cm. Cette mesure locale ne qualifie pas tous les guides.
La partition complète des U reste refusée et archivée ; aucun seuil ne baisse.

La revue indépendante passe 88 tests ciblés et quatre sondes supplémentaires.
La source57 figée comprend 505 fichiers, identité
`d09e85365e354c33cd2c02ce3e9e61f5341db20571991da2bf686ad0501feaa8`.
Ses 1 055 tests intégrés passent en 188,520 s, lancement 189,703 s ; les fichiers
figés restent identiques. Les présents ajouts de suivi sont postérieurs à
cette capture et ne prolongent pas ses tests. Les empreintes et reçus figurent
dans le [bilan de cette unité](automation-cage-restoration-evidence-20261004.json).

L'alignement du devant intérieur et du col, le conditionnement matériel à 15°,
les contacts et la couverture restent à corriger ou vérifier. L5 demeure
incomplet. Aucun PASS de physique, fitting, mouvement du vêtement, revue
artistique, préversion finale ou installation n'est accordé par cette unité.


### Alignement sourcé du devant intérieur — source59

Le commit `7996345` calcule une rotation propre et une translation depuis tous
les homologues permanents attendus entre les rôles `inner_front` et `front`.
Les UV, patrons, crans, partenaires du torse et corps sont conservés. Le noyau
Horn utilise au plus 64 rotations Jacobi, dans le budget et le délai partagés.
Les liens au col restent explicitement partiels ; aucun READY global n'est émis.
Les empreintes incluent le nouveau calcul et les rôles transmis. Les appels
historiques sans rôles conservent leurs reçus SOURCE57 exacts.

Les 1 072 tests intégrés passent en 192,915 s, lancement 194,343 s, sur les
509 fichiers figés de source59. Les 14 contrats indépendants passent aussi.
La revue indépendante reproduit 81 tests ciblés, neuf sondes supplémentaires
et tous les champs substantifs du replay, avec sources et références conservées.
Les ajouts documentaires présents sont postérieurs à cette capture.

L'écart maximal des 34 homologues passe de 20,151141 à 1,064999 cm ; le RMS
pondéré de 15,512012 à 0,875460 cm. Le seed reste rigide et déplace certains
contrôles de 34,630316 cm depuis le guide initial, déplacement conservé au reçu.
Après les moyennes avec le col non corrigé, le devant intérieur garde 142 faces
de cage hors [0,9 ; 1,1] : son maximum diminue de 88,942242 à 63,663509, mais
son minimum se dégrade de 0,080311 à 0,068041. Le triangle historique8082,
évalué aux mêmes UV sur ces cages, reste refusé à un maximum de 1,863016.
Ces métriques portent sur des cages auxiliaires, sans qualification du maillage
textile régulier, des contacts, du Cloth ou du fitting.

Le [reçu de l'alignement](automation-rigid-alignment-evidence-20261004.json)
lie le code, les tests et les observations. La correction conjointe de
l'encolure, le conditionnement à 15°, les contacts et la couverture restent
à réaliser avant l'admission L5. Aucun succès du seed ou des tests ne devient
une acceptation du manteau, une préversion finale ou une installation.

### Expériences numériques externes et cause du blocage

Les hypothèses de circumcentre stabilisé et de transport des intérieurs sont
mesurées en Blender isolé, puis revues indépendamment. Le transport améliore les
manches de 4,264129° / 4,313422° à 5,961774° / 6,270067°, mais le devant passe
de 5,453778° à 4,552743°. Tous restent refusés à 15°. Les identités, naissances,
budgets cumulés et rollbacks observés passent ; les prototypes restent externes
au noyau livré. Les deux campagnes et l'investigation conjointe de l'encolure
sont liées dans le [reçu des expériences](automation-numerical-probes-evidence-20261004.json).

La courbe brute du col ne peut rejoindre les deux arrêts par rotation seule.
Les sondes ancrées compriment trop certains chemins et sont refusées. Le solveur
V1 sous longueurs source stagne avec 4,191628 % d'erreur. Sa garde IEEE autorise
un pas de 0,5000000000000031 cm ; cela n'est pas un PASS du budget strict de V2.
La cause liée à la proximité reste une inférence, sans optimum global établi.

Le solveur V2 minimum-norm retrouve les 12 segments, 362 subdivisions et six
chemins du problème V9 historique dans leurs bornes IEEE dérivées. La revue
indépendante vérifie les 43 candidats, les 14 états acceptés, les arrêts exacts,
24 tests et le petit système JJᵀ. Le pas accepté maximal est
0,4999999999999945 cm ; le déplacement maximal depuis la référence V9 est
3,5238366456088657 cm. Les minuscules subdivisions doivent garder leurs erreurs
absolues et leurs bornes, sans seuil relatif de matériau. Le code reste externe,
sans intégration de bande, cage, contact ou qualification du candidat courant.

Le prototype des 45 graines d'éventails indépendants régresse en Blender :
1,193126° / 1,193124° aux manches et 1,525462° au devant. Les trois candidats
stagnent, sans plafond atteint ; les baselines sont reproduites à l'octet près.
Des graines de coins voisins occupent certains triangles analytiques ; aucun
point original ne les occupe. Cette obstruction locale ne prouve pas toute la
causalité. Le candidat est refusé et ne modifie pas le noyau livré.

Le [reçu de la seconde revue numérique](automation-numerical-probes-evidence-v2-20261004.json)
lie les preuves, leurs portées et la CI du commit documentaire ed345ddb.
La prochaine unité prépare des subdivisions communes aux bords source, avec
budgets initiaux comptés, références matérielles conservées et aucun succès
global déduit du témoin local. Un replay frais du col sur le code courant et la
composition approuvée est distinct du résultat historique V9. L4 reste partiel,
L5 non admis ; aucun Cloth, fitting, préversion finale ou installation n'est
qualifié par ces expériences.

### Référence et échéance partagées — source61

Le commit `9276422` ajoute les options `displacement_reference` et `deadline`
à la récupération métrique. L'entrée corrigée, l'alignement, les propositions
et le meilleur retour utilisent la référence du guide avant correction : le
déplacement déjà consommé n'est pas remis à zéro. Les contraintes numériques
injectées restent distinctes des pins et des arrêts source. Les nouveaux appels
vérifient le pas réel sans epsilon et n'admettent aucun résultat après expiration.
L'arrêt est coopératif ; la validation finale peut dépasser l'échéance et reste
alors une observation d'un résultat incomplet. Les appels sans ces options
conservent les reçus et les nombres d'appels d'horloge historiques.

La revue indépendante reproduit les 79 tests ciblés, huit sondes supplémentaires,
12 reçus historiques et trois témoins d'horloge. Les 1 095 tests intégrés passent
en 229,823 s (lancement 232,109 s), avec les 14 contrats indépendants. Le snapshot
source61 contient 514 fichiers identiques au commit et conservés après les tests.
Le build local vérifié reste un build de développement déclaré 0.7.0-rc.2,
sans publication ni installation. Ce suivi documentaire est ajouté après cette
capture. Le [reçu de la récupération partagée](automation-shared-recovery-evidence-20261004.json)
lie le code, la revue, les tests et l'archive exacte.

Le replay frais du col sur source60 et la composition approuvée est revu :
12 segments et 362 subdivisions respectent leurs bornes IEEE, avec 11 itérations
et un déplacement maximal de 1,3284480315009943 cm depuis sa nouvelle référence.
Ces preuves sont distinctes du témoin V9 historique et n'accordent aucun gate
au projet composé. Le [reçu du col courant](automation-current-neckline-evidence-20261004.json)
lie cette courbe et le précontrôle séparé des six surfaces.

Le payload auxiliaire conserve 20 278 contrôles, 38 316 triangles et 13 coutures ;
730 propriétaires transitifs reçoivent la courbe, huit stops restent exacts et
aucun pin physique n'est inventé. Ces cages restent refusées aux seuils déclarés
2° et 15°, avant et après injection, sans optimisation. Le col a notamment une
arête UV de 1,249999997 × 10⁻⁷ cm ; une face du devant gauche devient presque
aplatie après injection. Le refus porte sur ce maillage auxiliaire et ne prouve
pas l'impossibilité du patron ou du vêtement. L'enveloppe courbe+surfaces reste
non installable tant que ses phases et son horloge commune ne sont pas déclarées.

Le premier essai natif du raffinement des bords s'arrête avant CDT sur une
divergence de comparaison de batch. L'ordre des clés numériques puis textuelles JSON
est une cause portable reproduite sans écart scalaire ; sa portée native reste
à établir par un diagnostic isolé. Le refus et ses entrées sont conservés.
L4 reste partiel et L5 non admis ; aucune physique, qualification de fitting,
revue artistique, préversion finale ou installation n'est acquise par cette unité.

### Bords gradés — refus natif attribué et conservé

Le diagnostic isolé confirme la divergence de sérialisation : 4 632 clés
numériques (`int` et `float`) deviennent textuelles dans JSON. Les 78 853 valeurs
et leurs types sont conservés exactement. La comparaison corrigée s'appuie sur
ces identités, sans epsilon ; le diagnostic seul n'exécute aucune CDT.

Le replay V3 conserve dix pièces préparées, 24 relations, les 2 236 anciens
contrôles et 40 fractions nouvelles transportées en 80 contrôles débités. Les
trois baselines sont reproduites à l'octet près. Les nouveaux angles minimums
sont 1,834793° et 1,699532° aux manches, puis 0,715063° au devant gauche : les
trois candidats restent refusés au seuil de 15°.

La seconde triangulation restitue exactement les positions déjà acceptées des
premiers points refusés. Le lisseur repart de l'entrée courante et leur ajoute
un déplacement ; le contrôle depuis leurs naissances permanentes refuse alors
0,622328 / 0,629737 / 0,591643 cm contre 0,5 cm. Les références sont correctes.
L'arrêt final découle de ce dépassement, sans stagnation d'insertion. Le meilleur
état est restauré exactement ; les 35 / 35 / 16 insertions tentées restent
débitées. La revue indépendante confirme les six résultats et conserve 2 702
fichiers. Le [reçu des bords gradés](automation-graded-boundary-evidence-20261004.json)
lie les preuves et leur portée.

La prochaine correction donne au lisseur une référence permanente explicite.
Le noyau Blender livré reste inchangé pendant cette étude ; aucun plafond
n'est relevé. Une meilleure proposition de maillage et la qualification du
vêtement restent à établir. Les refus du maillage auxiliaire ne constituent
aucune preuve d'impossibilité des patrons. L4 reste partiel, L5 non admis.

### Identités matérielles séparées du porteur UV

Le commit `1322725` ajoute le contrat local `MATERIAL_SAMPLE_CARRIER_V1`.
Source, porteur et échantillons gardent des identités distinctes ; les supports
barycentriques et intersections sont rationnels. Une face du porteur peut
traverser plusieurs faces source : la couverture est contrôlée exactement dans
les deux sens. Des fractions voisines et les crans à 1/2 restent distincts.
Aucun voisin spatial, weld ou arrondi ne remplace une identité source.

Les 55 tests ciblés passent, dont 39 nouveaux. La revue reproduit ces tests,
ajoute 21 sondes et vérifie 7 886 assertions exactes sur le col. Le témoin garde
743 contrôles et huit samples de crans, sept crans, six coutures permanentes et
une fermeture ; 586 intersections couvrent les 13 faces source et 192 faces du
porteur. Le replay est exact hors reçu temporel, avec les mêmes compteurs.
Les 132 fichiers examinés restent conservés. Voir le
[reçu du porteur UV](automation-material-carrier-evidence-20261004.json).

Ce format n'est consommé par aucun caller ni solveur de production. Les anciens
schémas et validateurs restent conservés ; ce module ne peut pas les contourner.
La phase chronométrée de 60 s commence après le précontrôle et l'empreinte JSON
bornés. Le coût maximal en entrée n'a pas été qualifié. Les fractions d'arc sont
déclarées ; la géométrie des partenaires externes et le champ 3D restent à
vérifier. Une grille UV exacte ne prouve ni la représentabilité des cassures
en volume, ni la faisabilité des contraintes interpolées, ni le fitting.

La prochaine unité spécifie le champ 3D, sa référence avant injection et les
contraintes de la courbe, avant toute récupération des six surfaces. Les
mesures restent liées à leurs candidats ; aucune preuve de coupon, de courbe
ou de couverture UV n'est transférée aux gates du vêtement.

### Lisseur cumulatif et candidat logiciel source62

Le commit `6fdd487` ajoute la référence permanente optionnelle du lisseur.
L'entrée hors budget est refusée, les propositions et le retour utilisent la
même limite stricte. La référence est copiée immuablement ; les ancrages restent
fixés à l'entrée. Les 38 tests ciblés et 11 sondes indépendantes passent ;
34 témoins historiques reproduisent exactement les points, reçus et refus.
Les callers historiques restent inchangés. L'essai natif V4 doit encore mesurer
l'effet de cette option sur le maillage complet, après sa revue préparatoire.

Le candidat logiciel source62 est figé sur 523 fichiers du commit exact :
1 151 tests passent en 212,159 s (lancement 213,421 s), avec 14 contrats
indépendants. Les fichiers restent conservés. Le build local de 2 914 188 octets
est vérifié, SHA-256 `a404f525317aec0749689eb89e051dcc74c6a07796ebad8838b9f13d9eece5f3`.
Il reste un build de développement déclaré 0.7.0-rc.2. Les ajouts documentaires
suivants sont distincts de ce snapshot. Le [reçu source62](automation-mesh-shared-reference-evidence-20261004.json)
lie le code, les revues, les tests et l'archive.

Pour les surfaces, le contrat proposé retient un champ libre affine sur un
porteur fourni et la référence originale avant injection. Le modèle qui garde
les anciennes cassures et ajoute seulement un déplacement affine est refusé
pour le porteur col étudié : ce certificat concerne ce modèle précis. Dix
cassures de la trace proposée manquent au porteur actuel. La compilation et
l'évaluation du nouveau champ sont la prochaine unité ; les contraintes,
la récupération et les contrôles des six pièces restent à qualifier.

### Résultats natifs V4 : trois maillages corrigés, revue indépendante terminée

La référence permanente du lisseur corrige le dépassement cumulatif mesuré en
V3. Sur les mêmes patrons et contrôles préparés, les angles minimaux deviennent
15,038750° pour la manche gauche, 15,050577° pour la droite et 15,125134° pour le
devant gauche. Les déplacements réellement transportés restent au plus à
0,499282 / 0,494336 / 0,499595 cm de leur naissance permanente. Les plafonds et
les seuils de 15°, 0,001 cm et 0,5 cm sont conservés.

La revue indépendante vérifie les six géométries, frontières et identités,
les références après chaque triangulation et les budgets non remboursés :
448 184 assertions passent et 3 939 fichiers restent conservés. Les trois
baselines restent byte exactes, avec leur refus historique. L'essai natif prend
49,872 s, le lancement 55,859 s ; aucun gain de performance comparatif n'est
qualifié. Le [reçu V4](automation-native-shared-reference-v4-evidence-20261004.json)
lie les sorties exactes et les deux revues.

Cette preuve porte sur trois maillages numériques UV. Le batch complet garde
dix pièces, 24 relations, 40 fractions communes et 80 contrôles ajoutés ; la
campagne native des dix pièces est en préparation. La présence physique de
chaque ancien sommet collinéaire authored reste à établir. Le caller de
production n'est pas modifié. Placement, contacts, Cloth, fitting et acceptation
artistique restent ouverts ; aucun PASS de ces trois pièces ne leur est transféré.

### Champ 3D intégré et campagne des dix pièces : état du 5 octobre

Le [champ affine 3D](material-surface-field.md) est intégré au commit `71a284e`.
Il conserve la référence avant injection, les supports matériels exacts et les
budgets communs ; aucun caller de production n'est modifié. La revue V3 passe
98 tests et 38 contrôles indépendants, après correction de deux refus conservés.
Le [reçu source63](automation-material-surface-field-evidence-20261005.json)
lie les 1 194 tests, les 14 contrats, les 528 fichiers exacts et le build local.
Les six cages actuelles ne sont pas encore compilées ; leur taille exige un
traitement borné adapté. Contraintes et récupération restent à qualifier.

Les [observations natives des dix pièces](automation-native-full-ten-evidence-20261005.json)
sont revues : neuf traitements atteignent les seuils numériques, le col reste
à 12,372726°. Les treize cas sont clos à 86,390 s et 895 517 assertions passent.
Le bilan final dépasse ensuite le plafond de 90 s : la campagne reste incomplète,
malgré le statut COMPLETE erroné du reçu original, conservé. Le correctif host
est séparé et en revue ; aucune relance ni hausse de budget n'est implicite.
Une borne sur quatre triangles actuels du col ne prouve aucune impossibilité
du patron. La correction des subdivisions et de leurs partenaires est en cours.

L4 reste partiel, L5 non admis. Le vêtement complet, les contacts, le drapé,
le fitting, les mouvements et la revue artistique restent à réaliser. Le build
de développement reste déclaré 0.7.0-rc.2, sans nouvelle installation ni release.

### Contraintes interpolées intégrées au candidat source64

Le commit `13ebc0a` ajoute le [compilateur de raccords](material-surface-constraints.md).
Les coutures permanentes et arrêts physiques forment des lignes rationnelles
exactes ; les cibles IEEE restent des observations SOFT. Les déclarations
locales, la référence fraîche complète, les identités, les budgets communs
et la sortie entière sont contrôlés. Aucun pin ni caller de production n'est
ajouté. Les 123 tests et 23 sondes de revue passent, avec 1 223 assertions.

Le [reçu source64](automation-material-surface-constraints-evidence-20261005.json)
lie les 1 219 tests intégrés, les 14 contrats et le build local aux 533 fichiers
du commit exact. La preuve de rang porte sur les contraintes HARD déclarées,
pas sur la métrique, les douze barres, le continu physique ou le fitting.
Les six références de surface actuelles et leurs porteurs restent à adapter
exactement et sous une enveloppe bornée. L4 reste partiel et L5 non admis.

### Chemins continus de surface : module revu et intégré

Le commit `9748d3f` ajoute l’[observateur de traces](material-surface-traces.md).
Il conserve les cassures de chaque champ fourni et mesure séparément C,
la référence fraîche et le précédent. Les cordes et longueurs continues
gardent leurs propres quantités ; les bornes historiques ne deviennent pas
une marge supplémentaire. Une longueur sans bande explicite reste mesurée
sans décision d’acceptation. Le transport continu entre partenaires reste absent.

Le [reçu des traces](automation-material-surface-traces-evidence-20261005.json)
lie les 130 tests ciblés, 7 sondes et 614 assertions de revue indépendante.
Les caps existants, le budget commun par appel et le contrôle de délai après
le dernier hash sont conservés. Aucun caller de production n’est modifié.
La suite complète et un nouveau package ne sont pas encore exécutés pour ce
commit ; source64 conserve sa portée historique. Les six surfaces réelles,
leur récupération, les contacts et le fitting restent à qualifier.

### Référence UV construite par code et candidat logiciel source65

Le commit `97d247f` ajoute la [partition de référence matérielle](material-reference-partition.md).
Les seeds sont rationnels depuis leurs poids source ; les cellules, bords,
parents et vues par face restent explicites. Le vérificateur reconstruit le
certificat de construction. Les samples et crans demeurent des observations,
sans créer implicitement des inconnues de géométrie. Les callers et anciennes
références fraîches restent conservés.

Sur le source réel du col, la construction UV seule produit 477 nœuds,
832 triangles actifs, 13 vues source et 120 intervalles de bord qui couvrent
exactement les 15 bords source. Les 751 samples incluent huit crans. Cet essai
utilise les sections extrêmes ; les sections intérieures sont couvertes par
fixtures séparées. Les 367 087 opérations de fractions demandent le plafond
explicite du nouveau format ; l'essai par défaut s'arrête à 300 000. Le plafond
du champ 3D existant reste inchangé. Aucune substitution de S_fresh n'est faite.

Le [reçu source65](automation-material-reference-partition-evidence-20261005.json)
lie les revues, les 1 272 tests intégrés, les 14 contrats et le build local aux
541 fichiers exacts. Il couvre aussi le module de traces ajouté après source64.
Le package reste déclaré 0.7.0-rc.2 ; les ajouts documentaires suivants sont
distincts du snapshot testé. La partition UV ne crée ni champ 3D qualifié ni
budget agrégé entre appels. Les six surfaces réelles, contraintes, métrique,
contacts et récupération restent à intégrer. L4 reste partiel et L5 non admis.

### Cascade synchronisée : col et deux dos corrigés en essai UV isolé

Le [nouveau reçu natif](automation-native-cascade-three-evidence-20261005.json)
conserve les patrons approuvés et ajoute quatre fractions communes avec leurs
partenaires. Les angles minimaux sont 15,073571° au dos gauche, 15,014254° au
dos droit et 15,288697° au col, contre 12,372726° pour le précédent col. Les
bords, aires et topologie restent contrôlés. Les distances cumulées depuis
la naissance de chaque point, y compris après Float32, respectent 0,5 cm.
Les tentatives sont débitées sans remboursement : 31 / 31 / 14.

La revue indépendante passe 1 353 016 assertions et conserve 4 200 fichiers.
La préparation complète native/portable est exacte sur 10 pièces, 24 relations,
2 324 points de bords et 88 contrôles ajoutés. Les sept autres pièces n'ont pas
été exécutées pour ce nouveau candidat et restent non qualifiées. Aucun nouveau
rollback non monotone n'est exercé par ces trois historiques monotones.

Le host révisé atteste cette campagne avec le QPC commun et la finalisation
contrôlée. Le checkpoint natif post-persistance est 50,585448 s ; le consumer
après lecture/hash est 50,992853 s. L'erratum distingue le snapshot host persisté
avant écriture de la valeur tool-only après écriture. Le lancement prend
62,165795 s sous watchdog 120 s ; le budget de calcul 90 s a une autre origine.
Le bilan historique des dix pièces reste incomplet et conservé.

L'audit borné du runtime produit ne démontre aucun mélange d'origines entre MCP
et Blender : les chemins examinés transportent des durées et créent leurs
échéances localement. Ses 18 sondes passent ; aucun patch du plugin n'est proposé.
La cascade corrigée demeure un essai isolé, à intégrer dans les callers natifs.
Elle ne qualifie ni présence physique de tous les anciens authored, ni surfaces
3D, contacts, Cloth, fitting, mouvement ou acceptation des 15 textiles et boucle.

### Maillage synchronisé intégré, campagne native et volume encore ouverts

Le [bilan source67](automation-synchronized-meshing-20261005.md) et son
[reçu](automation-synchronized-meshing-evidence-20261005.json) lient le profil
explicite, les revues, les 1392 tests intégrés, les 14 contrats et le
build local au commit exact. Les bords réels passent leur comparaison publique
UV. Le champ du col s'arrête au plafond de sortie avec un résultat absent ;
son format compact séparé est en développement. La campagne native du profil,
les surfaces 3D, contacts et fitting restent ouverts. Aucun PASS historique,
portable ou de coupon n'est transféré au manteau complet.

### Stockage compact exact : module revu, col réel à exécuter

Le [format compact](material-surface-compact.md) et son
[reçu de revue](automation-material-surface-compact-evidence-20261005.json)
conservent la référence complète et les coûts cumulés. Les 129 tests ciblés,
15 sondes et 12 résultats V1 complets passent. Le commit `7b703b5` ajoute
uniquement ce stockage ; le build source67 le précède et ne l'inclut pas.
Le col réel, l'observer, les métriques et contraintes restent à exécuter ou
développer. Aucun résultat de stockage n'admet le placement ou le fitting.

### Col sauvegardé, métriques privées et stockage natif encore incomplet

Le [bilan des calculs et du stockage](automation-calculation-storage-20261005.md)
et ses [preuves](automation-calculation-storage-evidence-20261005.json) remplacent
le statut d'attente précédent pour le col compact. Sa référence fraîche complète
de 743 sommets et 1098 triangles est compilée et sauvegardée sous les mêmes caps,
en 51,625 s au checkpoint terminal. L'écart physique stdout de 1 octet sous Windows
reste un finding à corriger ; cette compilation n'admet pas le placement.

Le module privé de métriques affines passe 92 tests et neuf sondes, sans nouvelle
mesure du col réel. Les essais natifs V2 et V3 terminent le calcul des dix pièces,
mais refusent la sortie complète sous la limite de stockage. Les qualités par pièce
restent absentes et non qualifiées ; aucun PASS historique n'est transféré. La suite
porte sur ces frontières de transport et de stockage, puis les métriques, contacts,
construction physique et revues du candidat exact.

La [mise à jour de transport du col](automation-current-collar-transport-evidence-20261005.json)
confirme désormais le stdout UTF-8/LF physique exact sur l'essai V3 complet,
sous les caps conservés. Les métriques réelles sont la prochaine unité ; ce
résultat de persistance n'admet toujours pas le placement ou le fitting.

### Observation affine du col : défaut localisé, admission ouverte

L'[observation du champ expérimental du col](automation-current-collar-metrics-20261005.md)
est maintenant exécutée et sauvegardée : 144 faces respectent les bornes,
48 les dépassent. La référence auxiliaire et les maillages natifs restent des
candidats distincts. La localisation et une correction calculée précèdent
l'admission de placement ; les patrons, le corps et les gates sont conservés.

### 2026-10-05 — Seed rigide du col revu

Le placement préalable du rôle `collar` utilise maintenant tous ses raccords permanents déclarés et les positions partenaires proposées après le seed du devant intérieur. Une rotation propre et une translation communes déplacent tous ses contrôles ; les patrons et le corps restent conservés.

La revue indépendante reproduit 59 tests ciblés, 7 comparaisons historiques et 11 sondes. [Preuves exactes](automation-collar-rigid-alignment-evidence-20261005.json) et [contrat de la capacité](collar-rigid-alignment.md). Statut portable uniquement, qualification `NONE`. La propagation intérieure, les métriques après couplage, les contacts et la réduction des 48 défauts du champ auxiliaire historique restent à mesurer sur un nouveau candidat complet.

### 2026-10-05 — Qualification logicielle source68

Le commit `65f8965deed6a03475f3f1c66f70c8685db3c4e9` est exporté et capturé sur 579 fichiers exacts. Une exécution locale donne 1 501 tests PASS en 197,576 s et 14 contrats PASS. L’archive de développement est vérifiée contre ces mêmes fichiers et le Git exporté. [Preuves du candidat](automation-software-source68-evidence-20261005.json).

Cette preuve couvre le logiciel et son build local 0.7.0-rc.2. Elle ne publie ni préversion finale ni installation et ne qualifie pas le maillage, le placement ou le fitting. Le préflight natif V4 conserve son refus de revue pour attestation incohérente des lectures ; V5 prépare la correction ciblée avant un nouvel essai isolé.

### 2026-10-05 — Essai natif V5 : stockage incomplet

L’unique processus isolé V5 termine avec un diagnostic de réserve mémoire `ALLOCATION`. Seule la capture des entrées est sauvegardée ; le calcul final reste `UNKNOWN_OR_UNATTESTED`, sans nombre de pièces ou qualité admis. [Diagnostic actuel](automation-native-storage-diagnostic-20261005.md) et preuves exactes associées.

Les plafonds sont conservés. Le correctif suivant prépare un JSON ASCIIescaped compté exactement, en préservant le texte après parse et les conventions UTF-8 du hash et du DTO développé. Il attend tests, revue et nouvel essai propre ; aucun gain réel ou admission du manteau n’est annoncé.

### 2026-10-05 — Stockage ASCII du codec V3 revu

Le codec privé encode son DTO en JSON ASCII échappé, avec comptage exact et réserve de `3N + 256` avant sérialisation. Les conventions UTF-8 du hash natif et du DTO développé, les types, valeurs, IDs, rapports, plafonds et horloges sont conservés. Unicode dense peut accroître la sortie et atteindre plus tôt le plafond d’octets.

Les 76 tests ciblés, six comparaisons V2 de l’auteur et neuf sondes indépendantes passent. La revue couvre notamment 265 caractères, dont le contrôle U+007F oublié lors du premier essai, et cinq mesures des buffers directs. [Preuves V3](automation-native-diagnostic-arrays-v3-evidence-20261005.json). Les échecs V1, les preuves V2 et le refus natif V5 restent conservés avec leur portée.

La qualification reste `NONE` : aucun payload natif réel n’est exécuté par ce lot. Le nouvel adaptateur isolé doit encore être revu et essayé avant toute affirmation de persistance complète. La préparation du col conserve aussi le refus de revue de son premier lecteur de stdout ; son correctif LF est revu séparément avant exécution.

### 2026-10-05 — Qualification logicielle source69

Le commit `21509d9061d40ffce0f05601e0cd91c7169fad46` passe une suite complète de 1 511 tests en 215,119 s, puis les 14 contrats. Ses 583 fichiers exportés depuis Git et capturés restent identiques après exécution. Le build local est vérifié contre ces mêmes fichiers ; [preuves source69](automation-software-source69-evidence-20261005.json).

L’archive conserve la version déclarée 0.7.0-rc.2 pour le développement local. Elle ne publie pas la préversion finale, n’installe pas le plugin et ne qualifie pas le manteau physique. Les preuves source68 restent historiques. La préservation mesurée par ce lot couvre l’export Git et la copie de test ; aucun checkpoint distinct des originaux avant source69 n’est revendiqué.

La [CI du commit exact](https://github.com/leuzeus/atelier-3d/actions/runs/37321173885) passe sur Windows 3.11 et Ubuntu 3.13, avec tests, contrats Windows et archives. Le compteur de tests provient de l’exécution locale ; il n’est pas extrait des logs du fournisseur.

### 2026-10-05 — Référence du col : diagnostic à préciser

L’unique essai de référence fraîche se termine en 30,078 s avec `StudioError`, sans référence complète. [Observations et limites](automation-current-collar-reference-diagnostic-20261005.md). La lecture indépendante confirme le refus et la préservation des entrées, mais le message et la phase sont absents du diagnostic. La nouvelle opération prépare leur capture bornée avant un nouvel essai ; aucune cause géométrique ou qualité n’est inventée.

### 2026-10-05 — Priorité actuelle : placement, drapé et fitting du manteau

Cette priorité remplace les prochaines actions expérimentales décrites ci-dessus, sans supprimer leurs travaux ni leurs preuves. Le chemin à terminer est celui du manteau approuvé sur le corps masculin accepté à 180 cm : placement admis, premier drapé, puis fitting mesuré. Chaque nouveau correctif doit répondre à un défaut observé sur ce chemin. Les 1 511 tests logiciels ne mesurent pas l’avancement physique du vêtement.

Les modules privés de stockage et de champ matériel ne sont pas importés par les opérations Blender de production. Leur essai natif V6, préparé et revu, reste différé et non exécuté. La capture supplémentaire du diagnostic privé du col est une proposition non intégrée ; elle ne conditionne pas la préparation native du manteau.

Le contrôle du projet composé `44f03e6c-dc68-4adb-85b9-e30f88b1aeaa` est actuellement refusé par le MCP connecté. Sa copie installée 0.7.0-rc.2 ne contient pas `a3d/reviewed_pattern_admission.py`, présent dans la source testée, et charge un autre `blender/bootstrap.py`. Il faut donc charger un build local distinct par le mécanisme natif de Codex, puis refaire `studio_check_pipeline`. Ce refus ancien ne justifie pas une nouvelle approbation des manches inchangées.

Après admission, réunir les artefacts exacts et les décisions existantes du corps accepté, préparer les opérations du plugin et demander l’autorisation pour chaque exécution Blender. L’archive source69 existante est un build de développement, pas une installation ni un runtime connecté. La préversion GitHub finale attend toujours l’acceptation prévue par L11.

Le texte de la PR est envoyé depuis un fichier UTF-8 sans BOM et relu depuis GitHub pour vérifier son contenu exact et ses accents. Ce contrôle documentaire ne qualifie pas le produit.

### 2026-10-05 — Corps accepté présent dans la construction actuelle

Le run public `run.74b32ba8748a452a93e1983fa1664357` est terminé après
l'autorisation distincte d'introduire le mannequin. Le reçu canonique et le
checkpoint natif sont vérifiés : [preuve du contexte corporel](automation-body-context-20261005.json).
La scène contient le corps masculin accepté à 180 cm, sans redimensionnement
ou déformation, avec collision de 0,3 cm. Aucune pièce de vêtement n'a encore
été construite dans cette scène ; aucun Cloth ou fitting n'est exécuté.

La compilation actuelle couvre les 15 textiles et la boucle. La préparation
initiale des guides et templates manquait dans l'interface publique. Une
branche optionnelle du compilateur réutilise maintenant ses producteurs
existants avec paramètres, recette et dossier de sortie explicites. Elle doit
être chargée dans le runtime connecté avant l'essai réel du manteau. Les
paramètres et recettes exacts sont disponibles dans le projet ; aucun ancien
guide, mapping ou résultat de placement n'est transféré.

### 2026-10-05 — Préparation publique testée et nouveau build installé

Le commit `11d0b807f716c0df4216cce9c1e0b6158561c79e` expose la préparation
initiale dans `studio_compile_production_dossier`. Les 1 528 tests logiciels
et les 14 contrats passent ; la revue indépendante clôture les deux défauts
de diagnostic corrigés. [Preuves logicielles et installation](automation-public-preparation-evidence-20261005.json).

Le build `0.7.0-rc.2.dev.2026100501` est installé par Codex et ses 592 fichiers
sont vérifiés. La copie précédente sur G: reste disponible. Le runtime connecté
doit être rechargé avant la vérification `studio_doctor`, la nouvelle admission
du projet et l'appel réel de préparation. La requête est prête dans
`preparation/public-source-preparation-request-v1.json` du projet composé.
Les guides du manteau ne sont pas encore calculés par ce build, et aucun
résultat de placement, physique ou fitting n'est accordé.

### 2026-10-05 — Runtime rechargé et distinction entre guides et placement

Après le redémarrage, le MCP confirme `0.7.0-rc.2.dev.2026100501`, son chemin
installé et son empreinte. L'admission du projet composé passe. L'appel public
de préparation a réellement calculé les guides et le plan, puis a refusé les
templates du manteau : [tentative exacte](automation-public-preparation-attempt-20261005.json).
Les dix panneaux sont présents, sans pièce en attente ; le défaut déclaré est
l'alignement encore partiel des relations source. Cette observation ne démontre
aucun défaut du corps ou du découpage approuvé.

Le correctif distingue la complétude des entrées de l'admission du placement.
Seul ce diagnostic partiel précis peut produire un template marqué
`NEEDS_CORRECTION` ; les guides source et les critères finaux restent inchangés.
Les diagnostics sont transmis par l'interface publique. Le consommateur natif
existant `bind_component_preparations` est raccordé au dispatcher contrôlé :
origine native du corps, références exactes, package canonique, policy obligatoire,
collider déclaré, checkpoint et reprise vérifiée d'un binding complet. Un
répertoire partiel reste conservé et exige une nouvelle opération.

La revue indépendante a relevé puis fait corriger le refus de reprise d'un
binding complet et le contrôle tardif du package canonique. Les tests et le
build local de ce correctif sont enregistrés séparément ; aucun essai Blender
du nouveau binding, placement, Cloth ou fitting n'est exécuté à ce jalon.

Validation du candidat intégré : **1 551 tests logiciels PASS en 201,091 s**,
dont les 23 nouveaux cas de complétude et de binding ; **14 contrats PASS**.
Les journaux sont conservés sur G: dans `program-public-binding-tests-v1.log`
et `program-public-binding-contracts-v1.json`. La dernière relecture indépendante
clôture les deux défauts et vérifie les tests terminés, sans revendiquer un essai
natif. La prochaine requête publique est enregistrée dans
`preparation/public-source-preparation-request-v2.json` ; elle conserve les
entrées et demande un dossier neuf.

Le commit `06173c2301e83901d6ac468dc8e4e1981b6fa9b0` est empaqueté depuis
son export Git exact : 595 fichiers source. Le build local distinct
`0.7.0-rc.2.dev.2026100502` est installé par le gestionnaire natif Codex ;
les 596 fichiers adaptés correspondent au stage vérifié. Les anciens stages
sur G: sont conservés. [Preuves du correctif et de l'installation](automation-source-binding-evidence-20261005.json).

Après installation, `studio_doctor` échoue sur un fichier de l'ancien cache
`dev.2026100501`, remplacé par le gestionnaire natif. Le serveur connecté reste
à recharger : redémarrer Codex, vérifier la nouvelle identité et l'admission,
puis exécuter la requête V2. Préparer ensuite le binding public exact et demander
son autorisation Blender distincte. Aucun binding ou placement nouveau n'est
exécuté ; le fitting et la préversion finale restent soumis aux gates produit.

### 2026-10-05 — Préparation publique V2 calculée après rechargement

Le second redémarrage charge réellement `0.7.0-rc.2.dev.2026100502` :
`studio_doctor` passe et l'admission du projet composé est positive.
La requête publique V2 s'exécute sans erreur et produit les cinq artefacts
de préparation. [Preuve du runtime et du calcul réel](automation-public-preparation-v2-evidence-20261005.json).
La compilation couvre 15 textiles et une boucle ; les guides, la politique
et le plan gardent les mêmes empreintes que la tentative précédente. Les
templates signalent explicitement l'alignement du manteau à corriger, sans
admission de pièce ni validation de placement.

La lecture MCP de Blender retrouve la scène de construction sauvegardée,
non modifiée, contenant uniquement `A3D.BodyTarget.MainMale180`. Ce résumé
n'est pas une revue visuelle. Le run `run.433754fe078b4a46b1f689aec50cbf54`
conserve les 15 références d'entrée et prépare `bind_component_preparations`,
tentative `attempt.d49dd370520b41bcb0dea15c05430152`, en attente de son
autorisation distincte. Le code exact est enregistré dans
`preparation/native-source-binding-run-step-v1.py` du projet composé.
Le binding doit produire les mappings et fichiers natifs ; il n'exécute ni
placement ni Cloth. Son autorisation n'est pas celle des étapes suivantes.

L'appel sans profil de fitting retourne séparément `FIT_METADATA_REQUIRED`.
L'intention de manteau ample et le corps approuvé sont conservés ; les mesures
homologues et la couverture du candidat restent à établir avant admission
physique. Restent ensuite placement admis, construction complète, enfilage,
drapé, fitting, mouvement et revue artistique. Aucune nouvelle modification
de découpage n'est présentée à ce jalon.

### 2026-10-05 — Refus natif préservé, restauration exécutée

Après l'autorisation explicite du raccordement, l'appel natif a refusé la
remeasure des sections de peau, avant de créer le dossier de sorties. Le run
`run.433754fe078b4a46b1f689aec50cbf54` reste `INCOMPLETE`, sans qualification.
Le reçu exact et son checkpoint sont conservés dans
[la preuve du refus](automation-native-binding-refusal-20261005.json).
L'autorisation distincte de restauration a ensuite été exécutée : Blender a
réouvert le checkpoint vérifié et sauvegardé une nouvelle scène de récupération.
La lecture MCP confirme une scène sauvegardée, non modifiée, contenant seulement
le mannequin accepté. L'opération échouée n'est plus en attente ; son historique
et ses fichiers restent conservés. Aucune revue visuelle, aucun placement ni
Cloth n'est déduit de cette restauration.

La divergence des périmètres est reproduite avec les interpréteurs réels
Python 3.11.0 et Python 3.13.13 fourni par Blender : neuf sections sur onze
diffèrent uniquement sur le scalaire de périmètre, de moins de
`4.3e-14 cm`. Les courbes, statuts, profil et géométrie source sont identiques.
Le calcul utilise désormais `math.fsum` explicitement, pour conserver une
sommation commune aux deux environnements. Le contrôle d'empreinte et la
comparaison intégrale sans arrondi restent stricts. Les politiques et guides
dépendants doivent être régénérés sous la nouvelle identité du code ; les
sources anatomiques et les patrons approuvés restent leurs entrées immuables.

La première comparaison des rapports complets révèle aussi des différences
de normalisation des arcs et de longueurs des sections de torse, propagées
aux cibles et à leurs identités. Le correctif couvre donc les accumulations
flottantes de ces générateurs, leurs moyennes et projections communes. Les
compteurs entiers et les partitions UV rationnelles restent exacts. Les
artefacts de diagnostic conservent séparément l'essai limité au périmètre et
la comparaison du candidat intégré. Ils ne constituent aucun résultat natif
de placement, physique, fitting ou revue artistique.

La comparaison V3 des modules réels, après interpolation compensée des cages,
est **identique octet par octet sous Python 3.11.0 et Python 3.13.13** pour la
politique, les guides des trois composants et le rapport complet, sans arrondi.
Les sources, paramètres et code sont vérifiés avant/après ; aucune base de
données ni scène Blender n'est utilisée pour cette preuve numérique pure.
Les comparaisons V1 et V2 restent conservées. Le nouveau binding public reste
à exécuter après installation, rechargement, régénération des dérivés et
autorisation distincte de ses arguments exacts. La requête V3 est préparée
dans le projet composé ; aucune nouvelle coupe n'est proposée à la revue.

Validation intégrée du correctif `18dbde47950ebb9ece6c2946e8971c32bbb98881` :
**1 558 tests PASS en 190,091 s et 14 contrats PASS**, dont sept régressions
numériques supplémentaires. Les tests ciblés passent aussi sous le Python
autonome de Blender. Les journaux initiaux restent conservés : une fixture
de test non sensible a été corrigée avant la suite finale. La revue indépendante
ne relève aucun défaut P2 ou supérieur confirmé ; les seuils, sommes entières
et rationnelles, gardes et autorisations restent inchangés.
[Preuves de la portabilité et des tests](automation-guide-portability-evidence-20261005.json).
Ce résultat qualifie le logiciel et la reconstruction numérique pure des guides.
Le succès du nouveau raccordement natif, les contacts et l'admission du vêtement
restent à mesurer sur leur candidat exact.

Le build local `0.7.0-rc.2.dev.2026100503` est construit depuis l'export Git
`8b4a375ca49e7e4db6330e918edbfe09515f51e3` : 601 fichiers distribués
identiques à cet export et aux modules de la comparaison numérique. Le
gestionnaire natif Codex l'installe ; ses 602 fichiers adaptés correspondent
au stage vérifié. Les stages précédents restent conservés sur G:.
[Preuve du build et de l'installation](automation-guide-portability-installation-20261005.json).
L'observation MCP après installation échoue sur un fichier de l'ancien cache
`dev.2026100502`. **Redémarrage de Codex requis** : le runtime corrigé connecté
reste à vérifier. Reprendre ensuite l'admission et la préparation publique V3,
puis un nouveau run et le raccordement exact à faire autoriser. Le reçu du
refus précédent reste `INCOMPLETE` ; aucune permission n'est transférée aux
nouveaux arguments. Restent placement, construction des 15 pièces et de la
boucle, enfilage, drapé, fitting, mouvements, réouverture et revue artistique.
Aucune nouvelle coupe ni revue anatomique n'est demandée à ce jalon. La
publication finale reste soumise à ces contrôles produit effectivement exécutés.

### 2026-10-05 — Runtime corrigé rechargé, préparation V3 et nouveau run

Le MCP chargé confirme `0.7.0-rc.2.dev.2026100503` ; `studio_doctor` passe et
le projet composé est admis. L'appel public V3 produit réellement les cinq
artefacts de préparation. La politique et les guides complets correspondent
exactement aux digests canoniques de la comparaison des deux Python, en lisant
les fichiers physiques sans conversion des types numériques par le transport.
Le rapport public ajoute ses preuves d'origine native. La compilation couvre
les 15 textiles et la boucle ; les sources anatomiques et les patrons sont
conservés. [Preuve de la préparation V3](automation-public-preparation-v3-evidence-20261005.json).

La lecture Blender confirme la scène de récupération sauvegardée, non modifiée,
avec le seul `A3D.BodyTarget.MainMale180`. Le manteau garde son diagnostic
d'alignement partiel à corriger : aucune admission de placement n'est accordée.
L'appel sans profil de fitting conserve séparément `FIT_METADATA_REQUIRED` ;
l'intention ample et les décisions existantes ne sont pas redemandées.

Le nouveau run `run.1a4b661f07cc4215abf1535c70529df8` conserve 15 références
d'entrée exactes. Sa tentative `attempt.2dd7013e4b5e416e9f25ab302e68533e`
prépare `bind_component_preparations` vers `preparation/native-source-bindings-v2`
et reste `AWAITING_CONFIRMATION`. Le code exact et son empreinte sont sauvegardés
dans `preparation/native-source-binding-run-step-v2.py` du projet composé.
Son exécution demande une autorisation distincte. Le premier refus et sa
restauration restent conservés ; aucun nouveau binding, placement, Cloth ou
fitting n'est exécuté à ce jalon. Aucune nouvelle coupe n'attend de revue ;
les revues visuelles du montage et la revue artistique restent à réaliser.

### 2026-10-05 — Raccordement natif V2 exécuté et réconcilié

Après la demande présentant l'opération exacte, l'utilisateur répond
« continue ». Le code enregistré de `bind_component_preparations` est exécuté
sans changement, sur le runtime connecté `dev.2026100503`. Le reçu natif
`attempt.2dd7013e4b5e416e9f25ab302e68533e` retourne
`NATIVE_PREPARATION_INPUTS_BOUND` en **180,6607187 secondes**. Le journal
`run.1a4b661f07cc4215abf1535c70529df8` est réconcilié `COMPLETED`, sans
qualification ni acceptation produit. Le contrôle natif reconstruit les guides
et confirme leur comparaison intégrale sans arrondi. Les 21 références de
fichiers du reçu et le checkpoint d'entrée sont vérifiés sur disque.
[Preuve du raccordement V2](automation-native-binding-v2-evidence-20261005.json).

Les trois composants textiles ont leurs recettes, plans, préparations et runs :
10 pièces pour le manteau, 4 pour capuche–empiècements et 1 pour la ceinture.
La boucle reste dans l'inventaire source compilé ; elle n'est pas construite
par cette opération textile. Les sondes temporaires ne laissent aucun vêtement
dans la scène : le mannequin accepté reste seul, à échelle unité et avec sa
collision de 0,3 cm. La scène de récupération reste sauvegardée sur disque ;
l'état live est marqué modifié après les sondes, sans nouvelle scène
finale sauvegardée ni acceptée. Aucun placement, Cloth ou fitting n'est exécuté.

La sonde capuche–empiècements révèle un **défaut de maillage dérivé** : angle
minimal 1,794312°, aire minimale 0,000141379 cm² et arête minimale
0,005035583 cm. `probe_quality = NEEDS_CORRECTION` reste dans le binding.
Une correction de ce dérivé doit préserver les contours, crans et relations
approuvés ; ce constat ne démontre aucun défaut de coupe. Le manteau garde
son alignement partiel à corriger. Aucun seuil d'admission n'est assoupli.

Le run séparé du manteau `run.04d8b017e9d340e4834eb1e26d4eafd0` prépare
`prepare_pattern_assembly` avec sa recette et sa préparation issues du binding
V2. La tentative `attempt.c5b8a1c8f91949edb10e65c54bca7477` reste
`AWAITING_CONFIRMATION` ; son code exact est enregistré dans le projet composé.
Elle produira un candidat distinct, ses mesures et vues techniques. Le statut
final peut rester `NEEDS_CORRECTION` ; seul `READY` autorise la suite de ce run.
Cette nouvelle opération n'est pas couverte par la permission du raccordement.
Les revues de placement et artistique restent à effectuer sur les fichiers
examinés ; aucune nouvelle revue de découpe n'est demandée à ce jalon.

Le correctif de provenance d'interpolation est livré séparément au commit
`661be50` : comparaisons UV exactes, routes réellement déclarées du sampler,
aucun epsilon ou fusion ajoutés. Deux lots ciblés sous chaque Python conservent
115 tests de bord/préparation/couture et 66 tests des consommateurs du profil,
soit 181 tests exécutés sous chacun de Python 3.11 et 3.13. La revue indépendante
ne relève aucun défaut P2 ou supérieur restant dans ce périmètre.
[Portée du contrôle et refus suivant conservé](source-boundary-lineage.md).
Ce correctif source n'est pas installé dans le runtime natif `dev.2026100503`.

### 2026-10-05 — Candidat manteau mesuré, refusé et conservé

L'utilisateur autorise explicitement `prepare_pattern_assembly` pour
`garment.coat`, avec les fichiers exacts du binding V2. Le code est exécuté
sans changement sous le runtime installé `dev.2026100503`. L'appel MCP expire
après 300 secondes ; aucune nouvelle soumission n'est faite. Le reçu natif
arrive ensuite et atteste une opération `RETURNED` en **287,6968375 secondes**.
La réconciliation canonique conserve le résultat **NEEDS_CORRECTION** et
requiert le checkpoint d'entrée avant un éventuel rejeu. Ce timeout de transport
n'est pas traité comme une preuve d'arrêt ou comme une permission de relancer.
[Preuves du candidat exact](automation-coat-native-preparation-v2-evidence-20261005.json).

La scène maître et les 32 références de sortie sont vérifiées sur disque.
Les vues neutres face, profil et dos sont effectivement ouvertes et examinées :
le corps traverse le haut du torse et les épaules ; les manches ne l'enveloppent
pas correctement. La silhouette n'est pas celle du manteau original. La
complétude locale est **10/10 pièces du manteau** ; la complétude globale est
**10/15 textiles, cinq absents**. La boucle rigide reste également à construire.
Le candidat et ses images sont des diagnostics conservés, sans acceptation
visuelle humaine ni admission physique. Aucun Cloth ou fitting n'est exécuté.

L'audit des patrons source est `SOURCE_AUDITED`, sans problème de contrat
signalé. Le candidat reste refusé pour triangles effilés, métrique source et
placée, compression/étirement, contacts, ordre des couches non qualifié et
enfilage non évalué. La récupération métrique ne peut réparer une mauvaise
qualité de triangulation source en conservant ce même maillage. Le découpage
approuvé ne devient pas un verdict de capacité des patrons.

Le retour de méthode est intégré : conserver l'original et le découpage, puis
réconcilier explicitement les dimensions et proportions extrapolées des
patrons avec le corps masculin accepté et l'intention ample. L'image originale
est réouverte et son SHA-256 vérifié contre le dossier enregistré. La hauteur
visuelle du vêtement et la stature corporelle sont distinctes. Les hypothèses
initiales de capacité ne valent pas mesures actuelles ; les chemins homologues,
la couverture du devant ouvert et les couches doivent être établis avant
admission physique. Une correction de conception produira une variante à
examiner ; aucune ancienne approbation ne sera transférée à cette variante.

### 2026-10-05 — Mesures actuelles et dispatch du col

Le correctif `c453bad` lit les deux représentations réellement déclarées du
guide de col. Pour une cage UV, il prouve la couverture de toute la ligne source
par découpage rationnel des triangles, puis évalue les ruptures et milieux
d'intervalles. Une représentation malformée retourne un diagnostic localisé.
Les seuils, longueurs source et exigences de revue humaine restent conservés.
**28 tests ciblés PASS sous chacun des Python 3.11 et 3.13**, avec revue
indépendante sans défaut P2 ou supérieur confirmé. Le correctif source n'est pas
installé dans le runtime connecté `dev.2026100503`.

Le corps exact est remesuré en lecture seule par les noyaux existants : dix
sections supplémentaires valides sur douze. Les deux sections à l'épaule sont
refusées pour contours ouverts ou branchés et restent exclues de la fiche.
Les maxima transversaux des manches approuvées sont 45,439902 et 45,476989 cm ;
ils constituent des bornes nominales et ne qualifient pas l'aisance portée.

La compilation source V3 relie les mesures corporelles valides et produit deux
propositions homologues aux poignets : bord source distal de 25 cm contre
17,395739 et 17,441566 cm pour le corps. La revue humaine de ces correspondances
reste requise, `admissible_for_fit` reste faux, et le fitting est non exécuté.
Six diagnostics subsistent : provenance UV native du torse et du haut des
manches, et absence de ligne entière du col au plan du cou mesuré. Le col est
contrôlé sur 725 points pour V=0 et 17 points pour V=7 ; des extrémités seules
ne suffisent pas. Les cibles numériques du manteau ample sont conservées dans
une proposition rattachée au dossier actuel, sans transférer l'approbation
historique de son ancien dossier.

[Bilan dimensionnel et portée des mesures](current-coat-dimensions.md).
La prochaine correction doit réconcilier la provenance native, la couverture
ouverte et les guides anatomiques avant toute nouvelle admission de placement.
La restauration du checkpoint et tout rejeu Blender nécessitent une nouvelle
permission exacte. La découpe approuvée reste conservée ; aucune nouvelle
variante à approuver n'est produite à ce jalon. La revue des correspondances,
la revue du placement et la revue artistique finales restent à effectuer.

### 2026-10-05 — Stockage UV source et reprise d'un résultat retourné

Le commit `4ca988e` authentifie le stockage `SOURCE_DOUBLE` et le stockage
historique `BINARY32` par rejeu canonique des frontières. Les 2 236 ancres du
candidat actuel correspondent exactement au writer. **45 tests ciblés PASS
sous chacun des deux Python**, sans tolérance ajoutée. La compilation source
V3 sous Python 3.11 produit quatre propositions non admises : hauts de bras
45,204894/45,240336 cm et poignets 25/25 cm. Les chemins du torse épuisent leur
budget de 15 secondes ; le col reste sans correspondance complète. Le même
diagnostic sous Python 3.13 refuse auparavant le supplément corporel remesuré,
problème distinct conservé. [Contrat et limites](source-uv-storage.md).

Le commit `bad8b28` ajoute `restore_checkpoint(run_id, attempt_id)` pour une
opération retournée refusée ou incomplète dont le pending a été retiré.
Le chemin historique sans arguments reste conservé. Le checkpoint et le reçu
historique exacts restent restaurables après correction de code ; aucun pending
n'est fabriqué et aucun refus n'est transformé en qualification. **47 tests
portables PASS sous Python 3.11 et 3.13**, avec admission historique en lecture
seule du reçu réel `dev.2026100503` et base SQLite inchangée. La restauration
Blender réelle reste non exécutée et exige une nouvelle permission.
[Contrat de reprise](run-recovery.md).

Ces corrections sont des commits source validés dans leurs périmètres. La
validation du code intégré, son build local et son chargement dans le runtime
doivent être enregistrés séparément. Aucune préversion finale n'est publiée.

### 2026-10-05 — Supplément corporel portable et références séparées

Le commit `d3daa5e` fixe uniquement l'ordre d'accumulation de deux périmètres
dans `body_region_sections`. Le premier écart réel mesuré était de
7,105427357601002 × 10⁻¹⁵ cm sous Python 3.13. Points, plans, axes et statuts
restaient identiques. **26 tests ciblés PASS sous les deux Python** et revue
indépendante sans P2 confirmé. Les nouveaux résultats complets sont identiques
entre runtimes ; les métriques historiques Python 3.11 sont conservées exactement.
L'identité du code et le cache changent légitimement. L'ancien supplément reste
archivé et strictement refusé ; il n'est pas réécrit.

Un supplément actuel V2 séparé est produit avec le nouveau code, en UTF-8 LF,
et son descripteur est réellement authentifié sous Python 3.11 et 3.13. La fiche
proposée V4 utilise cette référence. La compilation publique complète V4 reste
non exécutée à ce jalon ; aucun fitting n'est transféré. Les dix sections
corporelles valides, les deux refusées et le corps accepté restent inchangés.
[Preuve du code](automation-body-region-portability-evidence-20261005.json),
[références actuelles](automation-current-body-v2-evidence-20261005.json).

### 2026-10-05 — Code intégré validé, build local installé, redémarrage requis

Le candidat Git `3d242c08d24efbc0c49ff13ad8e34701ebe81d42` est exporté dans
un répertoire immuable sur G:. La suite complète retourne **1 592 tests PASS
en 203,286 secondes** sous Python 3.11, puis **14 contrats PASS**. Les fichiers
source restent identiques avant/après les tests. Les vérifications ciblées
des nouveaux correctifs sous Python 3.13 conservent leur portée séparée.

Le build local est comparé octet par octet à cet export validé : **620 fichiers
source**. Le gestionnaire natif Codex installe
`0.7.0-rc.2.dev.2026100504`, puis les **621 fichiers installés** sont comparés
à son stage préparé. Les stages G: précédents 21509, 0501, 0502 et 0503 restent
conservés. Aucune confiance des hooks n'est scriptée.

La copie sur disque est vérifiée ; le serveur connecté appelle encore le cache
`dev.2026100503` remplacé. Son `studio_doctor` retourne le chemin de schema
introuvable de cette ancienne version. **RESTART_REQUIRED** est donc observé,
pas déduit d'une simple recommandation. Aucune restauration ni nouvelle
préparation native n'est tentée avec ce serveur périmé.
[Preuves intégrées](automation-integrated-recovery-installation-evidence-20261005.json).

Entrée de reprise après redémarrage de Codex : vérifier `studio_doctor` et le
runtime connecté `dev.2026100504`, puis le pipeline courant. La requête publique
de mesure `preparation/coat-fit-measurement-public-request-current-v4.json`
utilise le supplément corporel séparé V2 et les sources exactes du candidat
conservé. Terminer le diagnostic de capacité du torse, du col et de couverture
ouverte, en conservant les budgets/refus. Préparer ensuite la restauration
native du run `run.04d8b017e9d340e4834eb1e26d4eafd0`, tentative
`attempt.c5b8a1c8f91949edb10e65c54bca7477`, et demander sa permission exacte
avant exécution. Le checkpoint attendu reste
`pre-028b75a4767b4e28b491a65da4bc85c0.blend`, SHA
`376aa273e226cef381f00a717d66db49f794e2c8450928189143c97adca7c301`.
Un nouveau run devra porter les identités actuelles du code et des entrées.

Le produit reste **RECONSTRUCTING** : placement refusé, 10/15 textiles dans
le candidat conservé, boucle absente, aucun Cloth/fitting actuel. Aucun nouveau
patron à examiner n'est produit à ce jalon. Les revues de correspondance de
mesure, de placement et artistique restent humaines. La préversion finale
GitHub attend toujours les critères du vêtement complet.

### 2026-10-05 — Généralité des scripts et essai d'index UV non qualifié

La nouvelle consigne utilisateur est enregistrée dans le
[contrat de généralité](garment-automation-generality.md) : les calculs
consomment les géométries, relations, mesures et budgets déclarés ; les domaines
non pris en charge sont expliqués. Les runners réutilisables prennent leurs
chemins et sélections en arguments. Les anciens reçus de campagne restent
conservés et ne deviennent pas des interfaces de production.

Le commit `8e7a73d` retire deux dépendances de nommage de la borne transverse.
Les bords sont dérivés de la relation source unique ; la section anatomique
vient du domaine épaule–coude déclaré, côté exact et paramètre 0,5, avec
concordance de l'index authentifié. **17 tests PASS sous Python 3.11 et 3.13**,
résultats identiques et revue indépendante. Le domaine reste une manche ou
manchette simple compatible avec cette preuve ; aucune homologie supplémentaire
n'est inventée. [Preuve ciblée](automation-capacity-generality-evidence-20261005.json).

Le profilage portable localise la recherche barycentrique exhaustive comme
coût principal sur les entrées conservées : 5 242 triangles source et
11 922 cellules de guide. L'instrumentation consomme elle-même le budget et
ses temps cumulés se recouvrent ; elle n'est pas un benchmark de production.
Les sections du torse restent incomplètes au budget inchangé de 15 secondes.
[Observations](automation-material-section-profile-evidence-20261005.json).

Les commits `af78094` et `6545a41` construisent un index par intervalles
conservateurs des opérations existantes, y compris les coefficients entiers
exactement convertibles. Le rejeu réel garde typiquement environ 9 269 cellules
sur 11 922 et progresse moins vite : 568/575/572 faces terminées pour
poitrine/taille/hanches, puis refus au budget. **L'accélération est non
qualifiée et plus lente dans cet essai.** Le parcours exhaustif est rétabli
comme défaut de production ; l'index reste un opt-in strict du noyau
expérimental, avec backend indiqué dans le résultat et sans activation publique.
Les sources, tolérances et critères d'admission sont conservés.

Le candidat final de cette unité passe **79 tests ciblés sous chacun des
deux Python** (2,364 s et 2,670 s), avec revue indépendante sans défaut P2 ou
supérieur confirmé. Ces tests couvrent les mesures, refus, provenance et
compatibilité du parcours par défaut ; ils ne qualifient pas une capacité
complète du torse ni le vêtement. La suite complète n'est pas rejouée sur ce
candidat. [Contrat et essai négatif](cage-material-lookup.md),
[preuve du défaut de production conservé](automation-cage-production-default-evidence-20261005.json).

Le contrôle live reste bloqué sur `dev.2026100503` ; l'utilisateur confirme
ne pas avoir redémarré Codex. La copie installée reste `dev.2026100504`, issue
du candidat intégré précédent. **Aucun nouveau build, installation, appel
Blender ou release GitHub n'est effectué pour cette unité.**
[Observation du runtime](automation-generality-runtime-evidence-20261005.json).

La reprise native attend toujours le redémarrage, la vérification du serveur et
du pipeline, puis la préparation de l'opération exacte et son autorisation.
La capacité ouverte du torse, le col et le placement des épaules restent à
traiter. Le vêtement complet, l'enfilage, le drapé, le fitting, les mouvements,
les revues visuelles et la livraison finale restent non qualifiés. Aucun
nouveau patron à approuver n'est produit par ce diagnostic.

### 2026-10-05 — Rechargement vérifié, régression de reprise et correctif local

Après le redémarrage confirmé par l'utilisateur, `studio_doctor` retourne
`PASS` sur `dev.2026100504` (52 schemas) et `studio_check_pipeline` est admis.
La requête publique V4 est réellement exécutée : compilation `READY_TO_PLAN`,
15 textiles et une boucle dans le dossier, mais `FIT_PREFLIGHT_INCOMPLETE`.
Les quatre propositions bras/poignets sont retrouvées, non admises. Les sections
poitrine/taille/hanches épuisent leur budget inchangé et le col manque encore
d'une ligne homologuée complète. Ces résultats ne qualifient ni le placement
ni la capacité du torse. Le résultat complet et la requête sont conservés dans
`program-restart-verification-v1` sur G:.

La restauration exacte du checkpoint `pre-028b75a4767b4e28b491a65da4bc85c0.blend`
est préparée par le dispatcher et autorisée par l'utilisateur. L'appel natif
ouvre le checkpoint et sauvegarde `working-recovered-9f447501a5ab421fb0ce7931973301ce.blend`,
puis refuse le second contrôle du reçu sur `.a3d/blender/session.json`.
**Sauvegarde partielle, restauration canonique non terminée.** L'erreur,
la copie partielle, le candidat refusé et son reçu sont préservés ; aucun second
envoi Blender n'est effectué.

Le commit `074850e` corrige le mécanisme générique de reprise. Les nouvelles
sessions et scènes de travail récupérées sont archivées à leur origine native.
Pour les anciennes références live, seule la restauration accepte des octets
historiques authentifiés par leur SHA intégral et leur reçu canonique. La
session réelle est reconstituée en mémoire en ne changeant que `working` :
687 octets, SHA identique à `aba7b83c385c649d4e810c44b43aa9a0e1be6a5807baf6a7b3fc0f91947f3bef`.
Les `.blend`, checkpoints et autres artefacts ne sont pas reconstruits. Le
contrôle ordinaire de rejeu reste strict ; aucun historique n'est réécrit.

**71 tests ciblés PASS sous Python 3.11 et 3.13**, puis authentification réelle
en lecture seule du descripteur historique sous les deux Python, SQLite
inchangée. La revue indépendante découvre un P2 de relecture du reçu ; il est
corrigé en hashant et décodant le même buffer, avec deux tests de remplacement.
Aucun défaut P2 ou supérieur ne reste confirmé dans le code revu.
[Contrat de reprise](run-recovery.md),
[preuve ciblée et refus natif](automation-session-recovery-evidence-20261005.json).

L'export Git immuable `074850e2a5bcf5176f4ea935fade3fd1399b2e86` passe ensuite
**1 635 tests en 210,694 s, aucun SKIP, et 14 contrats**. Le build vérifie
632 fichiers source distribués exacts ; la préparation adapte seulement les
métadonnées de version et les chemins natifs déclarés. Un premier comparateur
du stage refuse l'ordre JSON de TEMP/TMP ; ce témoin est conservé et le
comparateur corrigé est rejoué dans un dossier neuf, sans changement du plugin
validé. Le gestionnaire natif installe `dev.2026100505` ; ses 633 fichiers sont
comparés au stage et tous les anciens stages G: restent conservés. Les helpers
de validation, stage et vérification sont génériques, à arguments explicites.
Aucune confiance des hooks n'est scriptée, aucune release finale n'est publiée.
[Preuves intégrées et installation](automation-session-recovery-installation-evidence-20261005.json).

Le contrôle suivant utilise encore le cache remplacé `dev.2026100504` : un
nouveau redémarrage de Codex est requis pour charger le correctif. L'entrée de
reprise est : vérifier `dev.2026100505` et le pipeline, préparer de nouveau
`restore_checkpoint` pour le même run/tentative, obtenir son autorisation exacte
puis vérifier le reçu natif terminé. Le nouveau run de placement devra ensuite
porter les identités actuelles du code et des entrées. Le vêtement reste
RECONSTRUCTING ; aucun nouveau patron à approuver n'est produit. Les
correspondances de mesure, le placement et la revue artistique restent à
examiner ; construction complète, drapé, fitting et mouvement restent ouverts.

### 5 octobre — chemins Windows des archives historiques

Le redémarrage confirme cette fois `dev.2026100505` et son pipeline admis.
L'utilisateur autorise la restauration corrigée préparée. Son exécution native
échoue à la création d'une archive de scène de travail : chemin de 290
caractères, parent de 168 et nom de fichier de 121. Ce refus se produit avant
ouverture du checkpoint ; les archives exactes de session et d'inventaire
déjà présentes sont conservées. La restauration n'est pas déclarée terminée.

L'adaptateur Windows est appliqué après les validations de confinement, aux
accès fichiers seulement. Il répète les contrôles de liens et jonctions avec
les chemins étendus. Les lecteurs des runs et des preuves natives utilisent
la même adaptation pour les archives ; leurs modules sont maintenant inclus
dans l'empreinte commune du code. Les chemins relatifs des reçus et les chaînes
des sessions restent identiques. Une modification de code invalide le rejeu
sans retirer l'accès au checkpoint historique authentifié.

**78 tests ciblés PASS sous Python 3.11 et 3.13**, en 10,758 et 14,066 s. Les
six nouveaux scénarios Windows couvrent des sources réellement au-delà de
260 caractères, archivage et lecteurs, reconstruction exacte de session,
idempotence, UNC, préfixe existant, archives divergentes et refus de jonctions.
Le changement du code commun a sa régression d'invalidation. La revue
indépendante ne relève plus de blocage confirmé après renforcement de la
fixture longue. Le descripteur réel est vérifié en lecture seule, sans toucher
SQLite ni appeler Blender. Les premiers essais de tests restent conservés,
dont un lancement sandbox bloqué sur `Path.resolve` ; leurs comptes ne sont
pas additionnés à la suite finale.
[Preuve ciblée et échec natif](automation-windows-archive-evidence-20261005.json).

Le commit de code immuable `b378b60510a50a3b55943551238db1a659fa99ac` passe
**1 642 tests, aucun SKIP, et 14 contrats**, sources inchangées après les
contrôles. Le build local vérifie 634 fichiers source distribués ; le stage
et la copie installée `dev.2026100506` contiennent 635 fichiers exacts. Les
stages antérieurs G: restent préservés. Installation par le gestionnaire
natif, sans confiance de hooks scriptée ni publication finale.
[Preuves intégrées et installation](automation-windows-archive-installation-evidence-20261005.json).

Le contrôle connecté utilise encore le chemin remplacé de `dev.2026100505`.
La prochaine reprise vérifie 0506 et le pipeline après rechargement, prépare
une nouvelle restauration exacte et attend son autorisation, puis vérifie
son événement natif terminé. Le vêtement reste RECONSTRUCTING. Aucun nouveau
patron à revoir n'a été produit ; les correspondances de mesure et les
prochains candidats visuels restent à examiner. Placement, inventaire complet,
enfilage, matière, drapé, fitting, mouvements et revue artistique restent ouverts.
