# Historique

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
