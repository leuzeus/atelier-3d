---
name: 3d-project
description: Orchestrer un projet de production 3D local reprenable à partir de références, avec Comfy MCP officiel et Blender MCP.
---

# 3d-project

Dès l'ajout de tout mannequin destiné à un vêtement, suivre
[la préparation du corps cible](../../references/garment-body-target.md),
qu'il provienne du catalogue, d'un import ou de la scène. Reprendre les
mensurations prévues dans le dossier, préparer une variante séparée si
nécessaire, mesurer ses proportions et les présenter pour revue avant le
fitting. Une stature seule ne qualifie pas les tours ni l'enfilage. Conserver
les cibles déjà approuvées ; ne pas réduire le corps pour masquer un échec.
La sélection de la base et les cibles relèvent de la décision humaine ; la
capacité du patron ne choisit pas l'anatomie. Utiliser
`studio_prepare_body_target(project_root, selection_path, target_path)` avec
les fichiers explicites du corps et de ses cibles. La copie native est mesurée
et réouverte avant sa revue ; les dimensions absentes restent non ciblées.
Les contrôles régionaux gardent leurs budgets, résidus et régions protégées.
Voir [le parcours automatisé](../../references/automation-runtime.md).

Avant les étapes physiques du vêtement sur un mannequin, préparer [la classification du vêtement et son aisance](../../references/garment-fit-intent.md) : catégorie, intention de coupe, configuration de port et couches. Reprendre toute intention déjà donnée par l'utilisateur. Préparer les chemins de mesure homologues et les cibles minimale/cible/maximale d'aisance avec leur répartition mouvement/couches/style ; présenter les propositions chiffrées pour revue lorsqu'elles manquent. Ne pas demander à l'utilisateur de calculer ces données. Le mot manteau n'accorde aucun nombre de centimètres automatique. `studio_compile_production_dossier` retourne `compilation` et `fit_preflight` séparément ; utiliser `fit_profile_path` pour la fiche. Une compilation `READY_TO_PLAN`, une réserve de collision ou une simple longueur de bord ne qualifient pas l'aisance. Pour un devant ouvert, mesurer la couverture et les recouvrements du candidat exact ; ne pas additionner le devant intérieur d'une autre couche à un tour fermé. Une information absente reste manquante et bloque l'admission physique de production. Les essais synthétiques restent explicitement TEST_ONLY et ne qualifient pas le vêtement. En cas de capacité insuffisante, conserver le corps approuvé et préparer une variante de patrons séparée à revoir.

Suivre [la reprise après un refus](../../references/preparation-recovery.md).
Distinguer une limite du logiciel d'une erreur de préparation : pour une limite,
informer l'utilisateur et lui faire choisir entre conserver la technique
approuvée avec un parcours compatible et revenir au contrat supporté, avant
tout changement. Pour un défaut confirmé ou des pièces manquantes, proposer une
correction ciblée ou refaire les seuls patrons/dérivés concernés depuis les
sources approuvées, puis recontrôler raccords et complétude. Un bord partagé
entre couture permanente et attache détachable n'est pas automatiquement erroné.
Conserver le découpage approuvé et les autorisations d'exécution Blender.

Suivre [la complétude des pièces](../../references/piece-completeness.md).
Présenter `piece_completeness.summary` et les identités manquantes dans le
chat avec chaque aperçu. Les candidats de préparation restent distincts de
la géométrie active et une couverture locale ne vaut pas couverture globale.

Lorsque les valeurs numériques et la sous-couche ont été réellement acceptées, conserver cette décision comme `ease-design.<composant>` avec ses fichiers exacts. Utiliser `studio_prepare_pattern_ease_variant` pour préparer une variante calculée séparée et son diff. Le choix des paramètres de calcul et la préparation réversible ne nécessitent pas de faire réapprouver des chiffres inchangés. Cette décision ne vaut pas revue des patrons dérivés : présenter leur planche et les contraintes mesurées avant leur adoption. Conserver la revue de la fiche complète `fit-intent.<composant>` et l’autorisation Blender distinctes. Les chemins obliques gardent `source_uv_polyline_cm` ; ne pas remplacer une courbe par sa corde. Voir [les variantes calculées](../../references/pattern-ease-variants.md).

Avant chaque appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter l'opération préparée, le projet cible et ses effets attendus ; demander explicitement l'autorisation de l'utilisateur et attendre sa réponse affirmative. La préparation du code et les validations du pipeline ne valent pas autorisation d'exécution. Un refus ou une absence de réponse empêche l'appel. Si l'opération ou ses arguments changent, demander l'autorisation pour la nouvelle action. Respecter tout blocage de Codex ou du projet. Voir [le protocole Blender](../../references/blender.md).

Pour PATTERN_SEWN, suivre [le fitting mesuré](../../references/measured-fitting.md) avant de varier la physique : préparer la fiche technique depuis le corps cible, le collider effectif et les repères homologues des patrons à la ligne de couture. Appeler inspect_garment_fit ; repères/capacité absents restent NOT_QUALIFIED. Distinguer déficit de coupe prouvé, signaux de placement, supports et physique non établie. Ne jamais déduire un manque d'aisance d'un échec Cloth seul. Les fitting_tacks natifs ne tiennent qu'une closure source dans l'essai local, avec force commune/durée explicites ; pas de retypage/soudure, pas de full/freeze tant qu'ils sont présents. Retirer ces attaches puis requalifier local sur la recette exacte. Une proposition d'ajustement alloue le déficit en cm, sans éditer de courbes : si nécessaire, préparer une variante native séparée, recontrôler coutures/embu/droit-fil et faire valider le board des différences avant production. Ne pas faire réapprouver une coupe inchangée ni imposer un formulaire utilisateur.

