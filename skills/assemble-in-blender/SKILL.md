---
name: assemble-in-blender
description: Assembler dans une copie Blender des reconstructions 3D indépendantes ou des panneaux cousus, en conservant leurs articulations.
---

# assemble-in-blender

Suivre [la reprise après un refus](../../references/preparation-recovery.md).
Distinguer une limite du logiciel d'une erreur de préparation : pour une limite,
informer l'utilisateur et lui faire choisir entre conserver la technique
approuvée avec un parcours compatible et revenir au contrat supporté, avant
tout changement. Pour un défaut confirmé ou des pièces manquantes, proposer une
correction ciblée ou refaire les seuls patrons/dérivés concernés depuis les
sources approuvées, puis recontrôler raccords et complétude. Un bord partagé
entre couture permanente et attache détachable n'est pas automatiquement erroné.
Conserver le découpage approuvé et les autorisations d'exécution Blender.

Suivre [le contrôle de complétude](../../references/piece-completeness.md).
Avec chaque aperçu, présenter le résumé `piece_completeness.summary`, les
pièces manquantes et la portée locale/globale. Un manteau 10/10 peut rester
un vêtement 10/15 ; ne pas transformer ce résultat local en validation globale.
Ouvrir la page `piece_completeness.review` retournée pour voir le bilan près
des images, et distinguer présence, visibilité et qualification.

Avant chaque appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter l'opération préparée, le projet cible et ses effets attendus ; demander explicitement l'autorisation de l'utilisateur et attendre sa réponse affirmative. La préparation du code et les validations du pipeline ne valent pas autorisation d'exécution. Un refus ou une absence de réponse empêche l'appel. Si l'opération ou ses arguments changent, demander l'autorisation pour la nouvelle action. Respecter tout blocage de Codex ou du projet. Voir [le protocole Blender](../../references/blender.md).

## Parcours nominal PATTERN_SEWN

Commencer par [la préparation native](../../references/pattern-preparation.md)
avec `prepare_pattern_assembly(component_id, recipe_path, preparation_path)`
via `studio_blender_operation` et le MCP officiel. Examiner l'audit de coupe,
les extrema localisés de qualité/déformation, les appuis et les vues neutres et
wireframe. Un résultat `NEEDS_CORRECTION` ou `NEEDS_CLARIFICATION` reste un
candidat inspectable et n'autorise pas le montage. Une préparation `READY`
entre par `preposition` avec les références de recette/plan retournées : elle
conserve ses coordonnées, son repos et ses correspondances, sans revenir à
l'ancien placement. Ce statut n'exécute et ne qualifie aucun Cloth.

