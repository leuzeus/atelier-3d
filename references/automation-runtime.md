# Utiliser le runtime d'automatisation

Le runtime prépare des données et des étapes déterministes, conserve les
tentatives dans SQLite et rattache les résultats aux fichiers réellement
utilisés. Chaque contrôle garde sa portée : compilation, géométrie, physique,
fitting et décision humaine sont distincts. Le [programme approuvé](automation-program.md)
décrit les lots ; la [fiche de validation](automation-validation.md) décrit les
preuves disponibles et celles qui restent nécessaires.

Cette fiche décrit les interfaces du checkout de développement. Une installation
existante doit être vérifiée avec `studio_doctor` avant de supposer qu'elle expose
ces mêmes appels. Elle ne constitue ni une publication ni une nouvelle installation.

## Parcours systématique d'un vêtement

1. Sélectionner le projet avec `studio_project_status(project_root)` ; créer un
   dossier d'asset distinct du code du plugin si nécessaire. Références, découpage,
   packages et décisions restent liés à ce projet.
2. Dès l'ajout d'un mannequin, établir la sélection du corps et les cibles
   explicites depuis les décisions humaines. Conserver l'original, préparer une
   copie séparée, mesurer le corps évalué et faire revoir ses proportions. La
   capacité des patrons ne choisit pas l'anatomie du porteur.
3. Compiler les rôles, bords, raccords, couches et guides depuis les sources
   approuvées. Une donnée manquante appelle une correction localisée ; elle
   n'autorise pas à inventer une couture ou à modifier le découpage.
4. Enregistrer un programme borné, puis préparer sa prochaine unité admissible.
   Les guides ou un placement exploratoire restent non admis tant que les
   contrôles finaux de métrique, contacts et complétude échouent.
5. Présenter chaque opération Blender exacte, son projet et ses effets, puis
   attendre l'autorisation requise avant son exécution. Examiner le résultat
   natif et ses limites avant de préparer l'étape suivante.
6. Mesurer l'enfilage, exécuter les essais et le drapé, puis contrôler le fitting
   et les mouvements sur le vêtement complet. La revue artistique et l'acceptation
   finale portent sur les fichiers et pixels effectivement examinés.

Voir [la préparation du corps cible](garment-body-target.md),
[le fitting mesuré](measured-fitting.md) et [le protocole Blender](blender.md).

## Préparation du corps et des dossiers

| Appel | Arguments | Effet et limite |
| --- | --- | --- |
| `studio_select_catalog_body` | `project_root`, `asset_id`, éventuellement `target_stature_cm` et `target_provenance` ensemble | Copie une base explicitement choisie ; une stature déclarée prépare le dossier cible et son opération native |
| `studio_prepare_body_target` | `project_root`, `selection_path`, `target_path` | Valide les cibles et prépare le code natif d'une copie mesurée ; ne l'exécute pas |
| `studio_compile_production_dossier` | `project_root`, `dossier_path`, `specification_path`, éventuellement `fit_profile_path` et `body_region_options_path` | Renvoie compilation et précontrôle du fitting ; prépare les domaines corporels sourcés si les options sont explicites |
| `studio_plan_garment_assembly` | `project_root`, `specification_path` | Planifie groupes permanents, couches et dépendances ; ne déforme ni ne simule la scène |

Une variante définie seulement par stature utilise un facteur uniforme dans le
cadre déclaré et conserve le plan des pieds source. Les tours mesurés restent
non ciblés. Les contrôles régionaux V1 visent les sections sourcées de poitrine,
taille et hanches, avec budget, résidus et régions protégées ; les cibles
impossibles ou hors domaine sont refusées. Les essais génériques de ces contrôles
ne changent pas le corps principal approuvé. Tout changement du corps exige de
recalculer ses profils, guides et autres preuves dépendantes.

Les épaules utilisent des points de peau mesurés sur la triangulation du corps
évalué. Les centres d'os seuls ne définissent pas la surface sur laquelle placer
le tissu. Guides du col, du devant intérieur, de la capuche et des empiècements
conservent leurs références corporelles et leurs bords source.

La compilation du dossier renvoie désormais un wrapper
`{status, compilation, fit_preflight, qualification: NONE, fitting: NOT_EXECUTED}`.
`fit_profile_path` ajoute une comparaison géométrique avec le corps canonique
et les capacités source homologues. L'intention de silhouette, la classification
et les intervalles d'aisance doivent être explicites et sourcés : aucune valeur
en centimètres n'est choisie par défaut. Une classification ou une aisance
absente reste une donnée manquante. Ce précontrôle n'accorde pas de fitting.