Avant Cloth pour PATTERN_SEWN, suivre [la revue de prépositionnement](../../references/sewing-placement.md) : appeler `inspect_sewing_placement`, examiner coutures, supports, trajets dans les colliders et orientations, puis ouvrir un rendu du montage initial. Une manche alignée sur un bras n'est pas forcément enfilée. Utiliser d'abord flat/cylinder avec paramètres mesurés ; leurs limites restent explicites. Le rapport automatique de tentative ne remplace pas cette revue et n'accorde aucun PASS local ni validation de silhouette.

Commencer par le brief : destination render/game/animation/3d_print, hauteur réelle, composants, relations et fichiers sources. Lire [le déroulement](../../references/production.md). Utiliser studio_create_project puis studio_project_status pour reprendre la base SQLite canonique. Chaque composant garde son propre routage et son package. N'utiliser un état COMPLETE qu'après rapport profilé, fichiers vérifiés et acceptation humaine. Le plugin n'installe pas ComfyUI, comfy-mcp, comfy-cli ou Blender. Un backend absent est UNAVAILABLE, pas un échec de l'asset. Respecter le dossier de production choisi par l'utilisateur.

À chaque invocation, sélectionner explicitement le projet avec `studio_project_status(project_root)` (ou le créer), même dans un chat dont le cwd est ailleurs. Cette étape permet au hook de rattacher les appels suivants à ce projet lorsque l'hôte fournit son identifiant de session.

Avant toute production 3D, suivre [la préparation et la revue humaine du découpage](../../references/construction-review.md). Produire une proposition enregistrée avec `studio_propose_pipeline`, expliquer la méthode recommandée et ses alternatives, puis enregistrer uniquement les décisions réellement données. Préparer les données techniques et les packages conformes à cette méthode. Si PATTERN_SEWN est retenu, `studio_build_construction_board` doit produire l'image en trois parties : **1. vues orthographiques, 2. décomposition du vêtement, 3. patrons 2D**. Ouvrir cette image et le dossier, les présenter à l'utilisateur et demander son approbation du découpage. Ne pas enregistrer cette approbation à sa place.

`studio_check_pipeline` doit être admis avant reconstruction. Utiliser `studio_blender_operation` pour obtenir le code exact des opérations Blender. Une création générale autorisée, un job terminé ou une image générée ne valent pas validation du découpage. Si une méthode est indisponible, présenter ce blocage et une alternative : ne jamais la remplacer silencieusement par des surfaces procédurales. Ne pas contourner les contrôles par le terminal, un autre MCP, un changement de cwd ou une modification SQLite. Ne pas modifier l'historique d'un ancien projet pour le faire passer conforme.

Pour un programme repris ou composé de plusieurs étapes, enregistrer les unités
et budgets avec `studio_create_run(project_root, kind, specification_path)`.
Utiliser `studio_next_run_step(project_root, run_id)` pour réconcilier les reçus
réels et préparer la prochaine unité admissible ; lire son état avec
`studio_run_status(project_root, run_id)`. `studio_request_run_stop` conserve les
tentatives et arrête à une frontière. Chaque opération Blender préparée garde
l'autorisation exacte requise ci-dessus. Après interruption, suivre la
restauration canonique du checkpoint d'entrée avant de rejouer ; aucune reprise
dynamique Cloth à mi-cache n'est promise. `COMPLETED` du journal ne vaut pas
acceptation physique, fitting ou artistique. Voir
[les preuves et limites](../../references/automation-validation.md).

Pour ComfyUI, préparer les variantes via `studio_prepare_workflow_variant` et
conserver la clé de requête stable. Une soumission incertaine demande
`studio_reconcile_comfy_job` ou la réconciliation du run possédé. Ne jamais
resoumettre sous une nouvelle clé pour contourner une incertitude ; conserver
`UNKNOWN_COMPLETION` ou `INCOMPLETE` si les preuves fournisseur et les fichiers
de sortie ne permettent pas de conclure. La fin du job ne qualifie pas l'asset.

Le board de préparation est construit à partir des images de référence originales fournies par l’utilisateur, avant modélisation. Ne jamais utiliser le mesh produit comme sa propre référence de conception. Le dossier doit fournir `source_references` (preuves des originaux et origine dans la conversation), `source_evidence_keys` pour chaque vue et pièce, et `reference_notes` pour les indices observés ou extrapolés. Les références sources doivent être celles examinées dans le gate references. Elles sont intégrées au board et au dossier. Le type mesh-render est refusé pour les vues de ce board. Un board documentaire créé après la 3D est un diagnostic séparé et ne remplace jamais cette validation.

Appliquer les [contrôles des autres étapes](../../references/lifecycle-guards.md) : preuves spécialisées pour reconstruction, assemblage, finition, comportements et livraison. Reprendre les preuves existantes sans transformer une ancienne approbation générale en approbation du candidat actuel.

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
