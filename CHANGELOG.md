# Historique

## 0.7.0-rc.2 — 2026-10-03, stature codée et repères de surface

- Préparation systématique du corps cible dès l'ajout d'un mannequin pour un
  vêtement : mensurations prévues, variante séparée, mesures et revue.
- Calcul déterministe de stature en cm avec conservation du plan des pieds,
  de la topologie et de l'original, transformation des repères et nouveau
  profil mesuré. Les variantes à 180 cm sont vérifiées dans Blender et relues.
- Guide du haut du torse utilisant la peau mesurée aux épaules, distincte des
  centres articulaires. Refus d'un profil, cadre ou pose modifié, d'une
  triangulation incomplète, mal orientée ou d'un corps ouvert. Sections réelles
  du torse et bords nommés de patrons conservés.
- Limites : réglage indépendant de poitrine/taille/hanches non implémenté,
  contacts des quatre panneaux de torse encore refusés, Cloth et fitting
  complets des 15 pièces non qualifiés. Les mesures des variantes ne prouvent
  ni la compatibilité de coupe ni l'enfilage. Les PASS des coupons ne sont
  pas transférés. Aucune nouvelle installation Codex revendiquée.

## 0.7.0-rc.1 — 2026-10-03, préversion textile

- Catalogue hors ligne de deux bases réalistes CC0 de Dan Ulrich, import et
  sélection explicites, adaptateurs anatomiques mesurés et rig préparatoire.
- Planificateur séparant groupes cousus, couches spatiales, fermetures,
  attaches amovibles et contacts libres, avec provenance et refus explicites.
- Guides sémantiques du torse, des membres et d’une ceinture source unique ;
  patrons et métriques conservés. Corrections rigides bornées, dont mouvements
  coordonnés évalués atomiquement, sans assouplir les seuils.
- Simulation sur coupon couplé, contrôle de convergence et conservation des
  budgets incomplets ; réponses MCP compactes liées aux reçus complets et
  empreintes des modules chargés.
- Documentation réorganisée issue de la PR 21 intégrée dans cette branche.
- Limites : fitting complet non qualifié, intersections du haut du torse encore
  présentes, guides du col/devant intérieur/capuche/empiècements et orchestration
  complète à terminer. Le rig est préparatoire, sans contrôles indépendants de
  mensurations. Les PASS des coupons ne valent pas acceptation du vêtement.
- Cette préversion GitHub est publiée depuis la branche isolée ; aucune
  nouvelle installation Codex ni qualification artistique n’est revendiquée.
  [Contrat et limites](references/garment-automation.md).

## Notes historiques du correctif 0.6.9

Ces notes conservent l’état au moment de leurs essais, avant publication
de 0.6.9. Elles ne décrivent pas le statut de publication actuel.

- Correctif local 0.6.9 : essai explicite `single_panel` pour une pièce source
  unique sans couture permanente, avec provenance liée aux empreintes et
  fermeture/consolidation sans soudure ni qualification physique implicite.
- Préparation des raccords permanents/détachables partageant un bord source :
  subdivisions propagées à tous les partenaires ; les doubles coutures
  permanentes et cycles de correspondance incohérents restent refusés.
- Crans centraux des coutures inversées sur un même panneau : appariement sur
  les deux bords pour le point fixe exact 0.5, conformément à la planche.
  Les crans ambigus restent à clarifier. Les patrons approuvés restent intacts.
- Validation du correctif : 148 tests ciblés, 15 contrats JSON et audit des
  entrées réelles des 15 panneaux. Nouvelle préparation et simulation Blender
  avec le correctif encore à exécuter ; aucune publication GitHub effectuée.

- Consignes de reprise après refus : distinction entre limite du logiciel,
  erreur de préparation et pièces manquantes. Choix explicite de l'utilisateur
  entre technique approuvée et contrat supporté ; proposition de correction
  ou de préparation ciblée conservant le découpage. Les raccords permanents et
  détachables partageant un bord doivent être diagnostiqués avant toute
  attribution d'erreur aux patrons. [Protocole](references/preparation-recovery.md).