`body_region_options_path` nécessite cette fiche de fitting et son corps exact.
Les options déclarent régions, côtés, fractions, axe de plan et budgets. Le
runtime prépare les domaines de faces depuis l'adapter anatomique original et
les artefacts réellement créés ou introduits dans le projet. Le résultat
`body_region_preparation` reste `PREPARED_NOT_MEASURED` ; sa politique peut ensuite
être sauvegardée et mesurée par le [service de sections corporelles](body-region-sections.md).
Cette préparation ne modifie pas le mannequin ni ses mensurations approuvées.

## Programmes, suivi et arrêt

| Appel | Arguments | Comportement |
| --- | --- | --- |
| `studio_create_run` | `project_root`, `kind`, `specification_path` | Enregistre le DAG et ses budgets sans exécuter Blender |
| `studio_next_run_step` | `project_root`, `run_id` | Réconcilie un résultat natif réel ou prépare la prochaine unité ; l'adaptateur ComfyUI peut appeler les primitives admises |
| `studio_run_status` | `project_root`, `run_id` | Lit progression, reçus, défauts et qualifications sans mutation |
| `studio_request_run_stop` | `project_root`, `run_id` | Demande l'arrêt à une frontière ; conserve les résultats et opérations incertaines |

Les `kind` disponibles sont `garment`, `comfy`, `material_bench`, `motion` et
`export`. Le [schéma de programme](../schemas/run.schema.json) décrit les unités,
leurs dépendances, arguments, références et budgets. Les compilateurs matière
et enfilage produisent aussi leur programme natif prêt à enregistrer.

Chaque référence cite `path` et `sha256`. Le journal lie spécification, unité,
tentative, entrées exactes, code pertinent, checkpoint et reçus. Réutiliser la
même identité de spécification avec des fichiers ou du code différents est
refusé. Une référence périmée invalide la preuve qui en dépend. Un changement
d'admission ou de dispatcher commun concerne toutes les unités qui l'utilisent.

Pour Blender, `AWAITING_CONFIRMATION` contient le code préparé et
`execution_permission_required: true`. Préparer un run ou approuver sa conception
ne donne pas l'autorisation d'appeler `execute_blender_code` ou
`execute_blender_code_for_cli`. L'autorisation porte sur l'opération et ses
arguments exacts. Respecter les refus du projet et de Codex ; une nouvelle action
modifiée exige sa propre autorisation.

`COMPLETED` décrit l'exécution d'un programme. Le champ `qualification` conserve
la portée observée de chaque résultat ; `accepted: false` empêche de confondre
fin d'exécution et acceptation du vêtement. Un fichier fourni avec `PASS` ou une
preuve générique enregistrée par l'utilisateur ne remplace pas un reçu natif
canonique. Une lecture ou un rendu ne qualifie pas une gate physique.

Les budgets bornent les tentatives et le temps. Le temps d'attente d'autorisation
est exclu de l'exécution native. Le dispatcher mesure le temps après retour et
ne peut pas préempter Blender ; les simulateurs ont leurs propres arrêts bornés.
Pour ComfyUI, le temps de la phase soumise couvre aussi la file et l'exécution
entre deux interrogations. Dépasser un budget laisse une unité `INCOMPLETE`.

## Reprise V1 après interruption

Le début natif, sa frontière de checkpoint et le résultat réel sont enregistrés
séparément. Une opération mutante conserve le pending jusqu'à l'enregistrement
de son résultat canonique. Si le callback est perdu après le retour, la prochaine
étape réconcilie `run_native_result_ready` sans rejouer la mutation.

Si aucun résultat complet n'est établi, `RECOVERY_REQUIRED` prépare la restauration
du checkpoint d'entrée exact. Elle reste soumise à l'autorisation Blender.
Après l'événement canonique `blender_recovered` correspondant au même fichier
et à la même empreinte, la tentative interrompue reste conservée et une nouvelle
tentative peut être préparée dans les budgets. Un pending effacé manuellement,
un checkpoint différent ou un fichier périmé ne permettent pas de rejouer.

