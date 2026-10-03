---
name: refine-3d-asset
description: Corriger un asset Blender reconstruit en topologie, raccords, silhouette, UV ou matériaux à partir de preuves visuelles.
---

# refine-3d-asset

Suivre [la reprise après un refus](../../references/preparation-recovery.md).
Distinguer une limite du logiciel d'une erreur de préparation : pour une limite,
informer l'utilisateur et lui faire choisir entre conserver la technique
approuvée avec un parcours compatible et revenir au contrat supporté, avant
tout changement. Pour un défaut confirmé ou des pièces manquantes, proposer une
correction ciblée ou refaire les seuls patrons/dérivés concernés depuis les
sources approuvées, puis recontrôler raccords et complétude. Un bord partagé
entre couture permanente et attache détachable n'est pas automatiquement erroné.
Conserver le découpage approuvé et les autorisations d'exécution Blender.

Avant chaque appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter l'opération préparée, le projet cible et ses effets attendus ; demander explicitement l'autorisation de l'utilisateur et attendre sa réponse affirmative. La préparation du code et les validations du pipeline ne valent pas autorisation d'exécution. Un refus ou une absence de réponse empêche l'appel. Si l'opération ou ses arguments changent, demander l'autorisation pour la nouvelle action. Respecter tout blocage de Codex ou du projet. Voir [le protocole Blender](../../references/blender.md).

Pour un arrêt de déplacement Cloth, lire [le diagnostic de mouvement](../../references/cloth-motion.md) via inspect_sewing_failure : sommet source/pièce, excursion depuis le début de phase, incrément entre deux images évaluées et image d'arrêt. Ne pas déduire l'incrément de deux maxima scalaires ni qualifier une instabilité par l'excursion seule. Préparer une unique correction mesurée et bornée de placement/appui, avec précontrôle natif et nouvelle preuve locale ; ne pas relâcher le budget. mount/drape existent déjà ; après retrait d'appuis temporaires, requalifier la recette correspondante.

Pour PATTERN_SEWN, suivre [le fitting mesuré](../../references/measured-fitting.md) avant de varier la physique : préparer la fiche technique depuis le corps cible, le collider effectif et les repères homologues des patrons à la ligne de couture. Appeler inspect_garment_fit ; repères/capacité absents restent NOT_QUALIFIED. Distinguer déficit de coupe prouvé, signaux de placement, supports et physique non établie. Ne jamais déduire un manque d'aisance d'un échec Cloth seul. Les fitting_tacks natifs ne tiennent qu'une closure source dans l'essai local, avec force commune/durée explicites ; pas de retypage/soudure, pas de full/freeze tant qu'ils sont présents. Retirer ces attaches puis requalifier local sur la recette exacte. Une proposition d'ajustement alloue le déficit en cm, sans éditer de courbes : si nécessaire, préparer une variante native séparée, recontrôler coutures/embu/droit-fil et faire valider le board des différences avant production. Ne pas faire réapprouver une coupe inchangée ni imposer un formulaire utilisateur.

Un `garment` rejeté avant son reçu se diagnostique par [inspect_garment_failure](../../references/garment-rejections.md), même pendant pending et après restauration. Lire les segments/positions/cosinus ou les contacts initiaux par pièce/sommet/collider ; conserver les seuils et corriger la recette indépendamment des patrons approuvés. Ne pas déclarer un bug Cloth, un faux positif ou une silhouette réparée à partir de ces seuls diagnostics.

Pour un échec de montage textile, restaurer puis utiliser [le diagnostic de prépositionnement](../../references/sewing-placement.md) avant un nouvel essai Cloth. Ajuster localement la recette de placement/support sans réécrire les patrons approuvés ni relâcher les seuils ; rebuild conserve l'ancien mesh. Ne pas annoncer un fitting réparé à partir d'une fixture ou d'un rapport sans avertissement.

Pour cadrer un mesh existant, utiliser le parcours contrôlé `frame_view` puis
capturer VIEW_3D, sans code de géométrie direct ni changement implicite de
visibilité. Les échecs Cloth conservés s'inspectent par `inspect_sewing_failure` ;
leurs mesures FAIL n'accordent aucune acceptation. Voir le
[protocole](../../references/viewport-diagnostics.md).

Comparer les rendus neutres aux références avant la correction. Définir une correction bornée par composant et créer un checkpoint avec blender/operations.py. Conserver les IDs, la provenance et les relations. Vérifier la correction par un nouveau rendu aux mêmes caméras et mesurer la géométrie concernée. Ne pas relancer les reconstructions indépendantes réussies. Si une correction invalide une pièce acceptée, conserver l'historique et créer une nouvelle révision de projet/package ; ne pas réécrire un état COMPLETE.

Respecter [la revue humaine de construction](../../references/construction-review.md). Après préparation des packages, le board doit montrer les données réellement utilisées et attendre la validation humaine du découpage. Les opérations Blender passent par `studio_blender_operation`; ne pas contourner un refus par un script direct. Conserver les sources, ouvrir les preuves visuelles et ne pas confondre contrôles techniques et acceptation artistique.

Avant BEHAVIOR_AUTHORING, produire refinement-validation selon stage-validation.schema.json, stage REFINING, avec geometry/scale/orientation/separation et leurs check_evidence. Sauvegarder une copie immuable de la scène et une revue silhouette-review selon visual-review.schema.json ; présenter ses rendus contre les références, puis enregistrer l’accord réel dans le gate silhouette. Voir le [protocole des preuves](../../references/lifecycle-guards.md).
