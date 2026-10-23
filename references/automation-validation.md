# Preuves et qualification de l'automatisation

État documentaire du 4 octobre 2026, pendant l'intégration du checkout de
développement. Les essais ci-dessous ont leur propre identité de code,
entrées et fichiers. Ils ne valent pas validation d'une modification ultérieure,
publication de préversion ou vérification d'une nouvelle installation.
Voir [le runtime](automation-runtime.md) et [le programme approuvé](automation-program.md).

## Résultats natifs disponibles

Les liens `G:` pointent vers des preuves locales conservées hors du package
portable. Sur un autre poste, il faut disposer des reçus et de leurs fichiers
pour vérifier les empreintes et reproduire la campagne.

| Campagne | Résultat établi | Portée et limites |
| --- | --- | --- |
| [Corps cible v2](G:/projets/atelier-3d/work/garment-automation-v1/program-native-body-target-v2/receipt.json) | `NATIVE_BODY_TARGET_PASS`, deux bases séparées à 180 cm, mesures natives, export et réouverture | Copies géométriques mesurées, source conservée ; ni Cloth ni fitting |
| [Contrôles corporels v2 — L3](G:/projets/atelier-3d/work/garment-automation-v1/program-native-body-controls-v2/receipt.json) | Deux `NATIVE_TORSO_CONTROLS_PASS` ; poitrine et hanches +3 %, taille −3 %, régions protégées, proportions de section et réouverture contrôlées | `TEST_ONLY`, `TORSO_GIRTH_CONTROLS_GEOMETRY_ONLY` ; corps principal inchangé, rig et fitting non exécutés |
| [Mouvement du corps v7](G:/projets/atelier-3d/work/garment-automation-v1/program-native-body-motion-v7/receipt.json) | `NATIVE_BODY_MOTION_PASS`, marche/flexion du coude/élévation du bras sur deux bases ; 49 échantillons évalués par clip, soit six clips | `BODY_MOTION_SAMPLES_ONLY` ; aucun contact vêtement, Cloth ou fitting ; revue des axes d'os encore requise |
| [Vues comparables v1](G:/projets/atelier-3d/work/garment-automation-v1/program-native-review-v1/receipt.json) | Huit images natives : face/profil/dos/trois-quarts pour deux bases | `REVIEW_ARTIFACTS_ONLY` ; le reçu de rendu ne contient pas de décision artistique ou anatomique |
| [Banc matière v3 — L7](G:/projets/atelier-3d/work/garment-automation-v1/program-native-material-bench-v3/receipt.json) | Pipeline natif `PASS`, six coupons mesurés ; résultat de comparaison `FAIL`, run `NEEDS_CORRECTION` ; une convergence réelle, quatre budgets incomplets et un refus métrique | `COUPON_ONLY` ; aucun choix automatique de matière, aucun changement du vêtement ou de son fitting |
| [Mouvement textile v3 — L8](G:/projets/atelier-3d/work/garment-automation-v1/program-native-garment-motion-v3/receipt.json) | `TEST_ONLY_GARMENT_MOTION_FIXTURES_COMPLETE` sur deux bases ; vrais clips Cloth de cinq images, couche interne animée, contrôles entre images et caches natifs réouverts | Coupons génériques ; cache de géométrie observée avec interpolation linéaire, aucune acceptation du vêtement complet, du fitting ou d'une reprise physique exacte |
| [Prise et retrait textile v5 — L7](G:/projets/atelier-3d/work/garment-automation-v1/program-native-dressing-v5/case/receipt.json) | `TEST_ONLY_DRESSING_SOURCE_GRIP_FIXTURE_COMPLETE` ; cinq images Cloth, précision de prise contrôlée, retrait aux images 4–5, artefact réouvert ; budget court `INCOMPLETE` et instructions absentes `NEEDS_DATA` | Bande de fixture à 50 cm du corps ; ni passage réel sur le corps, ni fermeture, drapé final, fitting ou enfilage du vêtement principal |
| [Revue vidéo v3](G:/projets/atelier-3d/work/garment-automation-v1/program-native-motion-review-v3/receipt.json) | `TEST_ONLY_NATIVE_MOTION_REVIEW_MEDIA_PASS`, trente PNG et six H264 natifs relus, trois clips en affichages `NEUTRAL` et `MATERIALS` | `PIXELS_ONLY`, composition canonique de fixture ; aucun fitting, jugement artistique ou produit complet admis |

