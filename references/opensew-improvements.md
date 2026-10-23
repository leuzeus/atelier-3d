# Renforcements PATTERN_SEWN après l'étude OpenSew

État local du 3 octobre 2026, sans changement de version distribuée ni publication.
L'[analyse OpenSew conservée](G:/projets/atelier-3d/work/opensew-analysis-20261003/rapport-opensew-atelier.md)
a servi à identifier les contrôles à renforcer. Le parcours conserve les patrons
métriques, le mapping par IDs et longueur d'arc, le maillage dérivé, les repos
explicites et les transitions natives d'Atelier. Garment Tool n'est pas utilisé.

**Les mécanismes ci-dessous sont implémentés et disposent de preuves ciblées.
Le fitting du vêtement réel reste non qualifié.** Un résultat de coupon, une
préparation `READY` ou une consolidation ne transfère aucune acceptation
physique, anatomique ou artistique à ce vêtement.

## Six changements effectivement présents

| Axe | Implémentation | Portée et limite |
| --- | --- | --- |
| 1. Métrique commune | [cloth_metrics.py](G:/projets/atelier-3d/a3d/cloth_metrics.py) calcule les déformations principales, ratios d'arêtes, aire, angles, orientations et flexion. Préparation, fermeture, consolidation et chaque frame Cloth évaluée appellent ce socle. | Contrat `cloth-metrics/2`. Les UV, IDs de pièce et sommets source restent liés **par face**, y compris après soudure de plusieurs îlots. La flexion ne remplace pas la mesure d'étirement. |
| 2. Enfilage mesuré | [dressing.py pur](G:/projets/atelier-3d/a3d/dressing.py) valide régions, ouvertures, côtés extérieurs, ordre et jalons. [L'audit natif](G:/projets/atelier-3d/blender/dressing.py) intersecte les triangles du collider avec les sections sourcées, mesure le passage dans les bords du patron et vérifie les normales extérieures. | Une déclaration de pose ou un booléen ne suffit pas. Les données absentes, ambiguës ou partielles restent distinctes d'un enfilage complet admis. |
| 3. Contacts au cours du montage | [contact_geometry.py](G:/projets/atelier-3d/a3d/contact_geometry.py) fournit les distances et intersections triangle/triangle après présélection BVH ; [cloth_contacts.py](G:/projets/atelier-3d/blender/cloth_contacts.py) contrôle l'état initial, les frames et les intervalles échantillonnés. | Corps figé et lié par empreinte ; segments de déplacement des sommets et interpolation temporelle bornée. Une réserve ou un budget insuffisant produit un refus, pas un contrôle omis. Ce n'est pas une preuve de collision continue exhaustive. |
| 4. Repos et appuis explicites | [sewing.py](G:/projets/atelier-3d/blender/sewing.py) conserve `A3D.FlatRest` avant consolidation, `A3D.AssembledRest` après, `Dynamic Mesh` désactivé et `shrink_min/max` à zéro. Réglages réellement exécutés, repos, métriques source et état des appuis figurent dans le reçu. | La détente continue exige zéro ressort permanent et zéro appui temporaire. Les redémarrages du montage segmenté restent déclarés quasi statiques. Les coupons ne calibrent pas une matière réelle. |
| 5. Couches ordonnées | Le plan déclare un DAG intérieur→extérieur ; `layer_collision_selection` choisit les seuls colliders intérieurs. L'audit mesure également le côté relatif des surfaces de vêtements. | Une seule couche active de panneaux est simulable par l'objet Cloth natif courant. Plusieurs couches externes peuvent servir de colliders ; plusieurs couches actives exigent des simulations séparées et sont refusées par cette entrée. Interaction unidirectionnelle explicitement déclarée. |
| 6. Reprise et qualification bornées | Préparation et simulation émettent `validation_contract.version=2`. Le drapé remesure l'enfilage statique avant et après Cloth ; le gel vérifie à nouveau les références exactes et exige le drapé qualifié courant. | Les jalons de placement initiaux ne sont pas rejoués après consolidation. Les anciens PASS restent historiques ; une nouvelle qualification exige les contrôles actuels. Les mesures homologues de fitting, le comportement et l'acceptation humaine restent nécessaires. |

Le maillage triangulaire contraint et son raffinement borné restent en place.
Après la triangulation native, `a3d/mesh_refinement.py::improve_interior`
améliore les angles par déplacements intérieurs bornés. Les sommets des
contours et crans restent fixes ; une proposition qui dégrade la qualité
locale est rejetée. Les faces et leurs correspondances ne sont pas remplacées.
Cette évolution n'introduit ni remplacement par une grille quad ni correction
de coupe implicite. Une qualité insuffisante conserve son diagnostic.

Une normale opposée dans le repère mondial ne suffit pas à démontrer une
inversion matérielle : une rotation rigide peut produire ce signe sans
déformation. Le validateur contrôle les liaisons et le sens des faces source,
les effondrements lors des opérations géométriques explicitement linéaires,
puis le côté extérieur par les régions sourcées. Il ne présente pas les seules
positions finales d'un triangle isolé comme une preuve de son trajet.

## Contrat `dressing` et `layers`

Ces objets optionnels, chacun en version 1, prolongent le
[schéma du plan d'assemblage](G:/projets/atelier-3d/schemas/pattern-assembly.schema.json).
Le [template](G:/projets/atelier-3d/templates/pattern-assembly.json) est un exemple
à renseigner : ses références ne constituent pas des données approuvées.
Toute `source_ref` de ces objets contient un chemin relatif au projet et le
SHA-256 réel du fichier. Les références sont relues et vérifiées, même pour
des données de couches historiques sans contrat d'enfilage.

| Donnée | Contenu exigé et mesure |
| --- | --- |
| `dressing.required` | `true` pour demander l'admission complète de l'enfilage ; un contrôle facultatif ne peut pas devenir un PASS complet. |
| `regions` | ID, référence source, identité du collider, `axis_start_cm`, `axis_end_cm` et `section_parameters` croissants entre 0 et 1. Les sections sont calculées sur la cage évaluée, sans rayon déclaré considéré comme preuve. |
| `openings` | ID, référence source, région, section choisie, liste ordonnée de `{piece, edge, reverse}` et `plane_tolerance_cm` explicite. Les IDs désignent les bords du mapping courant, pas des indices d'une ancienne triangulation. |
| `assignments` | Pièce, région et `outward_normal_sign` sourcé. Une demande complète couvre tous les panneaux et dispose d'un passage pour chaque région affectée. |
| `mount_order` | Chaque ID d'ouverture exactement une fois. Cet ordre est conservé dans l'audit ; il ne fabrique pas une animation d'enfilage. |
| `milestones` | Jalons sourcés avec `translations_cm` rigides par pièce. Tous les états et segments respectent les budgets existants ; la base métrique source est requise pour contrôler le déplacement total. Les rotations de jalons ne sont pas prises en charge par cette version. |
| `layers.nodes` | IDs, `kind: body/garment`, panneaux et colliders possédés, référence source ; côté extérieur sourcé pour mesurer une couche de vêtement externe. Chaque panneau et collider appartient à un seul nœud. |
| `layers.inside_to_outside` | Relations `[intérieur, extérieur]` sans cycle. Les couches de vêtements incomparables demandent une clarification ; le corps précède les vêtements. |
| `layers.mode`, `interaction` | `single` pour une couche de vêtement, `ordered` pour plusieurs ; `one_way_declared` expose l'approximation de collision dans un seul sens. |

Une ouverture peut être encore non cousue. L'audit autorise alors uniquement
des **ponts virtuels entre partenaires permanents directs déclarés**, dans
`assembly.max_initial_gap_cm`. Il enregistre `bridged_permanent_seams` et ne
crée aucune union. La tolérance finale de soudure demeure indépendante.
Les raccords sans partenaire et les passages ouverts par `closure` ou
`detachable` ne sont pas modélisés comme des boucles refermées dans cette
version : ils restent refusés ou à préciser. Aucune fermeture fonctionnelle
n'est transformée en couture permanente pour faire passer le contrôle.

`READY` pour l'enfilage complet exige `required:true`, `full_coverage:true` et
tous les contrôles mesurés admis. Une demande facultative ou partielle sans
défaut donne `NOT_ASSESSED` avec `measured_status: GEOMETRY_CHECKS_PASSED`.
Un défaut conserve `NEEDS_CORRECTION` ; une donnée indispensable manquante
conserve `NEEDS_CLARIFICATION`. Sans ancien contrat, l'enfilage est
`NOT_ASSESSED`. Une préparation géométrique peut donc être `READY` alors que
son enfilage historique reste non évalué ; cela ne qualifie pas le fitting.

Les empreintes prouvent l'identité des fichiers et cages utilisés. Elles ne
prouvent pas que des repères déclarés sont anatomiquement approuvés. La revue
sourcée de l'enveloppe reste distincte du calcul et de l'acceptation artistique.
Une section peut couper plusieurs régions du même collider : seules les
mesures de l'unique boucle fermée contenant strictement l'origine de l'axe
sourcé alimentent le passage demandé. Les boucles exclues restent archivées.
L'absence de boucle, un axe sur la frontière ou plusieurs boucles candidates
provoquent un refus ; l'audit ne choisit jamais une boucle parce qu'elle passe.

## Recette générique et reprise

1. Conserver les sources et reçus existants, puis travailler dans une copie
   isolée sur G:. Identifier les patrons approuvés, le corps évalué, la pose,
   l'enveloppe et les éventuels vêtements intérieurs. Ne modifier ni coupe,
   corps, échelle ni seuil final pour obtenir une admission.
2. Préparer une préforme reliée aux UV : Bend natif pour une courbure simple,
   sections ou cage sourcée pour un raccord complexe. Déclarer les régions,
   passages, côtés extérieurs et appuis ; mesurer les repères au lieu de les
   déduire d'une silhouette rendue. Pour un squelette ajouré, fournir et revoir
   une enveloppe auxiliaire appropriée.
3. Déclarer le DAG des couches. Pour une couche active, sélectionner seulement
   ses ancêtres comme obstacles. Une couche extérieure ne doit pas devenir
   silencieusement un collider intérieur. Si plusieurs couches actives sont
   demandées, conserver le refus et préparer des simulations séparées.
4. Exécuter `prepare_pattern_assembly` selon la
   [recette native de préparation](G:/projets/atelier-3d/references/pattern-preparation.md).
   Examiner métrique, qualité, passages, contacts, matière et appuis ; lire les
   vues face/profil/dos/trois quarts et les raccords. Un candidat refusé reste
   inspectable sans remplacer le candidat actif.
5. Si une configuration correctement enfilée est construite directement,
   conserver le périmètre « configuration statique », sans prétendre avoir
   simulé un trajet. Si un déplacement autour d'un obstacle est nécessaire,
   fournir des jalons admissibles et leur base source. Les contacts sont
   contrôlés à chaque segment ; aucune projection corrective n'est appliquée.
6. Consommer la préparation exacte dans
   [l'assemblage natif](G:/projets/atelier-3d/references/pattern-assembly.md) :
   migration facultative, prépositionnement, montage, fermeture bornée unique,
   consolidation, détente puis drapé. Conserver la recette, le plan, les SHA,
   checkpoints et reçus. La consolidation préserve les UV distincts par face.
7. Avant et après le drapé, contrôler la configuration courante avec ses
   nouvelles coordonnées. Les jalons initiaux restent liés à leur preuve de
   placement ; `STATIC_RECHECK_CURRENT_DRESSING_ORIGINAL_PLACEMENT_PATH_NOT_REPLAYED`
   indique leur absence de rejeu. Après un refus, récupérer par la transition
   native et corriger une nouvelle entrée sourcée, sans éditer les reçus.
8. La création de la copie de rendu exige le drapé et le fitting courants
   qualifiés, les appuis temporaires retirés et les références encore exactes.
   Son comportement reste à qualifier ensuite ; l'acceptation finale et
   l'export exigent cette qualification et l'acceptation visuelle du candidat.
   Subdivision et épaisseur d'affichage restent après Cloth. La copie de rendu
   ne reçoit pas automatiquement `accepted:true`.

## Migration et fonctions conservées

| Fichier / fonction | Décision | Raison et migration |
| --- | --- | --- |
| `a3d/cloth_metrics.py` — `face_sources`, `evaluate_metrics`, `validate_metrics` | Conserver comme socle partagé | Métrique 2D par face et identité source après union. Contrat version 2 dans les nouveaux reçus ; aucune moyenne entre îlots UV. |
| `a3d/pattern_preparation.py` — `preparation_statistics` | Remplacer le calcul métrique dupliqué | Consomme le socle partagé en conservant les statistiques de préparation et leur localisation. |
| `a3d/pattern_assembly.py` — `continuous_quality`, `bounded_close`, `consolidate` | Conserver les étapes, remplacer le contrôle limité aux arêtes | Même contrat principal par face ; contrôle de l'effondrement pendant les interpolations géométriques explicitement linéaires. Les anciens reçus restent lisibles. |
| `blender/sewing.py` — `simulation_quality`, `simulate_object` | Remplacer l'admission finale seule par les contrôles courants | Métrique à chaque frame évaluée, contacts initial/final et mouvement discret ; paramètres et repos exécutés conservés dans `validation_contract.version=2`. |
| `blender/pattern_assembly.py` — `self_contact_report`, `collision_guard` | Remplacer la décision fondée sur le seul recouvrement BVH | Présélection conservatrice puis test précis triangle/triangle. Les anciens comptes BVH gardent leur ancien sens et ne deviennent pas des intersections confirmées. |
| `a3d/dressing.py` / `blender/dressing.py` | Conserver les nouveaux contrats et audits | Références exactes, passages mesurés, DAG et sélection d'obstacles. Ancien monocouche traduit explicitement ; plusieurs panneaux ne signifient pas plusieurs couches. Ancien multicouche ou collider non classé sans ordre : clarification. |
| `blender/preform.py` / `a3d/preform_volume.py` | Conserver | Bend, cages et sections restent des guides du maillage dérivé ; ils ne prouvent pas à eux seuls l'enfilage. Toute nouvelle préforme invalide les preuves dépendantes. |
| `blender/sewing.py::triangulate` / `a3d/mesh_refinement.py::improve_interior` | Conserver CDT natif, compléter le raffinement | Amélioration bornée des sommets intérieurs seulement, frontières fixes, objectif d'angle inchangé. Un reliquat sous la cible reste refusé ; aucun défaut de coupe n'est déduit de ce seul échec local. |
| `blender/sewing.py` — `apply_physics`, `physical_snapshot`, `verify_physics` ; `support_weights` | Conserver et compléter les preuves | Repos, `Dynamic Mesh`, shrink nul et appuis effectifs tracés. Les profils ne deviennent pas une calibration textile par simple migration. |
| `migrate_legacy_receipt`, `legacy_metric_evidence`, `prepared_receipt`, `freeze_continuous` | Conserver, renforcer l'admission | Ancien PASS enveloppé avec son périmètre historique ; ancienne préparation READY à refaire avec le validateur courant. Le gel vérifie les sources et exige les preuves actuelles. |
| Entrées historiques `experimental_prefit`, `interface_preparation`, `panel_mount`, `fitting_placement`, `contact_recovery`, `fitting_pose`, `fitting_tacks` | Déprécier leur empilement dans le parcours nominal | Utiliser le plan et les transitions natifs ; archiver la recette exacte avant retrait des champs. Garder primitives utiles, lecteurs de reçus et tests historiques. Voir la table détaillée de préparation. |
| Lecteurs de reçus et preuves historiques | Ne rien supprimer dans cette livraison | Leur suppression demanderait une migration vérifiée de tous les consommateurs. Aucune suppression n'est nécessaire pour ces renforcements. |

Un ancien PASS basé sur les ratios d'arêtes conserve ce périmètre historique.
Il ne devient pas une preuve de déformations principales, d'enfilage ou de
contacts intermédiaires. Le montage libre réel déjà passé reste sa propre
preuve ; son fitting demeure une qualification distincte.

## Preuves ciblées et limites actuelles

| Preuve locale | Résultat constaté | Ce qu'elle ne qualifie pas |
| --- | --- | --- |
| [dressing-05](G:/projets/atelier-3d/work/opensew-implementation-20261003/dressing-05/result.json) | `PASS_GEOMETRIC_DRESSING_ONLY` : manche droite et inclinée admises ; col insuffisant, trajet traversant, côté inversé, budget source et sources périmées refusés ; données manquantes ou facultatives non promues ; ordre des deux bandes mesuré ; sections multiples sélectionnées par axe sourcé uniquement. | Cloth, morphologie réelle et acceptation artistique. |
| [contact-08](G:/projets/atelier-3d/work/opensew-implementation-20261003/contact-08/result.json) | PASS des cas ciblés : traversée de face malgré sommets/arêtes/centroïde dehors, traversée entre frames, tangence extérieure, réserves, couches, corps modifié et budgets épuisés ; IDs du vêtement et du collider distincts dans les diagnostics. | Trajectoire d'un corps animé ou collision continue exhaustive. |
| [physics-03](G:/projets/atelier-3d/work/opensew-implementation-20261003/physics-03/result.json) | `PASS_COUPONS_ONLY` : vrais Cloth courts avec repos plat puis repos consolidé, métriques et contacts évalués, zéro shrink/ressort/appui temporaire, réouverture des repos. | Calibration de matière, stabilité longue et drapé du vêtement réel. |
| [preparation-01](G:/projets/atelier-3d/work/opensew-implementation-20261003/preparation-01/result.json) | Cinq `PASS_PREPARATION_ONLY` / préparations `READY`, contrat version 2, reprise exacte ; leur enfilage reste explicitement `NOT_ASSESSED`. | Fitting par simple transfert de leurs préparations. |
| [bending-03](G:/projets/atelier-3d/work/opensew-implementation-20261003/bending-03/result.json) | Quatre vrais Cloth, effets de flexion mesurés avec deux repos, autres paramètres identiques dans chaque paire. | Calibration de matière et vêtement réel. |

La détection temporelle est discrète et bornée. Les empreintes refusent un
collider modifié pendant l'intervalle ; le mouvement du corps n'est pas couvert.
Une tangence extérieure sans réserve ne justifie jamais l'acceptation d'une
pénétration profonde. Un manque de budget de calcul est un refus explicite,
pas un résultat clair par défaut. Les couches ouvertes sont mesurées par côté
orienté et échantillons ; leur ordre ne constitue pas une interaction Cloth
bidirectionnelle.

Le repos 3D consolidé mémorise la forme admise lors de sa création ; la métrique
source 2D reste auditée séparément. Les coupons ne démontrent pas que cette
mémoire est adaptée à tout tissu. Le raffinement peut encore laisser des
angles sous la cible ; il doit les signaler sans changer le contour source.

Le vêtement réel reste **NOT_QUALIFIED**. L'[audit régional](G:/projets/atelier-3d/work/opensew-implementation-20261003/regional-02/result.json)
admet géométriquement les poignets et orientations, mais conserve les autres
refus. Une variante auxiliaire séparant thorax/cervicales réduit les contacts
du col à préforme identique, sans supprimer le contact profond au buste.
Les essais réels et leur bilan sont liés à leurs rapports exacts dans
[VALIDATION.md](G:/projets/atelier-3d/VALIDATION.md), sans déduire leur résultat
des coupons ci-dessus. La scène interactive, les projets consommateurs et le
corps source sont préservés ; les essais et caches configurables restent sur G:.