La courte fenêtre entre `blender_started` et son hook de checkpoint est récupérable
uniquement si l'événement lie le run, l'unité, la tentative et les arguments exacts.
Sans cette origine canonique, le résultat reste `UNKNOWN_COMPLETION`. Le journal
ne déduit pas qu'une opération n'a pas eu d'effet.

Cette reprise restaure une frontière de scène et rejoue l'étape. Elle ne reprend
pas Cloth au milieu d'une dynamique : vitesses, caches et continuité physique
intermédiaire ne sont pas qualifiés. Les opérations temporaires qui préservent
la scène live produisent des artefacts distincts ; leurs échecs conservent leur
incertitude sans fabriquer un checkpoint de production.

## Banc matière et parcours d'enfilage

| Appel | Arguments | Sortie |
| --- | --- | --- |
| `studio_compile_material_bench` | `project_root`, `specification_path`, `output_dir` | Dossier de coupons comparables et programme natif ; répertoire neuf |
| `studio_compile_dressing_plan` | `project_root`, `candidate_path`, `assembly_plan_path`, `specification_path`, `output_dir` | Dossier de trajets et libération des supports depuis les sources exactes ; répertoire neuf |

L'opération native `run_material_bench` reçoit exactement `bench_path` et
`output_dir`. Ses programmes fixes cantilever/couture/contact ne varient qu'un
facteur déclaré, à conditions comparables. La convergence est observée sur les
positions évaluées. Une observation arrêtée par budget reste `INCOMPLETE`.
Le rapport reste `COUPON_ONLY` ; le contexte corps/pose cité n'est pas simulé
comme vêtement sur le corps, et aucune matière n'est choisie automatiquement.