Les contrôles corporels mesurent un résidu maximal de circonférence inférieur à
0,009 cm dans cette campagne. La source, les régions protégées et la stature
restent conservées. Les cas impossibles et les budgets s'arrêtent respectivement
avec `STAGNATED` et `BUDGET_EXHAUSTED`. Ces résultats décrivent le domaine testé,
pas une garantie pour toutes les anatomies ou toutes les cibles.

Les clips v7 ont été exportés et réouverts, et une mutation de l'Action a été
refusée. Ils qualifient les échantillons du corps générique et leur identité
rig/poids/Action. Ils ne qualifient pas le mouvement d'un vêtement habillé ni
une absence de contact continue entre tous les instants.

La base principale choisie humainement est `body.realistic-male`, à 180 cm.
La décision sur les proportions examinées est distincte du reçu de rendu et
doit rester liée aux preuves et au message humain correspondant. Les cibles
des essais L3 ne sont pas devenues les mensurations de ce corps principal.

Les campagnes échouées de mouvement restent conservées. Corriger leurs causes
et obtenir un résultat v7 n'efface pas leurs reçus ; leurs labels ne sont pas
transférés à une campagne suivante.

## Banc matière L7 : comparaison établie, recette non retenue

La [comparaison v3](G:/projets/atelier-3d/work/garment-automation-v1/program-native-material-bench-v3/project/compiled/native/comparison.json)
utilise des seeds `supported-v2` déclarés avant l'essai. Les recettes d'un même
programme diffèrent uniquement par `structural_damping`, 1 ou 20. Les coupons
gardent leurs mêmes géométries, supports, colliders, métriques et budgets :
24 images/s, 240 images au maximum, 45 secondes par cas, observation minimale
de 24 images, fenêtre de huit intervalles et seuil de 0,01 cm/s.

Le coupon de flexion mesure 10 × 10 cm et maintient son premier bord. La couture
relie deux panneaux distincts de 10 × 10 cm avec un écart initial de 0,1 cm,
déjà dans la tolérance de raccord direct de 0,15 cm. Elle teste la réponse d'une
couture admissible, sans qualifier sa fermeture depuis un grand écart. Le coupon
de contact démarre à 0,6 cm du support fermé et maintient son premier bord.
Tous les contacts initiaux ont été réellement admis, sans modifier la réserve
de contact. Les cas historiques v2 restent conservés avec leurs refus.

| Cas | Résultat | Dernière image | Vitesse maximale du dernier intervalle observé, cm/s | Observation déterminante |
| --- | --- | --- | --- | --- |
| Flexion, amortissement 1 | `INCOMPLETE` | 240 | 3,88098 | Métrique et contacts conformes ; convergence non obtenue dans le budget |
| Flexion, amortissement 20 | `INCOMPLETE` | 240 | 25,40542 | Métrique et contacts conformes ; oscillations encore présentes |
| Couture, amortissement 1 | `PASS` du coupon | 24 | 0,00002719 | Convergence mesurée ; écart de couture final 0,01154 cm, fenêtre complète sous le seuil |
| Couture, amortissement 20 | `INCOMPLETE` | 240 | 10,27771 | Écart de couture conforme mais vitesse non convergée |
| Contact, amortissement 1 | `INCOMPLETE` | 240 | 4,45780 | Surface hors pénétration ; mouvement encore mesurable |
| Contact, amortissement 20 | `FAIL` | 102 | 284,28944 | Étirement principal maximal 8,81857 sur la face source 41 ; arrêt métrique immédiat |

Les temps par cas vont de 3,30 à 28,85 secondes, tous sous 45 secondes. Les
quatre états incomplets résultent du nombre maximal d'images, et non d'un
timeout. La vitesse du cas refusé inclut sa dernière image observée ; le
moniteur de convergence n'admet pas cette image qui échoue à la métrique.