## 0.6.8 — 2026-10-03

- Contrôle de complétude des pièces Blender par identité source, bilans
  local/global et admissions des jalons globaux. Inspection des candidats
  non READY, rapports structurés et revue près des images. Demande explicite
  d'autorisation avant l'exécution de code Blender. Catalogue des templates
  ComfyUI conservé comme référence. Vérification native du vêtement séparée.

### Documentation incluse dans 0.6.8

- Correction de la complétude Blender : identités source et multiplicités
  par composant, bilans local/global, absences/doublons, visibilité distincte
  de présence et de qualification. L'inspection inclut les candidats non READY
  portant seulement a3d_source_component_id. Pages de revue près des images,
  cartes source conservées au gel, admissions des jalons globaux et invalidation
  des preuves sur changement des fichiers liés.
  [Protocole et limites](references/piece-completeness.md). Tests automatisés
  avec adaptateur Blender simulé ; exécution native et installation à vérifier.

- Bogue de complétude des pièces Blender enregistré dans
  [le rapport du 3 octobre](BUG-2026-10-03-completude-pieces-blender.md) et
  dans VALIDATION.md : résultat local du manteau 10/10, couverture textile
  globale observée 10/15. La correction dans les sources est documentée
  ci-dessus ; la qualification native reste à faire.

- Avant `execute_blender_code` et sa variante CLI, les skills demandent
  explicitement l'autorisation de l'utilisateur et attendent sa réponse.
  `studio_blender_operation` rappelle cette étape dans le code préparé retourné
  (champ `next`). Les permissions MCP et les contrôles d'admission restent actifs.

- Catalogue des templates ComfyUI SD1.5 image-to-image et Hunyuan multivue :
  usages, entrées/sorties, paramètres, exemples et procédure de réutilisation.
  README, guide de démarrage, références et skills Comfy reliés au catalogue.
  Graphes et registre existants conservés ; compatibilité native et qualité
  des résultats à qualifier sur l'installation cible.

## 0.6.7 — 2026-10-03, installation locale sans publication

- Version locale regroupant la préparation, l'assemblage et les renforcements
  ci-dessous, installable par le gestionnaire natif de Codex. Les anciens stages
  sont conservés ; aucune publication ni migration des projets consommateurs.