Le jeu `supported-v2` déclare ses dimensions, bords maintenus, support fermé et
écart initial de couture avant l'essai. Les recettes dérivées conservent les
contrôles source et modifient un seul facteur. Le rapport conserve chaque image
observée, les paramètres RNA réellement assignés, les vitesses, contacts,
étirements, écarts de couture et raisons d'arrêt. Un cas conforme et convergé,
un défaut métrique et un budget épuisé restent trois résultats distincts. La
[campagne L7 v3](automation-validation.md#banc-matière-l7--comparaison-établie-recette-non-retenue)
prouve cette capacité comparative ; elle ne fournit pas une recette admise pour
le vêtement principal.

L'opération native `inspect_dressing_plan` reçoit exactement `component_id`,
`recipe_path` et `dressing_path`. Elle mesure le maillage et les colliders
évalués, les ouvertures et les trajets déclarés dans une pose corporelle fixe.
Son résultat reste `GEOMETRY_ONLY` : échantillons discrets, retrait des supports
planifié mais non exécuté, enfilage physique et fitting non qualifiés. Des
passages, ouvertures ou trajets absents ne sont pas inventés.

Ces deux opérations s'obtiennent avec `studio_blender_operation` ou depuis leur
programme. Compiler les fichiers n'exécute aucune simulation.

### Données d'enfilage à dériver sur le vêtement principal

Les templates v5 conservent les 15 patrons, les rôles et côtés approuvés, les
bords nommés, les raccords avec leur type, les guides corporels et l'ordre des
couches. Ils ne contiennent pas encore de contrat `dressing`. Ces sources
permettent une dérivation par code, sans ajouter de couture ni demander à une IA
de déplacer les pièces :

| Donnée | Source réutilisable et dérivation possible | Limite à conserver |
| --- | --- | --- |
| Contours et ouvertures candidates | `source_geometry.edges`, raccords `permanent`, sens et extrémités source ; parcourir la frontière après identification des seules coutures permanentes | Un contour fermé dans le graphe peut être le périmètre d'un panneau plat ; ce n'est pas une preuve de passage autour du corps |
| Région et axe | `piece_semantics.role/side`, repères mesurés `wrist`, `elbow`, `shoulder.surface`, `neck`, `waist` et `head.center` ; associer le membre ou le torse déclaré puis mesurer ses sections natives | Un centre d'os ne remplace pas une section de peau ; les sections absentes ou ambiguës doivent être mesurées ou refusées |
| Ordre partiel | Couches `inside_to_outside`, graphe des groupes permanents, liens `closure` et `detachable` conservés ouverts pendant leur étape | Les couches ne choisissent pas l'ordre des deux bras ni le mode de mise en place de la capuche ; une ambiguïté de méthode exige une décision explicite |
| Contrôles géométriques candidats | Mapper les bords UV source sur les guides déjà compilés, et réutiliser les sections natives de l'axe mesuré ; échantillonnage et nombre total de points bornés | Ces contrôles ne définissent pas une entrée ni une trajectoire de prise physique. Ils restent exploratoires ; aucun waypoint de prise n'est ajouté comme donnée approuvée par défaut |
| Libération des supports | Supports temporaires effectivement déclarés, franchissement mesuré de l'ouverture ou fin de fermeture déclarée | Les templates actuels ont des listes de supports vides. Une prise temporaire nécessaire à l'enfilage doit être explicitement dérivée et tracée ; aucune date de libération ne peut être inventée |

Les poignets libres sont des candidats à un passage fermé après les coutures
permanentes des manchettes. La ceinture reste une bande avec fermeture sur
elle-même ; son périmètre extérieur ne devient pas une ouverture de taille.
Les devants libres et les raccords amovibles de la capuche doivent conserver
leur fonctionnement approuvé. Le contrôle actuel de `blender/dressing.py`
accepte des boucles de passage fermées par des raccords permanents ; il ne
décrit pas encore l'enroulement d'une bande ouverte ni toutes les méthodes de
mise en place d'un vêtement ouvert.

Les modules [dressing_derivation](../a3d/dressing_derivation.py) et
[dressing_paths](../a3d/dressing_paths.py) reconstruisent les templates depuis
le dossier, les packages, le plan et les guides exacts, puis remesurent les
sections sur le profil et la triangulation corporelle cités. Les descriptors
`dressing_derivation_descriptor(project, specification_path)` et
`dressing_paths_descriptor(project, specification_path)` restent des interfaces
internes de lecture. Le second reconstruit la dérivation : un JSON modifié puis
réempreinté ne suffit pas à changer une politique source.

L'inspection pure des sources principales v7 a dérivé quatre méthodes : deux
poignets `CLOSED_CUFF`, un vêtement `OPEN_FRONT` et la ceinture `OPEN_WRAP`.
Les quatre régions corporelles ont des sections mesurées et 606 points de
contrôle, dont 594 points UV, ont été mappés sans dépassement du guide, à un
pas déclaré de 0,5 cm. Deux ordres
des bras restent compatibles ; aucun n'est sélectionné par tri lexical. La
méthode capuche/empiècements n'était pas encore implémentée dans cette inspection.
Le supplément de peau v3 fournit maintenant les domaines projetés conservateurs
des mains ; ils doivent être liés aux instructions par leur politique exacte et
remesurés. Ils ne prouvent pas le passage des poignets. Le résultat est
`NEEDS_DATA`, `executable=False`,
`trajectory=None`, `EXPLORATORY_DRESSING_GEOMETRY_ONLY` : ni déplacement du corps,
ni retrait de supports, ni Cloth. L'exécution du vêtement principal reste à
qualifier avec une entrée et des trajectoires de supports explicitement
sourcées, ainsi que sa construction réelle et sa continuité complète.

La dérivation prend maintenant en charge `OPEN_HOOD_YOKE` et
`OPEN_DETACHABLE_YOKE`. Elle partitionne les pièces par les seules coutures
permanentes : capuche gauche/droite et empiècement supérieur forment une unité,
l'empiècement inférieur reste distinct. Les bords libres `face-free` et les
devants déclarés constituent les contrôles d'ouverture ; les bords `neck-base`
cousus sont conservés comme ancrages source séparés. Aucun raccord amovible
ne devient une couture permanente.

Le [contrat de dérivation](../schemas/dressing-derivation.schema.json) accepte
`method_configurations`. Chaque déclaration contient `method_id`, `mode`, une
`source_ref` exacte et les `source_link_states` des véritables relations du
package. Le document cité doit contenir exactement cette configuration sans
sa référence. Les modes de capuche proposés sont `RAISED_OPEN_HOOD` et
`LOWERED_OPEN_HOOD` ; le mode d'empiècement est `OPEN_SHOULDER_YOKE`. Cette
première capacité exige `OPEN` pour chaque fermeture et attache concernée,
sans ajouter de ressort ou de soudure. Une relation inventée, omise, répétée,
fermée ou incompatible avec l'unité source est refusée. Une configuration
absente conserve la proposition `NEEDS_DATA` ; aucun mode n'est choisi.

La [proposition sur les sources principales v8](G:/projets/atelier-3d/work/garment-automation-v1/program-main-dressing-method-proposal-v1/diagnostic.json)
dérive six méthodes et six régions mesurées : 1 086 points de contrôle au pas
source de 0,5 cm, dont 122 ancrages de col, avec les sources et SQLite conservés.
Les sections cou→centre de tête et poitrine→cou ne couvrent pas la tête entière
et ne prouvent pas un passage. Le mode choisi reste une intention déclarée ;
les prises, leurs trajectoires, leur retrait et les contraintes de fin doivent
être sourcés séparément. Le descriptor refuse avant simulation une configuration
ou une région nécessaire manquante, et interdit de prendre l'empiècement
inférieur au titre de la méthode de l'unité supérieure. Le kernel conserve
dans son reçu les configurations et les états source utilisés. Ce support
géométrique a des tests portables ; la capuche et les empiècements n'ont pas
encore leur qualification native sur le vêtement principal.

L'opération `run_dressing_program` reçoit exactement `profile_path`. Son
descriptor `dressing_execution_descriptor(project, profile_path)` reconstruit
les contrôles, vérifie le package et les contours source, puis authentifie le
corps fixe mesuré et les éventuelles couches animées. Le profil cite des
instructions explicites : configuration d'entrée, prises sur des bords nommés,
points lus dans des fichiers source exacts, intervalles successifs par méthode,
frames de retrait et contraintes de fin. Une donnée nécessaire absente retourne
`NEEDS_DATA` avant la création d'une scène ou le lancement de Cloth.

Pour `GARMENT_CANDIDATE`, le candidat doit conserver la continuité complète de
ses groupes natifs actuels, et le composant exécuté doit figurer dans la fiche
de classification et d'aisance numériquement revue, avec ses propres contrôles
mesurés. Une liste de composants ne remplace pas ces contrôles. Le corps de cette fiche
doit être celui des contrôles. Un poignet fermé exige aussi un domaine de main
sourcé ; l'enveloppe projetée conservatrice ne devient ni un tour anatomique
ni une preuve de passage physique.

Le kernel vérifie les contacts de l'entrée avant Cloth, observe chaque frame
entière, mesure les poids natifs évalués des prises, leurs cibles et leur retrait, puis
réévalue les colliders intermédiaires et les croisements relatifs. Les
surfaces textiles intermédiaires restent des interpolations des observations,
sans revendication de dynamique Cloth exacte. Il réouvre aussi sa copie
statique finale et remesure les contraintes source. Un résultat complet porte
`DRESSING_SEQUENCE_SAMPLES_COMPLETE` / `SAMPLED_SOURCE_DRESSING_SEQUENCE`, avec
fitting, convergence de drapé et comportement de fermeture non qualifiés.
Le [scénario natif](../tests/native_dressing_executor.py) teste une petite
trajectoire source sur une bande de fixture. Les essais v2 et v3 ont observé
deux images puis refusé l'image 3 : une prise de poids 1 restait à sa cible
précédente, avec 0,0050006 cm d'erreur contre 0,001 cm autorisé. L'Action native
linéaire de v3 n'a pas résolu ce décalage. Le
[diagnostic natif](automation-validation.md#ce-qui-reste-à-qualifier) a localisé
une sortie Cloth figée avec un cache périmé malgré des entrées animées correctes.
Le correctif prépare aussi les poids dans une Action native constante avant
Cloth : les groupes et le mesh source ne sont plus réécrits à chaque image.
Le retrait doit correspondre exactement au calendrier et un cache périmé est
refusé. Deux Actions natives distinctes conservent les trajectoires linéaires
et les poids constants ; leur identité est contrôlée avant et pendant Cloth.
Le [replay v5](G:/projets/atelier-3d/work/garment-automation-v1/program-native-dressing-v5/case/receipt.json)
a observé les cinq images sans cache périmé, avec une erreur maximale de prise
de 0,000001431 cm contre 0,001 cm autorisé, un retrait réel aux images 4–5 et
une réouverture géométrique exacte de la copie finale. Le budget court reste
`INCOMPLETE` sans artefact ; les instructions absentes restent `NEEDS_DATA`
sans exécution. Cette preuve concerne une bande de fixture éloignée du corps,
avec 0,01 cm de déplacement. Aucun de ces essais ne qualifie l'enfilage du
vêtement principal.

Le corps fixe peut provenir d'une mesure native locale ou d'une introduction
native canonique. Dans le second cas, le descriptor relit le contexte exact,
le reçu source, les identités profil/pose/géométrie et le hash de peau réellement
évaluée. Les fichiers source seuls ne remplacent pas l'événement d'introduction.

## Clips textiles observés

L'opération native `run_garment_motion` reçoit `profile_path`. Son profil lie le
candidat textile, sa recette, un reçu canonique de mouvement du corps, les
couches internes éventuelles, les Actions et leurs temps exacts. Les images
entières exécutent Cloth progressivement ; les contrôles entre images évaluent
à nouveau le corps et les couches, avec interpolation textile linéaire déclarée.
Les témoins de croisement relatif complètent les contrôles aux instants
échantillonnés sans prétendre à une détection continue exhaustive.

Un clip qui couvre tout son intervalle peut enregistrer les géométries Cloth
observées dans des clés de forme natives sur une copie, puis réouvrir cette
copie et comparer ses échantillons. Ce cache conserve les Actions et ressources
sourcées ; il n'est pas un redémarrage exact de la dynamique physique. Une
couverture insuffisante reste `INCOMPLETE` et ne produit pas de clip complet.
La [campagne L8 v3](automation-validation.md#mouvement-textile-l8--couches-et-obstacles-évalués)
porte sur des coupons génériques sur les deux bases. Elle ne qualifie pas le
mouvement habillé ni le fitting du vêtement principal.

La réutilisation d'un clip `GARMENT_CANDIDATE` vérifie aussi les empreintes des
modules physiques, de contact, de continuité, de peau et de cache réellement
chargés. Un handler absent ou changé exige une nouvelle preuve native. Le
transport historique `TEST_ONLY` garde ses échantillons exacts sans attribuer
une qualification de production ; une évolution étrangère du dispatcher
n'invalide pas seule leur géométrie observée.

## Rendu des clips pour revue humaine

L'opération `render_motion_review` reçoit `profile_path`. Son profil
[review-motion](../schemas/review-motion.schema.json) référence un profil d'export
exact et ses reçus natifs canoniques. Il conserve tous les clips, objets,
Actions simultanées et cadence source. Les rendus couvrent chaque image entière
du clip et conservent les PNG avec leurs empreintes. L'encodage H264 utilise
FFmpeg dans Blender lorsque sa configuration RNA le permet, puis recharge le
film pour vérifier son nombre d'images, ses dimensions et sa cadence.

`NEUTRAL` présente la géométrie avec un affichage sobre. `MATERIALS` conserve
UV, images et shaders source, avec un éclairage de revue créé dans la scène
temporaire. La caméra couvre les limites mesurées de tout le clip ; sa
projection est contrôlée avant les rendus. Les budgets comptent les images PNG
et les images d'encodage. L'évaluation des sommets est aussi bornée : dix
millions de sommets-images par défaut, ou la valeur explicitement déclarée.
Un codec absent ou un budget épuisé laisse `INCOMPLETE` et conserve les médias
déjà produits. Les contrôles portables du module sont exécutés. Le premier
essai natif v2 a conservé cinq PNG puis s'est arrêté `INCOMPLETE` à l'encodage.
Le sélecteur a été corrigé pour Blender 5.2 : `media_type=VIDEO` précède
`file_format=FFMPEG`, avec vérification du build et des paramètres effectivement
retenus. Le [replay natif v3](automation-validation.md#rendu-vidéo-natif)
a produit puis relu trente PNG et six H264 sur la composition de fixture
canonique, en modes `NEUTRAL` et `MATERIALS`. Les pixels gardent une portée
de revue de fixture, sans acceptation du vêtement principal.

Un résultat `REVIEW_MEDIA_RENDERED` reste `PIXELS_ONLY`. Il établit les fichiers
produits, sans décider leur qualité artistique ni accorder fitting ou
acceptation du vêtement. Le reload du H264 vérifie des métadonnées natives ; il
ne prétend pas à une identité de pixels avec les PNG, car l'encodage est avec
perte. La revue humaine doit citer les images et films effectivement examinés.

## ComfyUI et soumission incertaine

`studio_prepare_workflow_variant(project_root, template_id, variant_id, parameters)`
prépare une variante immuable, ses paramètres typés, son diff et la compatibilité
fournisseur observée. Le workflow et ses modèles doivent exister sur le backend
cible. Préparer une variante ne lance pas de job.

Une soumission utilise un `request_key` stable. Si son résultat est incertain,
appeler `studio_reconcile_comfy_job(project_root, job_id)` ou laisser le run
réconcilier son job possédé. La récupération exige une preuve fournisseur unique
et corroborée. Ne pas soumettre de nouveau le même travail avec une nouvelle
clé, ni traiter une histoire absente comme une réussite.

Le programme initial accepte l'opération ComfyUI `submit_workflow` avec
`component_id`, `workflow_id` et `parameters`. Il conserve le job connu, vérifie
sa fin puis collecte les sorties locales avec leurs empreintes. Une fin
fournisseur sans fichiers vérifiés reste en attente de sorties. La fin du job
ne qualifie ni la géométrie de l'asset ni son acceptation. L'arrêt contrôlé
n'envoie pas d'interruption globale à ComfyUI.

## Inventaire des interfaces publiques

Le checkout expose 43 outils après l'ajout du préparateur de variantes de patrons. Les
descriptions et schémas exacts se trouvent dans [tools.py](../a3d/tools.py).

| Domaine | Outils |
| --- | --- |
| Projet et diagnostic | `studio_doctor`, `studio_create_project`, `studio_project_status` |
| Corps cible | `studio_mannequin_catalog`, `studio_select_catalog_body`, `studio_prepare_body_target` |
| Méthode et construction | `studio_route_component`, `studio_propose_pipeline`, `studio_resolve_route`, `studio_compile_production_dossier`, `studio_build_construction_board`, `studio_prepare_exploded_view`, `studio_register_exploded_view`, `studio_check_pipeline` |
| Packages | `studio_build_package`, `studio_validate_package`, `studio_extract_package`, `studio_bind_package`, `studio_accept_reconstruction` |
| Preuves et cycle | `studio_record_evidence`, `studio_record_human_decision`, `studio_transition` |
| Opérations natives | `studio_blender_operation` |
| Journal | `studio_create_run`, `studio_next_run_step`, `studio_run_status`, `studio_request_run_stop` |
| Matière et enfilage | `studio_compile_material_bench`, `studio_compile_dressing_plan` |
| Variante de patrons | `studio_prepare_pattern_ease_variant` |
| Groupes textiles | `studio_plan_garment_assembly` |
| Variantes et récupération ComfyUI | `studio_prepare_workflow_variant`, `studio_reconcile_comfy_job` |
| Fournisseur ComfyUI | `comfy_health`, `comfy_capabilities`, `comfy_validate_workflow`, `comfy_upload_image`, `comfy_upload_mask`, `comfy_submit_workflow`, `comfy_run_template`, `comfy_job_status`, `comfy_job_outputs`, `comfy_cancel_job` |

Les hooks internes de début/checkpoint/résultat ne sont pas des outils publics
d'import de preuve. La compilation et les appels de suivi gardent les admissions
du projet, les décisions humaines et les autorisations d'exécution.

## Projections et artefacts des étapes

Les futurs reçus natifs archivent les projections de scène de travail et
l'index des pièces dans des copies liées à leur tentative exacte. Les fichiers
de résultat restent immuables ; une vue de travail modifiée ou supprimée est
exposée séparément et ne remplace jamais cette preuve. Les références des
étapes dépendantes doivent désigner les artefacts de résultat, dont les scènes
maîtres, plutôt qu'une projection courante.

Une archive seule ne crée pas de résultat canonique. La réconciliation d'un
RESULT_READY déjà enregistré vérifie son résultat exact et ses archives sans
réexécuter la mutation. Sans reçu enregistré, la voie de récupération conserve
les références strictes et les frontières de checkpoint. Les anciens reçus
ne sont pas réécrits ni admis par cette nouvelle capacité.

## Couplage explicite des guides

Une politique de guides peut déclarer `source_seam_coupling` pour un composant :
pièces sélectionnées, subdivisions, budgets et `recipe_ref` exact. La politique
conserve aussi le digest du contenu de la recette. Le wrapper projet vérifie
ses octets avant et après reconstruction ; le consommateur des mesures les
revérifie après calcul et conserve la référence dans ses entrées.

Le [noyau de couplage](source-seam-coupling.md) emploie uniquement les relations
permanentes du package source et leurs paramètres. Les coutures externes restent
déclarées non traitées. Cette correction d'une proposition de guide ne dispense
ni du contrôle métrique, ni des contacts, ni des décisions de couverture.