Les reçus natifs établissent une masse de 0,0000833333 kg par sommet. La recette
cite une densité de 0,3 kg/m² et une masse de référence d'amortissement de
0,001 kg : le facteur appliqué est 1/12. Les quatre canaux d'amortissement
structurel natifs valent donc 0,0833333 ou 1,6666667, et l'amortissement d'air
natif reste 0,000833333. Ces valeurs correspondent à celles effectivement
assignées ; les contrôles contre l'écrêtage RNA n'ont détecté aucun écart.

L'augmentation de l'agitation avec la valeur 20 est une observation de ce banc.
Elle ne démontre pas à elle seule la cause numérique du solveur. Le faible
amortissement d'air est une hypothèse à distinguer de la preuve. La capacité
établie est celle d'un banc comparable qui mesure une convergence et conserve
les défauts et budgets incomplets. Aucune recette n'est retenue pour le produit.
Une future expérience de matière doit citer des valeurs et une provenance
technique explicites, modifier un seul facteur, conserver les contrôles et
passer ensuite les essais propres au candidat de production.

## Mouvement textile L8 : couches et obstacles évalués

Sur chacune des deux bases, la campagne v3 a exécuté le coupon textile et un
coupon extérieur contre la couche interne réellement animée, de l'image 1 à
l'image 5. Les colliders du corps et de la couche sont évalués aux instants de
contrôle entre images. Chaque clip complet dispose d'un cache natif de clés de
forme réouvert et comparé aux géométries observées. La géométrie textile entre
images est explicitement interpolée de façon linéaire ; le corps conserve son
Action native réévaluée.

Le témoin d'obstacle conserve des extrémités sans contact mais refuse son passage
au milieu de l'intervalle, avec géométrie native réellement évaluée et témoin
de croisement relatif. Les budgets de deux images restent `INCOMPLETE` et ne
produisent aucun artefact de clip complet. Le reçu atteste aussi la conservation
de la scène source. Les échecs v2 de chargement restent historiques ; leur
correction ne transfère aucun résultat vers v3.

Ce résultat qualifie ces fixtures textiles et leur cache observé. Il ne qualifie
ni le vêtement principal à 15 pièces, ni son enfilage, ni son fitting, ni une
absence de contact exhaustive à tous les instants. Le cache réouvert n'est pas
une reprise exacte des vitesses et de la dynamique Cloth.

## Rendu vidéo natif

La [campagne v3](G:/projets/atelier-3d/work/garment-automation-v1/program-native-motion-review-v3/receipt.json)
a rendu les cinq images entières de chacun des trois clips en deux affichages,
soit trente PNG et six films H264. Les films ont été réellement rechargés pour
vérifier cadence, dimensions et nombre d'images. Le mode `MATERIALS` conserve
les ressources source ; les scènes temporaires et fichiers source ont été
préservés. La preuve concerne les médias de la composition canonique de fixture,
avec `PIXELS_ONLY` et revue artistique requise, sans fitting ou acceptation du
vêtement principal. L'encodage H264 est avec perte ; sa relecture ne déclare
pas une identité de pixels avec les PNG.

## Ce qui reste à qualifier

Le dossier et les guides des 15 pièces textiles peuvent être compilés depuis
les sources approuvées. Leur complétude documentaire ne constitue pas une
construction Blender admise. À cet état, aucune acceptation du vêtement complet
avec sa boucle rigide n'est accordée.

Le [diagnostic géométrique des sources principales v7](G:/projets/atelier-3d/work/garment-automation-v1/program-main-dressing-input-diagnostic-v1/diagnostic.json)
a dérivé deux méthodes de poignet fermé, un devant ouvert et une bande à
enrouler, quatre domaines avec sections natives mesurées et 606 points de
contrôle, dont 594 points de bords UV, au pas déclaré de 0,5 cm. Les sources ont été relues et leurs
empreintes vérifiées sans écriture dans le projet. L'origine locale du corps
est son véritable événement natif d'introduction 47. Le supplément de peau v3
fournit des enveloppes projetées conservatrices des mains, d'environ 36,74 cm
de périmètre, avec passage physique non qualifié. Les sections initiales des
hauts de bras restent ouvertes ou ramifiées ; ce défaut n'est pas masqué.