Suivre [l'assemblage générique reprenable](../../references/pattern-assembly.md).
Utiliser `transition_pattern_assembly(component_id, recipe_path, plan_path, stage)` :
`preposition`, `mount`, `close`, `consolidate`, `relax`, puis `drape`.
`migrate` conserve les anciens reçus sans transférer leur qualification. Les
patrons approuvés, les coutures typées et le mapping par longueur d'arc restent
la source. La préforme pilote uniquement le maillage dérivé. La fermeture est
une transition bornée unique ; la consolidation géométrique n'accepte ni Cloth,
ni fitting, ni apparence. Le repos continu est 3D et ses métriques source restent
2D par face. Ne pas fabriquer une FlatRest en moyennant plusieurs îlots.

Séparer les appuis temporary/drape/functional, retirer progressivement temporary
avant le drapé et conserver les conflits mesurés. Les tangentes 3D sont des
diagnostics de placement ; le sens des coutures est vérifié topologiquement.
Un contact profond impose une pose/enfilage explicite. Ne pas modifier le corps
ou augmenter une tolérance pour le dissimuler. Un squelette ajouré exige une
enveloppe auxiliaire sourcée et une revue visuelle liée à cette enveloppe.

Les paragraphes historiques ci-dessous servent à la reprise des reçus existants.
Ne pas empiler `experimental_prefit`, `interface_preparation`, `panel_mount`,
`fitting_placement`, `fitting_pose` et `contact_recovery` dans une nouvelle
recette nominale. Conserver leurs preuves et suivre la migration avant retrait.
L'acceptation finale et l'export restent soumis au fitting et au comportement.

## Reprise des parcours historiques

Pour une préparation de pose commune, suivre [les appuis de couture permanents](../../references/fitting-preparation.md).
Vérifier les résidus des cadres, les groupes fixes et les écarts par paire ; un
appui fixe peut empêcher la cible anatomique. Ne pas desserrer un seuil ni
modifier les pins pour masquer ce conflit. Le partage d'influence ne soude pas
les panneaux et un PASS de préparation ne qualifie ni Cloth ni les collisions.

Pour un corps cible choisi dans un .blend existant, suivre [la sélection native
et sa pose évaluée](../../references/body-source.md). Utiliser
inspect_body_source/prepare_body_reference via studio_blender_operation, avec
SHA, image, unités, meshes et dépendances explicites. Ne pas ouvrir le fichier
complet dans le Blender consommateur ni importer l'ancien vêtement. Le snapshot
ne crée pas de collider et ses points d'os ne valident pas les repères homologues.
Conserver le garde MCP et le journal de reprise ; recover_clean_construction
exige ROLLBACK_REQUIRED, jamais un pending inventé ou une réinitialisation des
préférences pour contourner le MCP.

Pour une reprise de construction explicitement demandée, suivre [la scène vide et le fitting distinct](../../references/clean-construction-fitting.md). start_clean_construction conserve le fichier courant comme témoin et ses reçus, refuse dirty/pending/identité périmée, puis ouvre une scène vide versionnée. Repartir du même package/board approuvé et obtenir de nouveaux local/full sans mannequin ; aucun ancien résultat n'est importé. Comparer les coordonnées au témoin avant d'affirmer une contamination cumulative. Après un full libre actuel, introduce_fitting_context importe uniquement le corps/enveloppe déclarés depuis le témoin exact, sans déplacer le vêtement. inspect_garment_fit mesure malgré un contact refusé mais conserve source/rest/pins/identités stricts ; proxy et repères supposés restent NOT_QUALIFIED. En cas de pose incompatible, fitting_placement exige un corps cible identifié et des cadres homologues validés par groupes disjoints, sans scale ni projection et avec pins/budgets/précontrôle inchangés. Ne jamais inventer ces repères depuis la seule hauteur du mannequin. contact_recovery est réservé aux pénétrations de 0,5 cm au plus : un contact profond exige pose/enfilage explicite et restauration native, sans seconde tentative aveugle. Aucun fitting PASS ne découle de la reprise propre.

Après un refus local d'orientation, suivre [la préparation native des interfaces](../../references/local-interfaces.md). inspect_sewing_placement doit retourner les mesures du candidat rejeté sans PASS ni mutation, tout en vérifiant source/map/rest/pins. Distinguer tangente locale et corde globale. Utiliser interface_preparation pour les seules interfaces et leurs voisinages déclarés, depuis la copie cousue. Si un refus Cloth mesuré provient encore de panneaux éloignés, panel_mount rapproche un groupe explicite sur ses seules coutures permanentes source avec extérieur fixe et réserve de déformation. Vérifier les receipts et le même précontrôle avant le nouveau local puis full purpose=assembly ; aucune élévation des seuils ni script de déplacement externe. Le solver de préparation ne qualifie pas Cloth. Retirer ces options dans la recette de fitting séparée. Conserver toute preuve FAIL et ne pas rejouer une hypothèse globale déjà rejetée.

Pour reprendre un PASS local sans collider, suivre [le montage par étapes](../../references/sewn-stages.md) : apply_sewn_result avec recette exacte, résultat immuable et SHA ; vérifier le reçu, les indices transférés et la copie. Ne pas repartir du placement initial, reconstituer les coordonnées par script ou fusionner les panneaux. Terminer les interfaces restantes avec prepare_sewn_stage(stage=assembly) sur la géométrie cousue actuelle ; chaque recette/placement modifié exige un nouveau local actuel. Full purpose=assembly vérifie tout le composant sans collider mais ne permet pas freeze. Après full assembly PASS, prepare_sewn_stage(stage=fitting) conserve ses coordonnées et introduit le corps identifié ; recontrôler contacts, qualité et mesures, puis local/full purpose=fitting. Les réparations contact_recovery sont bornées, respectent les pins fixes et ne donnent pas de PASS Cloth. Un refus réel d'emmanchure reste un refus : lire les tangentes et restaurer, sans relever le seuil. Conserver les closures réversibles, le col fixe et les composants amovibles indépendants. Ne pas faire réapprouver un board inchangé pour ces seules transitions techniques.

Après un arrêt de déplacement Cloth, suivre [les mesures natives de mouvement](../../references/cloth-motion.md) : lire motion et frames dans inspect_sewing_failure, identifier le sommet source/pièce, distinguer excursion depuis le départ et incrément entre images. Un FAIL de budget n'est pas seul une instabilité ou un déficit de coupe. Les anciens incréments absents restent NOT_RECORDED. Choisir une seule hypothèse mesurée/bornée de placement ou appui ; rebuild natif et précontrôle avant Cloth, sans relever les budgets ni balayer les profils. Les profils mount/drape existent déjà. Vérifier la stabilité après retrait de tout maintien temporaire avant production.

Pour PATTERN_SEWN, suivre [le fitting mesuré](../../references/measured-fitting.md) avant de varier la physique : préparer la fiche technique depuis le corps cible, le collider effectif et les repères homologues des patrons à la ligne de couture. Appeler inspect_garment_fit ; repères/capacité absents restent NOT_QUALIFIED. Distinguer déficit de coupe prouvé, signaux de placement, supports et physique non établie. Ne jamais déduire un manque d'aisance d'un échec Cloth seul. Les fitting_tacks natifs ne tiennent qu'une closure source dans l'essai local, avec force commune/durée explicites ; pas de retypage/soudure, pas de full/freeze tant qu'ils sont présents. Retirer ces attaches puis requalifier local sur la recette exacte. Une proposition d'ajustement alloue le déficit en cm, sans éditer de courbes : si nécessaire, préparer une variante native séparée, recontrôler coutures/embu/droit-fil et faire valider le board des différences avant production. Ne pas faire réapprouver une coupe inchangée ni imposer un formulaire utilisateur.

Après un échec de probe, suivre [le diagnostic des probes](../../references/probe-diagnostics.md) via `inspect_sewing_failure`. Distinguer backend_probe FAIL et vêtement NOT_EXECUTED ; les positions/pins/indices sont ceux des coupons synthétiques. Lire durée, profil et supports réels, restaurer puis corriger la recette séparément sans supprimer le probe ni relâcher ses seuils. Un ancien PASS local ne permet pas full après un nouveau FAIL.

Après un rejet géométrique de `garment` avant mapping/reçu, utiliser [le diagnostic de rejet](../../references/garment-rejections.md) via `inspect_garment_failure(component_id, attempt_dir)`. Lire la couture/les tangentes ou les contacts initiaux mesurés sans accepter le candidat. Distinguer tangente locale et corde globale ; aucun faux positif ou bug Cloth ne découle du rejet. L'inspection ne libère pas pending : restaurer avant toute nouvelle mutation.

Avant Cloth, appliquer [la revue mesurée de prépositionnement](../../references/sewing-placement.md) : appeler `inspect_sewing_placement`, examiner écarts, poids de maintien, trajets dans les colliders et orientations, puis un rendu autour du mannequin. Utiliser les placements flat/cylinder existants avec paramètres traçables avant toute extension. Ne pas confondre alignement et enfilage ni un avertissement de segment avec une impossibilité de draper. Garder le PASS local actuel comme condition du full.

Pour examiner les pixels d'un candidat, utiliser `frame_view` avec component_id
et object_name exact dans `studio_blender_operation`, puis capturer VIEW_3D.
Après un échec Cloth, lire `inspect_sewing_failure(component_id, attempt_dir)`
et son tracé mesuré avant de supprimer/rejouer quoi que ce soit. Cela ne valide
pas l'essai ; restaurer le checkpoint avant une nouvelle mutation. Voir le
[protocole de cadrage/diagnostic](../../references/viewport-diagnostics.md).

Avant de reprendre une session existante, suivre [le protocole de continuité](../../references/blender-continuity.md).
Demander un nouveau code exact au Studio actualisé : le résultat doit identifier
la version et la racine attendues. Utiliser `resume` avec des arguments vides pour
conserver en checkpoint les modifications non enregistrées de la scène de travail
connectée. Ne pas effacer `session.json`, relancer `prepare` ou provoquer un échec
pour obtenir une sauvegarde. Les panneaux 0.4.0 non acceptés passent uniquement par
`garment` avec `rebuild=true` et `migrate_legacy=true`, après les vérifications de
provenance ; ne jamais leur ajouter artificiellement un rôle ou un mapping.
Pour une variante densifiée, fournir l'empreinte récente d'`inspect` et les reçus
de scripts vérifiés selon le protocole. L'archivage n'est pas une acceptation de
ce mesh ; le nouveau mapping doit provenir des sources approuvées.
Si l'ancien reçu global appartient à un autre composant, utiliser d'abord
`verify_legacy_import` avec le package et un reçu guardé existant référençant un
checkpoint contenant les panneaux initiaux. Après lecture native vérifiée, ajouter
`legacy_checkpoint_receipt` à la migration. Ne pas renommer un reçu étranger ni
fabriquer un reçu d'import. Conserver le chemin/SHA de chaque nouveau reçu `garment`.

Lire [le protocole Blender](../../references/blender.md). Utiliser le MCP Blender officiel déjà connecté. Demander le code exact à `studio_blender_operation` puis le transmettre tel quel à l'outil Python Blender ; le dispatcher vérifie à nouveau les prérequis. `prepare` crée une copie sans écraser l'original. Vérifier la scène connectée. Après approbation humaine du board de découpage, `garment` construit les panneaux issus du package approuvé. Pour l'assemblage, faire approuver les relations critiques puis appeler `assemble`. Le mannequin de collision et la simulation restent un travail de scène explicite et traçable. Ne jamais substituer des tubes/surfaces procédurales à PATTERN_SEWN. Ne jamais souder des composants must_remain_separate. Inspecter les pixels avant toute conclusion.

Enregistrer et faire approuver assembly-plan, avec tous les composants, leurs sorties acceptées et les hashes du fichier de travail/checkpoint. Utiliser mode=existing pour les panneaux cousus déjà construits, mode=import pour les fichiers de parties. L’opération produit assembly-result nécessaire à REFINING. Après erreur, utiliser restore_checkpoint avant une nouvelle mutation. Voir les [contrôles des étapes](../../references/lifecycle-guards.md).

Pour PATTERN_SEWN, suivre [la recette native de toile](../../references/sewn-toile.md) après approbation du board : contours source conservés, maillage dérivé, mannequin auxiliaire vérifié, essais gravité/couture/contact puis sous-ensemble local, simulation complète bornée et consolidation des seules coutures permanentes. Préparer les données techniques pour l’utilisateur ; ne pas lui imposer un nouveau formulaire ni faire réapprouver un board inchangé pour ajuster la physique. Après deux échecs complets, diagnostiquer le petit cas et refaire l’essai local. Examiner les rendus avant toute conclusion artistique.

Si l'utilisateur demande de tester le prépositionnement expérimental, suivre
[son contrat borné](../../references/experimental-prefit.md) : copie de recette,
coutures permanentes et repères source explicites, `garment`/rebuild guardé,
inspection du reçu et des pixels, puis essai local. L'option est désactivée par
défaut. `PREPOSITIONED_NOT_SIMULATED` ne vaut ni fitting accepté ni PASS Cloth.
Conserver le contrôle dimensionnel et les règles local/full/freeze ; ne pas
substituer ce solveur à la validation du découpage ou modifier le corps pour passer.