- [Renforcements après l'étude OpenSew](references/opensew-improvements.md) :
  métrique commune par face à chaque frame Cloth évaluée, contacts précis et
  mouvement discrètement échantillonné, enfilage sourcé et DAG des couches.
  Contrat de validation version 2, repos et appuis exécutés tracés, contrôles
  statiques d'enfilage avant/après drapé et références revérifiées au gel.
  Coupons ciblés conservés sans promotion des anciens PASS ni qualification
  du vêtement réel.
- Sections corporelles partitionnées par boucle et sélectionnées par l'axe
  sourcé ; une coupe parasite de jambe ne devient plus un faux défaut de
  passage au poignet. Diagnostics distincts des faces du tissu et du collider.
- Raffinement local borné des triangles intérieurs, contours et crans fixes ;
  cible d'angle conservée et reliquats explicitement refusés. Coupons natifs
  supplémentaires pour mesurer l'effet des paramètres de flexion.
- Courbure simple évaluée par le modificateur natif Blender `Simple Deform →
  Bend`, avec paramètres sourcés et correspondances conservées après remeshing.
  Aucun Garment Tool requis ; aucun calcul de Bend réimplémenté. Les mauvais
  repères restent refusés et la préforme ne remplace pas le repos physique.
- Entrée native `prepare_pattern_assembly` : audit des sources et crans, maillage
  triangulaire à densité graduée, préforme sourcée et mesures localisées avant
  Cloth. Rapports, correspondances, vues de contrôle et master Blender produits
  par le plugin ; transmission au montage sans réinitialiser le placement.
- Préformes `arc_sections` : mise en volume des panneaux par sections 3D
  paramétrées en longueur d'arc réelle, reliées aux UV métriques source, avec
  repères, budgets de déplacement et contrôles de déformation conservés.
- Flexion mesurée séparément de l'étirement : distributions globales et par
  panneau des dièdres entre faces adjacentes orientées, comparées au plan
  source. Les plis retournés ne sont pas masqués ; interfaces et faces
  dégénérées sont exclues. Aucun seuil d'acceptation physique n'en est déduit.
- Masse surfacique et aire tributaires mesurées, distinction explicite avec la
  masse scalaire par sommet du Cloth natif. Les contacts profonds, appuis
  contradictoires et données périmées conservent un refus de préparation.
- Parcours natif reprenable : préforme liée aux patrons, Cloth court avec
  retrait progressif des appuis temporaires, fermeture bornée unique,
  consolidation permanente, détente continue puis drapé sur le corps.
- Correspondances par IDs et paramètres d'arc réutilisées ; préformes par cadres
  sourcés ou cages UV/3D. Les tangentes spatiales restent diagnostiques après
  vérification du sens topologique des coutures.
- Repos continu 3D et métriques 2D par face, sans FlatRest moyennée ni ressorts
  après consolidation. Contrôle des cohortes transitives, attaches fixes,
  orientations, non-manifold et recouvrements avant union.
- Migration additive des reçus existants, dépréciation de l'empilement des
  préparations, gel continu soumis à un fitting courant qualifié.
- Suite finale : 355 tests Python et 15 contrôles de contrats ; cinq préparations courbes
  natives `READY`, quatre refus attendus et quatre chaînes d'assemblage de
  régression réussies. La préparation complète de la copie réelle conserve
  447 fichiers source inchangés, mais reste refusée pour qualité et contacts,
  sans Cloth ni fitting qualifié ; voir VALIDATION.md.

## 0.6.6 - 2026-10-03

- La pose commune partage l'influence de chaque cadre anatomique entre les
  partenaires d'une couture permanente. Un appui fixe s'étend à ses seuls
  partenaires pendant cette préparation ; les poids source restent inchangés.
  Les fermetures et éléments amovibles ne sont ni contraints ainsi ni soudés.
- La relaxation conserve une limite propre à chaque paire de couture, calculée
  depuis son écart initial et le seuil de consolidation existant. Un écart élevé
  ailleurs ne permet plus de rouvrir une couture déjà rapprochée. Les résidus des
  cadres et les groupes d'appui sont rapportés sans cacher une contrainte fixe.
- Régression reproduite avant correction et vérifiée dans Blender : couture
  fixée ouverte de 2 mm auparavant, préservée après correction. Sur une copie
  réelle inchangée, écart maximal de pose réduit de 4,90394 à 1,65213 mm ; aucun
  fitting porté, contact profond résolu ou succès visuel n'est déduit de ce test.
- 230 tests Python, tests natifs de pose/appuis et chaîne synthétique Cloth avec
  consolidation. Le cas historique reste lu sans modification ; sa fusion à
  65,9 mm n'est pas adoptée et la limite actuelle de 1,5 mm n'est pas relevée.

## 0.6.5 — 2026-10-02

- Diagnostic d'enfilage explicite pour un corps seul : enveloppe, collisions,
  épaisseurs, pose et mesures homologues manquantes ; aucune déclaration de pose
  inférée de la seule présence d'un corps identifié.
- `prepare_fitting_envelope` produit un auxiliaire géométrique fermé depuis le
  reçu natif d'un corps évalué, avec régions explicites, partition par os,
  padding/voxel bornés, normales, couverture et épaisseurs vérifiés. Le corps
  cible et la scène live sont conservés ; la silhouette anatomique reste à revoir.
- `prepare_fitting_pose` mesure les cadres depuis les bords source nommés et
  les os évalués. Le champ continu respecte les pins fixes et les seuils existants,
  avec relaxation structurelle facultative bornée. L'artefact est lié au mesh,
  à sa map et au corps exact, puis appliqué uniquement dans un stage checkpointé.
- Profils de rigidité partagés et renforts par bord 2D dans chaque phase : groupes
  natifs structural/shear/bending, maxima et poids réellement exécutés, remappage
  local source, mutations et coefficients tronqués refusés. Recettes uniformes
  compatibles ; aucune anisotropie chaîne/trame promise.
- Documentation du rôle du board (intentions/hypothèses) et de Blender
  (calibration et qualification), sans réapprobation du découpage inchangé.
- Tests natifs et MCP officiel isolé ; les originaux consommateur sont préservés.
  Le champ R21 passe ses contrôles structurels, mais son admission physique avec
  l'enveloppe révèle un contact profond au haut du buste. Aucun fitting local/full
  consommateur, drapé final ou résultat Unreal n'est déclaré réussi.

## 0.6.4 — 2026-10-02

- Reprise vide via `read_homefile(use_empty=True, use_factory_startup=True)` :
  préférences, add-on officiel, timer persistant et connexion MCP conservés.
  Le garde du MCP refusait `read_factory_settings` en 0.6.3.
- Journal natif créé avant le changement de scène, avec identités source,
  témoin et archive de session ; rollback automatique ou
  `recover_clean_construction` si sa récupération a échoué. Aucun pending fictif.
- `inspect_body_source` évalue les seuls meshes et dépendances déclarés dans
  une scène temporaire. `prepare_body_reference` exporte leur pose figée avec
  provenance, plages de sommets, dimensions et repères d'os mesurés.
  Dépendances implicites, drivers à contexte arbitraire et géométrie de
  construction refusés ; scène courante et état du projet inchangés.
- `introduce_fitting_context` conserve les objets déjà présents dont les
  identités sont vérifiées et importe uniquement les objets manquants.
  Corps et collider peuvent ainsi provenir de sources exactes distinctes.
- Qualification interactive isolée avec le garde officiel actif, erreurs
  avant/après changement de scène, rollback échoué puis récupération native,
  source/session/DB conservés et nouvelles requêtes MCP après rechargement.
- Référence R21 sélectionnée : 28 meshes, rig et deux contrôles, pose évaluée
  à l'image 1, hauteur 179,9932 cm. Géométrie mondiale et repères du rig identiques
  à l'évaluation du fichier complet ; aucune ancienne robe importée.
  Collider auxiliaire, repères homologues et fitting restent à qualifier.

## 0.6.3 — 2026-10-02

- L'inspection de fit et la proposition de capacité retournent leurs mesures
  malgré le refus géométrique, sans mutation ni relâchement des identités.
- `start_clean_construction` conserve un témoin binaire et l'ancien session,
  puis crée une scène vide versionnée avec un nouvel ID de construction.
  Les approbations de coupe exactes restent en place ; aucun PASS n'est importé.
- `introduce_fitting_context` importe seulement les objets déclarés et liés au
  témoin après un full libre courant, sans déplacer le vêtement ou le mannequin.
- `fitting_placement` applique des cadres rigides par groupes source disjoints
  avec indices/repères validés et corps cible identifié, sans scale/projection.
  Ambiguïtés, proxy, pins fixes déplacés, budgets et précontrôles sont des refus.
- Contact profond (> 0,5 cm) refusé avant projection ; petites récupérations
  restent bornées et soumises aux gates initiaux inchangés.
- Reprise réelle depuis patrons dans une scène vide : nouveau local/full PASS,
  coordonnées exactement identiques au témoin. Proxy réintroduit séparément :
  contact refusé et capacité/enfilage NOT_QUALIFIED ; aucun fitting réel exécuté.

## 0.6.2 — 2026-10-02

- L'inspection de placement mesure les candidats refusés pour qualité,
  orientation ou contact sans accorder de PASS physique ni muter scène/état.
  Identité/source/map, rest, topologie et pins restent des contrôles stricts.
- `interface_preparation` prépare des tangentes dans un voisinage borné des
  coutures permanentes source ; références et poids fixes sont conservés.
  Les sommets partagés sont traités conjointement ; mêmes contrôles finaux.
- `panel_mount` rapproche un groupe explicite de panneaux sur les seules
  coutures source sélectionnées, avec extérieur fixe, budget, réserve de
  déformation et relaxation finale. Aucune soudure ou qualification implicite.
- Copie réelle : quatre tangentes corrigées ; préparation des huit panneaux
  de manches sans déplacement du torse ; local/full libre des 17 panneaux PASS
  à 18 images. Les premiers refus de déplacement et de qualité sont conservés.
  Limites 30 cm / étirement 0,8–1,25 / couture 0,5 cm inchangées.
- Le fitting exige un full actuel et une recette séparée sans options de montage.
  Documentation et tests de budgets, source, références et inspection non mutante.

## 0.6.1 — 2026-10-02

- `apply_sewn_result` transfère les coordonnées cm d'un PASS local libre vers
  une copie native, avec vérification package/recette/binding/indices, rest,
  limites source, topologie, pins et coutures conservés. Résultats 0.6.0 admis
  avec leur mapping implicite vérifié ; nouveau reçu PARTIAL_ASSEMBLY.
- `simulate_sewn(purpose=assembly)` évalue le composant complet sans collider
  avec qualification ASSEMBLY_PHYSICS_ONLY. Un nouveau FAIL local actuel bloque
  la reprise d'un ancien PASS ; freeze exige le fitting distinct.
- `prepare_sewn_stage` reprend les coordonnées actuelles pour assembly ou
  fitting. L'entrée fitting exige full assembly PASS lié au mesh/map/recette,
  colliders identifiés et mêmes contrôles. Réparation optionnelle des contacts
  initialement pénétrants, avec budget déclaré, pins fixes et requalification.
- Le prépositionnement peut garder les références à leurs positions cousues.
  Refus de placement conservés avec diagnostic de transition et checkpoint ;
  aucune reconstruction à plat ou modification automatique de coupe/corps.
- Parcours complet et refus vérifiés dans Blender sur fixture synthétique.
  Transfert du cas réel PASS (5 455 sommets, 1 194 inchangés) ; full réel et
  prépositionnements supplémentaires refusés par les contrôles existants.
  Aucun PASS d'assemblage complet/fitting du vêtement réel n'est revendiqué.

## 0.6.0 — 2026-10-02

- Prépositionnement expérimental opt-in via `experimental_prefit` dans la recette
  `garment`/rebuild : coutures permanentes source, références et bords fixes
  explicites, solveur géométrique local/global et fractions bornées. Les mêmes
  contrôles natifs qualifient le placement initial et chaque candidat. Le reçu
  expose les mouvements et écarts ; aucune soudure ni qualification Cloth.
- Raffinement optionnel `mesh.quality_refinement`, borné en passes et sommets,
  conservant les ancrages du contour et la coupe ; refus si cible inaccessible.
- `final_quality` et `final_checks` conservés lors d'un refus final de qualité,
  avec toutes les violations mesurables et les contrôles contacts/coutures.
- Fixtures natives : placement amélioré sans mutation du package/rest,
  repères contradictoires refusés, budgets de raffinement et récupération des
  diagnostics. Cas réel isolé : contrôle initial PASS, Cloth toujours FAIL.
  Fonction expérimentale livrée pour essai, sans changement des seuils physiques.

## 0.5.9 — 2026-10-02

- Les mesures Cloth séparent excursion depuis le départ de phase et incrément
  entre images réellement évaluées. Chaque maximum expose index local/source,
  pièce, positions, delta, UV, bords et poids de maintien ; l'échec expose aussi
  les maxima par pièce. Pas de vitesse de sous-pas ni classification d'instabilité.
- L'image qui dépasse max_displacement_cm est enregistrée avant le même refus.
  Aucun budget, durée, profil, couture ou règle de qualification n'est assoupli.
- inspect_sewing_failure expose motion et l'historique ; les preuves anciennes
  donnent une excursion calculée en lecture seule et un incrément NOT_RECORDED,
  sans réécriture ni soustraction trompeuse des maxima scalaires.
- Documentation et instructions de montage : choisir une hypothèse mesurée et
  bornée, conserver les contours et seuils, requalifier après retrait des attaches.
  mount/drape existent déjà ; aucun mécanisme ou outil MCP redondant ajouté.

## 0.5.8 — 2026-10-01

- Nouveau contrat fitting-plan et opérations gardées en lecture seule
  inspect_garment_fit / propose_pattern_adjustment : identité/pose corps et
  enveloppe, sections fermées excluant les bras séparés, chemins homologues
  à la ligne de couture, aisance, reprises/chevauchements et incertitude.
- Mesure manquante, proxy ou repère supposé : NOT_QUALIFIED. Déficit minimum
  démontré : INCOMPATIBLE et full bloqué si la recette référence cette fiche.
  Cible de style distinguée. Marge de coupe jamais comptée comme aisance.
- Propositions limitées aux allocations chiffrées de capacité et dépendances
  des coutures ; aucun contour/courbe/droit-fil/package édité automatiquement.
- fitting_tacks tient les paires de closure source sur le seul mesh local
  jetable, avec provenance, durée et force native commune déclarées. Les gaps
  sont contrôlés, la qualification demeure CONSTRUCTION_FITTING_ONLY ;
  full/freeze refusent les tacks. Aucun retypage ni soudure de closure/detachable.
- Fiche, corps et recette lient les qualifications ; preuve périmée refusée.
  Actualisation du binding de trial : refaire local avant full après mise à jour.
- Fixtures Blender natives et régressions testées. Aucun PASS de fitting ou
  de montage complet du vêtement consommateur revendiqué.

## 0.5.7 — 2026-10-01

- Les probes ratés conservent un diagnostic natif dans un répertoire unique
  avant suppression des coupons, ainsi qu'une projection SVG avec titre explicite.
  Cas, profil, durée configurée et évaluée, positions, pins, qualité, coutures,
  contexte et paramètres Cloth observés sont conservés.
- `inspect_sewing_failure` vérifie les preuves et previews du probe, puis expose
  le stade backend_probe, probe FAIL, vêtement NOT_EXECUTED et le domaine
  géométrique synthetic_coupon. Les empreintes package/mapping/placement lient
  la demande parente ; les indices du coupon ne deviennent pas ceux du vêtement.
- Les échecs de contrôles après évaluation conservent aussi le dernier état
  évalué. Les probes restent à 12/24 images avec leurs seuils existants.
- La projection de qualification locale devient FAIL après un nouvel échec,
  empêchant un ancien PASS de lancer full ; ses preuves historiques restent intactes.
  Restauration obligatoire, patrons et validations humaines conservés.
- Fixture native : échec réel de couture de coupon avant essai du vêtement,
  24 images contre recette 48, preuve intacte après restauration et refus full.
  Aucun défaut du solveur ni réparation du vêtement réel établi.

## 0.5.6 — 2026-10-01

- Diagnostic conservé avant de relancer un rejet géométrique de `garment`,
  notamment orientation, déformation du maillage dérivé et pénétration initiale.
  Répertoire unique, SHA, package/source/recette/checkpoint liés, aucun reçu accepté.
- Orientation : couture, pièces/bords source, segments successifs, indices,
  UV repos et positions natives, cosinus local et seuil -0,5 inchangé. Les cordes
  entre extrémités sont des mesures de contexte, sans décider d'un faux positif.
- Contact : pièce/sommet/bords/support, collider/face/normale, profondeur mesurée
  et seuil conservés. Test signé au sommet, pas une intersection exhaustive.
- `inspect_garment_failure` lit le diagnostic historique en lecture seule,
  pendant le pending et après restauration ; aucune mutation ni libération d'échec.
- Fixture Blender isolée : rejets orientation/qualité/contact, source/package/
  mesh antérieur/reçu/board conservés, restauration obligatoire et diagnostics intacts.
  Aucun défaut Cloth ni réparation de la robe réelle établi.

## 0.5.5 — 2026-10-01

- Ajout de `inspect_sewing_placement(component_id, recipe_path)` en lecture seule
  dans la copie Blender attendue, avant Cloth ; identité package, recette, rest,
  mesh, supports et collider vérifiés sans changer la scène ou les décisions.
- Mesures par paire de couture : panneau, bord source, longueur d'arc,
  coordonnées, poids de maintien et premier croisement du segment par collider.
  Régions spatiales et orientations des faces, sans déduction anatomique.
- `placement.json` conservé avant chaque tentative native et lié par SHA au
  résultat ou au diagnostic d'échec. Aucun avertissement n'accorde un PASS local.
- Documentation du montage cylindrique existant sur bras posé et de ses limites
  pour une manche effilée. Patrons, seuils, circuit local/full et gates inchangés.
- Fixture native : deux panneaux de manche effilés et coupons d'emmanchure
  autour d'un bras incliné ; aucune robe réelle réparée ou validée revendiquée.

## 0.5.4 — 2026-10-01

- `frame_view(component_id, object_name)` cadre un mesh visible appartenant au
  composant/package de la copie de travail ; sélection, orientation et mode de
  vue conservés. Refus des scènes étrangères, archives, objets masqués, mode
  édition, vues caméra/quad et verrous. Aucun checkpoint, sortie ou validation
  implicite. Le refus de navigation directe indique désormais ce parcours.
- Un échec de Cloth après évaluation conserve les dernières positions, triangles,
  mapping vers le mesh complet, recette et contexte exécutés, arêtes et faces
  hors limites, écarts par couture et pénétrations localisées, avant nettoyage.
  Un SVG montre trois projections mesurées du résultat explicitement FAIL.
- `inspect_sewing_failure(component_id, attempt_dir)` vérifie et lit cette preuve
  après échec/restauration, sans supprimer le pending ni qualifier une simulation.
- Le sous-ensemble par panneaux remappe aussi les contours/bords et conserve les
  indices source et coutures omises. Il reste un ensemble de pièces entières,
  dont l'étendue est rapportée ; aucun nouveau découpage ou support automatique.

## 0.5.3 — 2026-10-01

- Reçus `garment` immuables sous `blender/garment-receipts/<component_id>/`, avec
  identité du composant, SHA du package et lien conservé dans l'objet Blender.
  Les opérations suivantes ne remplacent plus le reçu historique global.
- `verify_legacy_import` vérifie l'objet d'import dans un checkpoint guardé :
  hash du fichier, identité composant/package et topologie du package. Lecture
  de l'objet sans ouvrir sa scène, puis retrait des datablocks temporaires ;
  aucun checkpoint ni état d'opération en attente n'est créé par cette vérification.
- `legacy_checkpoint_receipt` permet une migration après perte du reçu unique.
  La nouvelle preuve décrit l'objet réellement observé ; elle ne transforme pas
  le reçu d'un autre composant en reçu d'import du mesh migré.
- Régression native avec trois imports réels 0.4.0, manteau densifié par un script
  guardé, conservation des voisins/rest/sources et refus des preuves invalides.
  Le code de reprise 0.5.2 reste compatible.

## 0.5.2 — 2026-10-01

- Chargement du dispatcher depuis l'installation explicitement demandée, avec
  remplacement des modules `a3d` et `blender` conservés dans l'interpréteur et
  nouvelle vérification de l'admission. Le résultat indique version et racine.
- Opération `resume` : checkpoint des modifications en mémoire, sans recharger
  la scène, changer le fichier de travail ni effacer la session ou une erreur.
- `garment(rebuild=true, migrate_legacy=true)` : reconnaissance limitée des
  panneaux 0.4.0 par identité, package, topologie, reçu et checkpoint. Archivage
  conservant leur géométrie avant création d'un nouveau maillage dérivé ; aucune
  attribution artificielle de rôle de simulation ou de correspondance de couture.
- Variante legacy densifiée : archivage explicite lié à l'empreinte courante et
  aux reçus des anciens scripts, avec vérification avant/après et conservation
  des formes de repos. L'ancien mesh reste non validé ; ses indices ne sont pas
  réutilisés dans le maillage natif dérivé.
- Tests de refus et essai natif de reprise d'une scène legacy modifiée, dans un
  processus Blender isolé ; validations du découpage et sources conservées.
- Placement cylindrique `mirror_u` explicite : sens d'enroulement inversé sans
  modifier les contours ou le rest 2D. L'option fait partie de l'empreinte de
  recette et invalide le maillage dérivé antérieur ; contrôles avant simulation
  conservés. Le défaut reste `false` pour les recettes existantes.

## 0.5.1 — 2026-10-01

- Procédure de mise à jour : terminer les opérations en cours et recharger Codex
  après remplacement du plugin pour éviter de conserver les chemins de l'ancienne
  copie installée.
- Diagnostic des hooks : distinguer configuration et confiance, exécution directe
  des scripts, puis exécution réelle dans l'application après rechargement.
- README et procédure de publication alignés sur ces contrôles. Aucun changement
  du code des hooks ou des opérations de production ; aucune attribution automatique
  de tous les codes 1 à un problème de cache.

## 0.5.0 — 2026-10-01

- Recette native pour le passage du board approuvé à une toile cousue : contours
  conservés, maillage de simulation indépendant, correspondance des coutures,
  placement contrôlé et reconstruction dérivée avec archivage de l’ancienne copie.
- Masse totale ou surfacique convertie en masse par sommet, plafond de couture
  fini et amortissement rapporté à la masse ; contrôle des paramètres exécutés.
- Mannequin auxiliaire identifié, forme de repos, pins, collection de collision,
  cache court et essais mesurés de gravité, couture et contact.
- Essai local avant chaque recette complète ; arrêt après deux échecs complets.
  Un réglage technique n’impose pas une nouvelle approbation du board inchangé.
- Consolidation des seules coutures permanentes. Fermetures, bords libres et
  pièces amovibles préservés ; absence de soudure par proximité.
- Version du serveur MCP et diagnostic alignés sur le manifeste réellement
  installé, y compris le profil Windows sans `plugin.json` à la racine.
- Tests natifs synthétiques et documentation du parcours. Aucun asset complet,
  fitting complexe ou export Unreal qualifié par ces tests.

## 0.4.0 — 2026-10-01

- Vue éclatée préparée pour Codex Image à partir des références originales,
  avec enregistrement de la sortie réelle et de sa provenance déclarée.
- Board : trois volets, nomenclature et libellés, caractéristiques par pièce,
  patrons issus des packages, contours de coupe et couture, plis, droit-fil,
  repères appariés et échelle commune.
- Mesures de proportions comparées aux références et nouvelle revue humaine
  obligatoire pour les boards incompatibles avec le contrat actuel.
- Correction de descriptions françaises dont l'encodage était détérioré.
- Première publication GitHub : documentation d'installation, licence MIT,
  politique de sécurité et CI. Les backends et les données machine restent externes.

## 0.3.0 — 2026-10-01

- Références originales réellement consommées par le template SD1.5.
- Preuves liées au candidat de reconstruction, assemblage, finition et livraison.
- Plan d'assemblage complet, reçu immuable et mode pour panneaux déjà présents.
- Blocage des mutations après erreur Blender et restauration conservant les fichiers.
- Contrôles de comportement, simulation et import moteur selon la destination.

## 0.2.0 — 2026-10-01

- Proposition de pipeline, validation par composant et dossier technique obligatoires.
- Board de construction approuvé avant reconstruction ; invalidation lorsque ses
  références, données ou packages changent.
- Contrôles dans le runtime, les opérations Blender et les hooks, en complément des skills.

## 0.1.0–0.1.3 — 2026-09-30 à 2026-10-01

- Socle local : SQLite, 11 skills, serveur MCP, packages et adaptateur Comfy officiel.
- Profil d'installation Windows et correction des hooks sous cmd et PowerShell.
- Connexions natives vérifiées séparément de la production d'assets.

Consulter [la validation](VALIDATION.md) pour la portée des essais ; une entrée
de cet historique ne constitue pas une qualification artistique ou de production.