Ces contrôles v7 restent `NEEDS_DATA` : méthode capuche/empiècements alors non
implémentée, ordre des deux bras ambigu, entrée continue admissible et prises
natives manquantes. Les candidats de préparation v7 demandent encore une
correction. L'aisance numérique et le recouvrement du devant restent à définir
et revoir ; la revue de silhouette ample du manteau ne couvre ni ces nombres,
ni la ceinture ou la capuche. Les contrôles source ne constituent pas une
trajectoire physique ni une nouvelle preuve de fitting.

La [proposition géométrique sur les sources v8](G:/projets/atelier-3d/work/garment-automation-v1/program-main-dressing-method-proposal-v1/diagnostic.json)
ajoute les méthodes `OPEN_HOOD_YOKE` et `OPEN_DETACHABLE_YOKE` depuis les bords
et les vrais raccords du package. Elle conserve séparément l'unité permanente
capuche gauche/droite + empiècement supérieur et l'empiècement inférieur.
Elle remesure six régions corporelles ; ses 1 086 points comprennent 1 068
contrôles UV, dont 122 ancrages permanents du col, et 18 contrôles d'axe
corporel. Aucun bord n'est extrapolé hors de son guide. SQLite et les références
source ont été vérifiés identiques avant/après cette lecture.

Cette extension conserve `NEEDS_DATA` / `NOT_EXECUTED`, avec choix relevé/abaissé
non sélectionné, véritables fermetures et attaches à déclarer ouvertes, ordre
des bras ambigu et entrée/prises physiques manquantes. Les sections
cou→centre de tête ne deviennent ni une enveloppe de tête complète ni un
passage admissible. Les tests portables couvrent les unités permanentes, les
deux modes ouverts, le refus de relations inventées/fermées/dupliquées, la
référence exacte de la déclaration, la distinction bords libres/ancrages et
les données manquantes avant exécution. Ils ne constituent pas un essai
physique de capuche ou d'empiècement.

Le [reçu d'enfilage de fixture v3](G:/projets/atelier-3d/work/garment-automation-v1/program-native-dressing-v3/case/project/.a3d/outputs/dressing-ddbc5354956949e7833e5aa0f6744741/receipt.json)
conserve `NEEDS_CORRECTION`, deux images observées et le refus de l'image 3.
La prise native de poids 1 présente 0,0050006008 cm d'écart contre une limite
de 0,001 cm. Les deux premières erreurs sont inférieures à cette limite.
L'Action native linéaire n'a pas supprimé le décalage constaté dans l'essai v2.
La cause restait à localiser avec le
[diagnostic du driver](../tests/native_dressing_driver_diagnostic.py), qui
compare les entrées pré-Cloth et deux lectures de sortie avec et sans scène
intermédiaire. Aucun seuil, budget ou paramètre physique n'est assoupli.
Le [diagnostic natif à trois branches](G:/projets/atelier-3d/work/garment-automation-v1/program-native-dressing-driver-diagnostic-v1/case/diagnostic.json)
a ensuite observé cinq images dans chaque branche, avec conservation des
sources et de la scène. Les Keys, l'Action, le slot, le temps du graphe et les
entrées pré-Cloth sont corrects ; à l'image 3, cette entrée présente seulement
0,000000229 cm d'erreur. La sortie Cloth conserve le hash de l'image 2 jusqu'à
l'image 5, avec un cache `is_outdated=True` et deux images en mémoire. La seconde
scène et l'ordre de lecture pré-Cloth ne changent pas ce résultat.

Les écritures Python répétées de poids et de données mesh sont corrélées à
cette invalidation. Le [code RNA officiel Blender 5.2](https://raw.githubusercontent.com/blender/blender/blender-v5.2-release/source/blender/makesrna/intern/rna_object.cc)
montre que `VertexGroup.add/remove` marque la géométrie à recalculer. Le
correctif prépare désormais les poids et retraits dans une Action native
constante et des modificateurs de poids avant Cloth ; il conserve les groupes
source pendant le cache et contrôle leurs poids réellement évalués. La
[définition RNA officielle du mélange de poids](https://raw.githubusercontent.com/blender/blender/blender-v5.2-release/source/blender/makesrna/intern/rna_modifier.cc)
décrit cette surface native. Le diagnostic n'accorde aucune qualification.

L'essai v4 a ensuite refusé une identité d'Action/Key avant sa première
observation. Il reste conservé ; le driver crée désormais deux Actions natives
distinctes pour les trajectoires linéaires et les poids constants, et conserve
les champs attendus/observés en cas de divergence. Le
[replay natif v5](G:/projets/atelier-3d/work/garment-automation-v1/program-native-dressing-v5/case/receipt.json)
a terminé en 97,119 s avec le snapshot source32
`175267535ad30e5ddc5aa38be1bf7286f80d115442c7bdf5a8e31d02028b26e4`.
Ses cinq images gardent un cache non périmé. Les erreurs de la prise de poids 1
sont respectivement 0,000001431, 0,000000601 et 0,000000229 cm aux images 1–3,
contre le seuil conservé de 0,001 cm. La prise est absente des poids réellement
évalués aux images 4–5 ; les pins fonctionnels restent présents. Le fichier
Blender sauvegardé, de hash
`ecfa6157fff5ba06a286d9d66cf5312dc1f274ae388703849e096c1e7f87e8e6`,
est réouvert avec un écart géométrique mesuré de 0 cm. Les quatre intervalles
sont aussi contrôlés dans la portée d'interpolation déclarée.

Le cas de budget limité à deux images retourne `INCOMPLETE` sans artefact
final ; le cas sans instructions retourne `NEEDS_DATA` / `NOT_EXECUTED`.
Ce replay démontre la correction dans l'appareil testé. Il ne tranche pas
isolément la contribution de chaque correction, et ne qualifie pas un passage
sur le mannequin : la bande de 2 × 8 cm est située à 50 cm de sa peau et la
trajectoire de prise ne parcourt que 0,01 cm. La portée reste
`TEST_ONLY_SOURCE_GRIP_APPARATUS`, fitting et acceptation produit non accordés.

Le [reçu natif de rendu vidéo v2](G:/projets/atelier-3d/work/garment-automation-v1/program-native-garment-motion-v3/project/.a3d/outputs/motion-review-a7d63f96039d4cf485ec5fc98527e070/receipt.json)
conserve cinq PNG du premier clip et un état `INCOMPLETE` /
`MOVIE_CODEC_UNAVAILABLE`, sans film produit. La sélection du domaine vidéo
Blender 5.2 a ensuite été corrigée et testée portablement ; cette correction
ne transforme pas le reçu v2 en réussite. Le replay v3 dispose de sa propre
preuve ci-dessus. L'examen humain de ses pixels demeure distinct du reçu.

| Porte de qualification | Preuve requise sur le candidat exact | État à cette fiche |
| --- | --- | --- |
| Construction complète | 15 pièces textiles + boucle, identités et raccords déclarés, source et topologie conservées | À réaliser sur le vêtement complet |
| Placement et enfilage | Ouvertures, trajets, contacts et métrique conformes, couches prévues, positions réellement évaluées | Placement admissible et enfilage physique non qualifiés |
| Physique et drapé | Essais puis Cloth local/complet réellement exécutés, convergence et budgets, seuls raccords permanents consolidés | Non qualifiés sur ce produit |
| Fitting | Corps principal approuvé, pose/collider exacts, mesures homologues et aisance, supports transitoires retirés | Non qualifié |
| Mouvement habillé | Clips complets avec collider animé et contrôles de contacts, métrique, coutures et liberté des pans | Coupons génériques avec corps et couche animés testés ; vêtement complet non qualifié |
| Revue artistique | Pixels et vidéos du vêtement exact, comparaison avec les références et décision humaine explicite | Non exécutée pour l'acceptation complète |
| Livraison | Scène et ressources réouvertes, export/réimport selon profil, package versionné puis publication et installation vérifiées | Nouvelle livraison non réalisée |

Les campagnes L6, fournisseur ComfyUI et finition/export sont
suivies dans [le programme d'intégration](automation-program.md). Une campagne
en cours ou un fournisseur récupéré après interruption n'est pas un nouveau
PASS. Le présent document n'annonce pas leur résultat avant reçu exact.

## Contrôles portables pertinents

Le [reçu d'intégration du 4 octobre](automation-evidence-20261004.json) relie
les 795 tests, les 21 contrôles de contrats et la campagne native textile v14
à la source figée 37 et au code commité. Sa portée est le logiciel en
développement et les cas de test ; le fitting et l'acceptation de MAIN restent
explicitement non qualifiés.

Les tests Python vérifient calculs, contrats, refus et journaux. Ils ne lancent
pas implicitement un backend Blender/ComfyUI et ne remplacent pas une campagne
native. Exécuter les suites touchées sur le checkout intégré, puis conserver le
résultat et l'identité de ce candidat.

| Domaine | Suite | Ce qu'elle distingue |
| --- | --- | --- |
| Stature, mesures et cibles | [body_dimensions](../tests/test_body_dimensions.py), [body_target](../tests/test_body_target.py), [body_controls](../tests/test_body_controls.py) | Cadre, source immuable, cibles et domaine borné, résidus et régions protégées |
| Peau des épaules et guides | [shoulder_surface](../tests/test_shoulder_surface.py), [garment_guides](../tests/test_garment_guides.py) | Triangulation et source exactes, repères mesurés, couverture et lacunes |
| Compilation et placement | [production_dossier](../tests/test_production_dossier.py), [placement_solver](../tests/test_placement_solver.py), [textile_executor](../tests/test_textile_executor.py) | Relations approuvées, exploration non admise, seuils finaux et groupes |
| Journal et interruption | [runs](../tests/test_runs.py) | Idempotence, fichier périmé, reçu arbitraire refusé, crash, rollback, restauration exacte et réconciliation sans replay |
| Matière et enfilage | [material_bench](../tests/test_material_bench.py), [dressing](../tests/test_dressing.py), [dressing_derivation](../tests/test_dressing_derivation.py), [dressing_paths](../tests/test_dressing_paths.py), [dressing_executor](../tests/test_dressing_executor.py) | Un seul facteur, frontières et guides sourcés, domaines manquants, aucune entrée inventée, dossier falsifié ou budget refusé ; prises source, séquençage, poids/retrait natifs et contraintes observées |
| Variantes et fournisseur | [workflow_variants](../tests/test_workflow_variants.py), [jobs](../tests/test_jobs.py) | Compatibilité, clé stable, soumission incertaine, outputs exacts |
| Mouvement et livraison | [motion_profiles](../tests/test_motion_profiles.py), [garment_motion](../tests/test_garment_motion.py), [asset_export](../tests/test_asset_export.py), [delivery](../tests/test_delivery.py), [review_motion](../tests/test_review_motion.py) | Identité des clips et ressources, provenance canonique, couches animées, témoins de croisement, couverture, cadrage et budgets |

Les tests du journal couvrent l'interruption avant le retour, le crash après
`blender_started` avant son hook de checkpoint, le résultat sauvegardé avant
callback, le rollback après écriture atomique et la perte de finalisation après
commit. La reprise exige l'événement de restauration exact. Une continuité
Cloth à mi-cache reste non qualifiée.

## Lire une preuve sans élargir sa portée

Un reçu exploitable lie la campagne et la tentative, le code chargé, les
références SHA-256, le corps et sa pose, la recette, les sorties, les critères,
le temps et la raison d'arrêt. Vérifier aussi que la scène source est conservée
et que les fichiers exportés ont été réellement réouverts lorsque ce critère
est demandé.

- `PASS` d'un coupon reste une preuve de coupon. Le vêtement complet doit passer
  ses propres essais, fitting et revue.
- `READY` d'un guide ou d'une préparation reste une admission géométrique locale.
  Un défaut ou un budget final non satisfait laisse le candidat non admis.
- `COMPLETED` d'un run décrit la fin des unités exécutées. Il n'accorde aucune
  acceptation de production.
- Une mensuration mesurée n'est ni une cible approuvée ni une preuve d'aisance.
- Un reçu de rendu établit les pixels produits ; la décision humaine cite les
  fichiers effectivement examinés.
- `INCOMPLETE`, `NOT_EXECUTED`, `NOT_QUALIFIED`, `UNKNOWN_COMPLETION` et les refus
  conservent leur sens. Les états absents ne sont pas interprétés comme PASS.

Après une correction, rejouer les contrôles dépendants invalidés et préserver
les observations antérieures. Une modification de coupe, de corps, de pose,
de recette ou de rig exige les preuves pertinentes sur le nouveau candidat.
