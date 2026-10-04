# Correction d’aisance — suivi du 4 octobre 2026

Cette unité poursuit le [programme approuvé](automation-program.md), après
l’accord humain « ok continue avec ca » sur la fiche d’aisance ample proposée.
Le corps masculin à 180 cm conserve ses mensurations et sa géométrie acceptées.

## Décision et portée

| Région | Aisance minimale / cible / maximale |
| --- | ---: |
| Poitrine | 16 / 20 / 24 cm |
| Taille avant serrage | 6 / 10 / 14 cm |
| Hanches | 14 / 18 / 24 cm |
| Cou | 4 / 6 / 8 cm |
| Haut des bras | 6 / 8 / 12 cm |
| Poignets | 5 / 7 / 10 cm |

Le haut léger est retenu comme sous-couche de conception. Pour le torse et le
col ouverts, corps + aisance définit une enveloppe spatiale à étudier ; ce
nombre ne remplace pas une mesure de couverture ou de recouvrement.

Décision canonique `ease-design.garment.coat`, dans
`program-production-main-v1/preparation/coat-ease-design-decision-v1.json`, SHA
`d564f336f3741eabd479a4b6afe00077d7103c853b3eaa5e0a4681c480066223`.
Le reçu `program-ease-design-review-v1/receipt.json` conserve l’enregistrement.
La gate de revue de la fiche complète `fit-intent.garment.coat` reste distincte.
Aucune variante de patrons ou simulation de production n’est acceptée par cet
accord numérique seul.

## Correction du guide de manche

Le guide précédent utilisait un cylindre constant de 36 cm. Les patrons source
ont une largeur réelle variable de 29 à 36 cm. La cage barycentrique corrigée
réutilise les triangles source et les chaînes sous-bras de longueur identique,
avec des points partenaires coïncidents. Le noyau de placement et celui des
mesures évaluent la même cage ; leurs tolérances restent inchangées.

Sur les triangles UV natifs source de la préparation v8 :

| Manche | Longueur matérielle oblique | Cible nominale avec +8 cm | Fermeture du guide |
| --- | ---: | ---: | ---: |
| Gauche | 35,044241 cm | 45,439902 cm | écart 0 cm |
| Droite | 35,046953 cm | 45,476989 cm | écart inférieur à 10⁻⁸ cm |

Cette correction porte sur la correspondance géométrique du guide. Elle
n’ajoute aucune matière et ne qualifie pas les contacts, les épaules, l’enfilage
ou le fitting. Les chemins nominaux droits et les chemins obliques restent
identifiés séparément.

La compilation publique MAIN v4 a produit huit propositions en 32,39 s, avec
corps, packages et SQLite inchangés. Rapport SHA
`e76c013670a84a73a1dd6e5dddc13914e15b9e367137fe6b33da5021a2b92aa1`, dans
`program-main-fit-public-measurements-v4/report.json` ; chemins dans
`program-production-main-v1/preparation/source-measurement-path-proposal-v6.json`,
SHA `ca20513d99a88f5eb4ca02f3214626b3f7fc8ce3c453a2411f53a6ebaee528f3`.
Qualification `NONE`, fitting non exécuté, précontrôle incomplet.

Le noyau de fitting remesure les huit chemins en 0,157 s, avec les mêmes
longueurs à 10⁻⁷ cm près. Les segments obliques conservent
`source_uv_polyline_cm` et chaque tronçon est contrôlé dans la matière. Reçu
`program-main-path-remesure-v1/receipt.json`, rapport SHA
`37e8f2618016554796cde2053635a57fa5e995054dcd3bfe54605772070beba6`.
Il s’agit de longueur brute de matière ; aucune prise de confection, revue
d’homologie ou admission physique n’est déduite.

La préparation portable des composants MAIN accepte les quatre cages des
manches et manchettes, couvre les 15 pièces et conserve les budgets physiques.
Reçu `program-main-cage-templates-v1/receipt.json`, 1,938 s, qualification `NONE`.
La pose initiale est rigide, dérivée du triangle source contenant le pivot ;
sa borne de déplacement utilise l’enveloppe des cibles barycentriques.

L’essai Blender isolé `program-native-source-cage-v1` passe en 5,266 s sur la
source figée 40. Il contrôle une cage de coupon tournée, la pose Euler native
sans échelle matière, la correspondance de couture, la section oblique et la
réouverture du fichier. Portée `TEST_ONLY`, aucun Cloth ni vêtement principal
exécuté. Les deux refus de données et le consommateur de cage signalés par la
revue indépendante sont corrigés ; cette revue ne remplace pas le fitting.

## Variante et travaux suivants

Le préparateur [de variantes calculées](pattern-ease-variants.md) conserve les
sources et écrit une proposition séparée. L’agrandissement uniforme est
incompatible avec les poignets : les ouvertures source de 25 cm sont déjà dans
les plages retenues. La variation de largeur doit donc être locale, avec tête
de manche, jonction de manchette et partenaires de couture contrôlés.

Une densification de contour, lorsqu’explicitement déclarée, appartient à la
variante : nouveaux points sourcés sur les bords, provenance et remappage des
indices. Elle ne prétend pas conserver la topologie à l’identique. Les valeurs
de torse ouvert, col, couverture et recouvrement restent à préparer et revoir.

Trois variantes v2 ont été calculées avec conservation des vrais crans. La
gradation uniforme est refusée ; les deux variantes locales atteignent les
cibles nominales, mais celle sans insertion élargit la manche à plus de 65 cm
à un autre niveau. La variante densifiée atteint 45,439902 / 45,476989 cm avec
deux points ajoutés sur chaque manche, 30 → 32 sommets et 28 → 30 triangles.
Têtes de manches et raccords aux manchettes restent identiques aux sources ;
les poignets conservent 25 cm. Elle reste `NEEDS_DATA` pour torse, taille,
hanches et col ouverts, avec homologie et acceptation `PENDING`.

La comparaison exacte est dans
`program-production-main-v1/variants/ease-variant-policies-v2/comparison.json`,
SHA `03d434c12eedbd6e84a60397b4667d8cadd92eb574d977014543c24993b50be9`.
Le patron densifié est une proposition séparée, SHA
`4d4c63fef0fb1d7e39093069ed981c10480da50bdf1d0aecb0f5422f9ecbde6a` ;
son package de manteau a pour SHA
`771eddd4dec57f4c938d8b16932ee0a3757c9cc9b5c73ea8675bf2a2f9742bad`.
La planche SVG montre les 15 pièces ; la vue PNG compare les quatre pièces de
manche, SHA `be3d2c8a6fafbbc1d2727ba8024e2dca6d60cdffd2c8f5d271fbd3ab79e4de0b`.
Aucun package de variante n'est attaché à la production.

Conserver la fraction 0,5 des anciens crans les aurait déplacés de 2,087 / 2,099
cm sur ces manches. Le contrat `seam_side_positions` conserve désormais les
points matériels sur les deux bords de chaque couture unaire ; leurs résidus
sont inférieurs à 3 × 10⁻¹⁶ cm. Board, préparation et compilation consomment
ces fractions explicites avec les mêmes contrôles d'orientation.

## Correction des raccords internes du torse

La cage du torse réutilise les triangles et les partitions des vrais bords
source. Les cibles de guide des partenaires permanents reçoivent leur moyenne
commune ; les longueurs ou partitions incompatibles sont refusées. Les cinq
raccords internes — dos, épaules et côtés — sont coïncidents sur leur domaine
continu de bord. Correction maximale d'un contrôle : 1,41498 cm. Les dix
raccords externes restent explicitement hors de cette correction.

La politique v6 et les guides correspondants sont liés à leur code exact. Le
rapport de cage conserve son égalité complète après sauvegarde JSON et
reconstruction. Les mesures dans les cages utilisent le plan corporel réel et
la polyligne source, sans inventer de hauteur V constante. Une source native
ou un panneau manquant produit un diagnostic local ; aucun chemin n'est admis.

Compilation publique MAIN v6 : 33,563 s, SQLite et corps préservés, cinq chemins
proposés. Les trois chemins du torse sont refusés sur la correspondance stricte
des anciens bords UV natifs binary32. Rapport SHA
`b2fb3b1aa7c2f04fc869a7edb42055259a966ca7e42aedcfde31bab858c11f0a` ;
propositions v7 SHA `e96b5aebe0b3c97ed089b2cfff54cee68e9c2980475b060b3a239c197b68e5d7`.
Les anciennes longueurs v4 restent des observations de l'ancien guide, sans
transfert aux nouvelles cages. Les contacts natifs du haut du torse ne sont
pas corrigés par cette mesure ou par l'alignement des bords.

La préparation portable MAIN v2 couvre les 15 pièces et huit cages — quatre
du torse, deux manches et deux manchettes — en 2,063 s. Rapport SHA
`029b40e8654292c279416775699f22bbcd0fe0b02a637033cb0df9c740fc7fd1`.
Les budgets et critères physiques restent inchangés, qualification `NONE`.

## Vérification de cette unité

Source figée 41 : 472 fichiers, SHA
`a702d6448a2c97b2d18d46e875a8075c6fc89e90400ca493484195af9b44baa4`.
857 tests portables PASS en 129,210 s (130,406 s de lancement) ; 29 contrats
JSON PASS avec PowerShell Test-Json. Groupes textiles natifs v15 PASS en
42,344 s, portée `TEST_ONLY`, sans vêtement principal exécuté.

La revue indépendante des cages, du consommateur et des propositions ne
conserve aucun P1/P2 concret après corrections. Elle a notamment fait corriger
la sérialisation des couples de contrôles et le diagnostic de panneau absent.
Cette revue n'est ni une acceptation de patrons ni un essai de fitting.

Les prochaines décisions portent sur la couverture et le recouvrement du
devant ouvert, puis sur les patrons exacts. Les anciennes réussites portables
ou de coupons gardent leurs identités et ne qualifient pas le vêtement complet.

## Reprise des mesures et revue des manches

Les trois refus binary32 viennent de clés de périmètre arrondies à huit
décimales, proches d'un midpoint de coordonnée native. Le helper
`source_uv_witnesses` retrouve le point par le vrai paramètre de couture
enregistré ; il exige le contour, le bord, la relation et leur identité, la
clé de périmètre exacte après arrondi et l'égalité binary32 exacte. Les
relations contradictoires sont refusées avant la voie nominale. Aucun point
n'est recherché par proximité et aucun seuil n'est élargi.

La revue indépendante a reproduit un cas supplémentaire : inverser le
paramètre diffère numériquement d'inverser la chaîne avant échantillonnage.
Le helper reproduit désormais le préparateur officiel. Onze tests et la
reproduction indépendante passent ; le rapport initial d'échec est préservé.
Sur les quatre panneaux MAIN, 1 332 points sont réconciliés, dont seulement
trois utilisent cette désambiguïsation. Les fichiers natifs restent intacts.

Compilation publique MAIN v8 : 129,485 s, sept chemins proposés, rapport SHA
`f288b82f038aa0d97662295a89e4c1d0123aeca106cac2e2b219680e4274e65a`.
Les propositions v9 ont pour SHA
`f7d406452e36d3935c44bd7f94dc195cd63384b2105f7e590c7087c30eca2ba8`.
La poitrine reste refusée : un ancien segment triangulé s'écarte de 0,004727
cm du vrai bord source, pour une tolérance inchangée de 10⁻⁷ cm. La nouvelle
préparation devra préserver ce bord ; aucune projection forcée de l'ancienne
intersection ne vaut correction. Taille/hanches et membres restent des
propositions d'homologie. Le noyau de fitting remesure les sept chemins en
0,219 s ; reçu `program-main-path-remesure-v2/receipt.json`, longueur brute
seulement, aucune prise de confection ni acceptation déduite.

L'utilisateur a répondu « Accepter cette variante de manches » après la
planche PNG exacte. La décision
`variants/ease-variant-dense-v2/sleeve-pattern-decision-v1.json`, SHA
`6bc1d81b01b8c540af7dd4553de4eb1cb07da718f25b28b32e9b528f4f275bc4`,
est enregistrée dans la gate `pattern-variant.sleeves.garment.coat`.
Sa portée est les deux patrons de manches, avec têtes, raccords et points
matériels des crans conservés. Elle conserve les anciennes gates et les
packages de production. Torse/col, fiche complète, physique et fitting restent
à vérifier ; aucune permission d'exécution Blender n'est créée par cette revue.

L'audit des données du torse dans `program-torso-ease-input-audit-v1` sépare
les corrections techniques des choix de couverture. Les attaches externes
du devant intérieur sont encore séparées de 11,56 à 20,15 cm dans les guides,
et celles du col de 13,51 à 13,74 cm. Leur couplage par les vrais liens source
est la prochaine unité de code. Les angles d'extrémités présentent des retours
locaux de phase ; ils ne qualifient pas une couverture. Le retrait source de
3 cm reste une proposition, pas une distance portée mesurée et acceptée.

## Validation du code final de cette unité

La source figée 43 contient 474 fichiers ; son empreinte est
`6a2ad258fafca340e2f312a72db3c0d36562696b03d59641e52a52e54cd462ed`.
Les 369 fichiers de code, scripts, contrats et tests correspondent exactement
aux octets du commit `49ade3c6a78b3514c17f0104af02441761f9ca09`.
Le [reçu vérifiable](automation-ease-evidence-20261004.json) référence les
rapports conservés sur G: et leurs empreintes.

- 868 tests portables PASS en 103,962 s ; lancement en 105,094 s.
- 29 contrats JSON PASS, zéro FAIL et trois SKIP explicitement consignés.
- Groupes textiles natifs v16 PASS en 36,282 s, portée `TEST_ONLY`.
- Cage source native v2 PASS en 4,031 s, portée `TEST_ONLY` : distances source,
  coutures couplées, section oblique et réouverture, sans Cloth.
- Revue indépendante du témoin UV : onze tests et sept assertions PASS ;
  l'échec initial de l'échantillonnage inversé reste conservé.

Ces essais couvrent le logiciel livré et ses cas isolés. Les observations
MAIN v8, les décisions d'aisance et de manches et les contrôles natifs ont
leurs identités propres. Le manteau complet reste non qualifié ; la nouvelle
unité de couplage du devant intérieur et du col suit cette validation.

## Six pièces couplées et coins matériels conservés

Le couplage générique traite les 13 relations internes entre les quatre pièces
du torse, le devant intérieur et le col. Il conserve les quatre relations
externes des manches comme non traitées. Les UV et les aires des faces source
restent conservés ; les nouvelles subdivisions portent les vrais bords source.
L'écart aux contrôles communs est nul. La correction maximale de cible est
10,51971685 cm : ce résultat impose une nouvelle mesure métrique et des contacts.

Politique MAIN v8 :
`e95e0034626ad9e04df5c467bc41394147103494ffa3b05a8f1db75680a5c996`.
Guides : `355043fb3de4d7fe7bab03b8c21e05c6813f00680cc37e2971ed9e713aeb5a02`.
Rapport : `3abbd3132cb213377f6dcb7c1ba0ddc900f0c6a22c337f4f43aa5767336e530f`.
Ils se reconstruisent à l'identique depuis leurs sources et recette hachées ;
SQLite, corps, packages et anciennes propositions restent conservés.

Le coin 26 du dos gauche avait été omis car son écart à la corde, 0,01496194 cm,
restait sous la borne historique de 0,05 cm. La préparation conserve désormais
chaque changement de direction exact avant de retirer les points optionnels.
Les fractions des deux chaînes orientées sont propagées aux partenaires ; les
bords libres suivent la même règle. Un arrêt source exact restitue le sommet
original, sans seuil de proximité. Toute perte, collision de clé ou contrainte
de qualité incompatible produit un refus. L'ancien maillage reste refusé pour
la mesure de poitrine ; une nouvelle préparation native est nécessaire.

La source figée 45, 480 fichiers, a pour empreinte
`6762731d8bb71bef47cf202b9737843c6651f8872d9c7523254bebb76739a483`.
900 tests portables PASS en 114,496 s. La revue indépendante de 49 tests et ses
reproductions passent ; rapport final
`program-source-seam-coupling-review-v1/review-corners-final.json`, SHA
`64a24681aa5f1f34efa3e8ccbe34d4c3cbc189315404a9245fc0f818690002f9`.
Le dépassement de budget pendant sérialisation finale est corrigé et testé.

Deux cas natifs utilisent cette source sans la modifier : cage v3 PASS en
6,219 s, avec stockage/réouverture de six cages synthétiques et 13 raccords,
puis contour v1 PASS en 4,718 s. Le coin du coupon reste exact après CDT,
la qualité passe et la scène se rouvre. Portée `TEST_ONLY`, pas de Cloth.
La politique v8 passe son contrat JSON indépendant. La couverture, les contacts,
la construction et le fitting du manteau complet restent non qualifiés.

Le [reçu de cette unité](automation-source-coupling-evidence-20261004.json)
lie ces preuves au commit de code `848c9a89f6e5ff57576bcc9ed91fd8dedaa2211f`.
Les 389 fichiers de code et contrats vérifiés correspondent aux octets de la
source figée testée. Les mises à jour documentaires et l'archive locale sont
consignées séparément du code et de l'acceptation produit.

### Récupération métrique commune — source 47

Le commit `d024819774b749c540bd65f172fa436ad345bf71` ajoute la récupération
par cohortes permanentes aux entrées natives de préparation. Les relations
source, frontières, ownership, appuis et pins sont vérifiés avant l'optimisation.
Une borne corde/longueur UV incompatible refuse les appuis sans itération.
L'égalité exacte est garantie pendant ce noyau ; le contact suivant conserve
son gate d'écart de couture distinct.

Source figée 47 : 483 fichiers, identité
`33b30cf1833390805430d767d4067571686a294502d3780c31f502aaf783fd2b`.
922 tests portables PASS en 107,480 s, lancement 108,547 s. Revue indépendante
de 33 tests PASS, deux coupons impossibles refusés, quatre cas vérifiés par
chacun des deux validateurs de contrats. L'essai natif de placement v3 passe
en 4,094 s : récupération commune, contacts statiques, sauvegarde et réouverture
de deux panneaux synthétiques ; corps fixture préservé, aucun Cloth.

Le [reçu](automation-metric-cohort-evidence-20261004.json) lie 390 fichiers
de code et contrats aux octets du commit et de la source testée. Les huit
appuis de la proposition MAIN v8 restent mathématiquement incompatibles.
Le diagnostic de phase du col explique une partie du déplacement des épaules.
Les repères UV du col et du devant intérieur ne sont pas des pins physiques :
leur immobilisation automatique demande une correction explicite de politique.
La nouvelle préparation native principale, la couverture et le fitting restent
non exécutés ; aucune publication finale ou installation.

### Phase du col et ancrage des composantes — source 48

Le col reçoit maintenant la phase issue du milieu périodique de ses deux vrais
bords d'ancrage. Une ambiguïté antipodale, une précision insuffisante ou des
coordonnées hors domaine sont refusées ; aucun seuil physique n'est changé.
Le mode `permanent_component` vérifie les triangles et tous les sommets après
union des cohortes. Chaque composante doit disposer d'un appui déclaré positif.
Les arrêts source et pins explicites restent protégés ; les ancres UV du col
et du devant intérieur servent au placement sans devenir des pins automatiques.

Code final `0c744c193968a8e80fb0df20beeb80da2ca19c17`, après la correction de
phase `fa08ffe`. Source figée 48 : 484 fichiers, empreinte
`d54aac47ffa7b3bafb329d0e6c31b460612d01a5bfb7a36183249e9495d81e90`.
939 tests portables PASS en 108,606 s ; lancement 109,781 s. Revue indépendante
de 88 tests PASS et 12 cas de contrat PASS par chacun des deux validateurs.
L'essai Blender statique v4 passe en 3,938 s : deux panneaux synthétiques dont
un seul ancré, cohortes permanentes, contacts, sauvegarde et réouverture ; corps
préservé, aucun Cloth. Le [reçu](automation-metric-anchor-evidence-20261004.json)
lie ces résultats aux octets du code et conserve les campagnes antérieures.

La proposition MAIN v9 se reconstruit à l'identique après JSON, avec 13 raccords
internes communs à écart nul et quatre arrêts numériques d'épaule. Les rapports
corde/longueur source sont 0,943781 et 0,942288, sous la borne maximale 1,1.
Ces conditions sont nécessaires, sans suffire à admettre triangles ou contacts.
Politique SHA `dc3b4531bccd5aeb8fcbd600574232317d273581bc8aa3ce7a3d29bf3a444c84`,
guides SHA `9db51cd58780257018fd8a959eadcca57bc977ffc906882d09ec261155332938`.
Corps, patrons, SQLite et ancienne préparation native sont conservés.

Le diagnostic des six cages auxiliaires s'arrête avant de produire un candidat.
Il observe au col un segment source d'environ 1,25 × 10⁻⁷ cm, sous la borne
0,001 cm, et un triangle déjà trop fin avant alignement. Il ne s'agit pas du
maillage régulier natif. Aucun résultat de fitting ou impossibilité de patron
n'est déduit de ce refus. La prochaine unité prépare le maillage régulier exact
avec les nouveaux guides, puis mesure métrique, raccords et contacts.

Le contrôle du runtime confirme que la copie installée `0.7.0-rc.2` exécute sa
propre racine, sans option permettant de substituer la source 48 sur MAIN.
La qualification isolée du code reste possible avec portée explicite ; une
installation locale de développement et sa vérification doivent être examinées
avant d'utiliser ce code sur MAIN. Aucune nouvelle release, installation ni
permission Blender implicite ; les critères de qualification finale restent
inchangés.

### Conditionnement et composition de variante — sources 50 et 51

Le précontrôle métrique distingue désormais l'angle et l'aire UV immuables
des défauts corrigibles par déplacement. Il retourne le défaut dérivé sans
itération, en conservant les bornes des appuis et les limites finales. Il
ne déclare pas le patron impossible.

Chaque candidat CDT reçoit maintenant le même lissage borné puis la
restauration exacte des ancres avant comparaison au meilleur candidat.
Le coût maximal de huit passages locaux par candidat reste explicite.
La suite source50 passe 967 tests en 111,096 s, lancement 112,234 s.
Le carré natif V1 à quatre coins est refusé à 11,998° : cette preuve reste
conservée. La fixture V2 emploie seize stops de contour à 1 cm, mêmes coins,
aire et limites ; carré et bande atteignent leur cible, l'angle aigu est
refusé, la scène se rouvre exactement. Aucun Cloth.

Le diagnostic réel source50, exécuté en instance isolée, conserve le corps,
les sources et SQLite. Le minimum d'angle source du col atteint 15,438170034°,
contre 13,747708476° dans l'essai précédent. La récupération 3D accepte une
itération, commence la deuxième puis s'arrête au budget temps ; la recherche
de correction des contacts ne commence pas. Les mesures de contact conservées
ne valent pas admission. Lors de cette campagne source50, le build complet
était encore refusé sur un très court segment des anciennes manches.

Les helpers de composition passent aussi leur revue et le replay pur sur les
deux dossiers et packages réels : seules les deux manches acceptées changent,
les treize autres lignes textiles et la boucle restent exactes. Les différences
incidentes de dix lignes sont exclues et rapportées. La revue corrige l'identité
des crans en `(seam_id, id)`, sans epsilon. Cette préparation ne modifiait pas
les bindings de production ; son consommateur canonique restait à intégrer.

Le [reçu](automation-source-conditioning-evidence-20261004.json) conserve les
identités de code, sources, reviews, essais réussis et refus. La construction
physique complète, l'enfilage, le drapé, le fitting, le mouvement du manteau et
la revue artistique restent requis. Aucune release ou installation finale.

### Crans et composition canonique — source53

L'unité `4528424` conserve les coins exacts et lie les crans à la matière.
Un cran à l'intérieur d'un segment porte ses deux sommets, poids et paramètres
source ; il ne prétend pas être un sommet ou un indice physique de couture.
Le conflit des anciennes micro-arêtes de manches est traité : les replays
originaux et de la composition acceptée ne contiennent aucune arête sous
0,001 cm. Ils conservent 48 références de crans, 249/253 vrais coins et quatre
crans de dessous de manche sous forme BOUNDARY_SEGMENT. Les résidus numériques
observés sont consignés ; ils ne deviennent pas une tolérance de couture.

L'unité `b0873264` ajoute l'import du design approuvé avec la variante explicitement
revue. La décision humaine authentique des deux manches est réutilisée ; la
lignée du design original, de sa génération et de sa planche est vérifiée.
Le candidat séparé `program-reviewed-design-main-v1/execution-project` est
RECONSTRUCTING avec 15 textiles et la boucle. Ses deux manches sont celles
acceptées ; les treize autres lignes textiles et la boucle restent exactes,
et dix lignes incidentes non revues sont exclues de la composition. MAIN et
ses bindings originaux restent inchangés. Il s'agit de l'admission des entrées
de reconstruction : aucun fitting, placement ni permission Blender accordé.

Le reçu d'import a été réconcilié sans répétition de l'import après une erreur
de reporting. Le temps initial n'est pas enregistré et les octets des bases
parentes avant l'import n'ont pas été capturés par le script initial.
La réconciliation de 7,516 s
conserve la base candidate ; une revue indépendante ultérieure en lecture seule
contrôle la lignée, la décision humaine et trois bases réelles sans mutation.
Ces preuves ultérieures sont distinctes des observations initiales manquantes.

Source53 comprend 497 fichiers, identité
`acf950165513b1a2b29a7d99295de13b907d4020b7ec6785493968411d58353a`.
La suite portable passe 1 012 tests en 206,460 s, lancement 207,656 s.
La revue des crans passe 100 tests ciblés ; celle de l'admission conserve ses
fixtures synthétiques et ses refus distincts de la revue des trois bases réelles.
CI `37234999162` sur `b08732641a342b8314ab765485cdcff013a5fb01` : tests/build
Windows 3.11 et Linux 3.13 PASS ; contrats Windows PASS, Linux SKIP.

Le nouveau diagnostic construit les dix pièces originales (15 555 sommets,
28 874 triangles) en 39,525 s, puis la variante acceptée (15 669 sommets,
29 082 triangles) en 38,905 s. NATIVE_PAYLOAD_BUILT ne signifie pas que les
triangles atteignent 15° : les deux devants, deux dos et deux manches portent
déjà NEEDS_CORRECTION dans leurs rapports réguliers. Le contrôle global de
recette n'exige que 2° et ne remplace pas ce critère de préparation.

Le sous-ensemble de six pièces conserve exactement les coordonnées matérielles,
faces et UV du maillage complet. À la face 2605 du devant gauche, l'angle source
vaut 4,483886989° ; le minimum d'aire source vaut 0,000475676532 cm² à la
face 2607. La récupération s'arrête à zéro itération avec
METRIC_RECOVERY_IMMUTABLE_SOURCE_MESH_QUALITY. Ce nouveau défaut de triangles
dérivés n'est ni le conflit de crans corrigé ni une preuve d'impossibilité des
patrons. L'écart binary32 de la face témoin n'explique pas le refus. L'ancien
col à 15,438170034° sur six pièces indépendantes source50 reste une preuve de
cette campagne ; il n'accorde aucun PASS au nouveau maillage complet source53.

La cause locale est un court segment de bord de 0,010898331 cm, créé par deux
vrais coins homologues conservés. Une sonde pure calcule un candidat de
raffinement dans la face incidente ; le circoncentre choisi par la règle
actuelle est seulement dans le polygone et peut se trouver hors de cette face.
Cette proposition reste à contrôler par CDT natif. Les sources, les appuis,
le corps et les seuils de qualité sont conservés.

Le [reçu détaillé](automation-reviewed-pattern-evidence-20261004.json) référence
la suite, les revues, l'import réconcilié, le diagnostic et son investigation.
Le refus anticipé `336cdb6` passe sa revue et 68 tests ciblés ; le lot CDT
`9febfb3` passe sa revue et 49 tests portables. Les résultats de leur intégration
source54 sont consignés séparément ci-dessous. Ce suivi est ajouté après les
captures source53 et source54 ; il n'étend pas la portée de leurs essais.

### Intégration des corrections — source54

Source54 : 501 fichiers, identité
`fe517779f1f19fecf91eca55297c2a2d47ff5c908f3ab1b7e9ff10e1870d23b0`.
1 040 tests portables intégrés PASS en 177,628 s ; lancement 178,719 s, source
figée inchangée. Le refus anticipé ne peut pas admettre un candidat ; le
validateur final reste complet. La proposition locale CDT conserve les coins
authentiques, les partenaires, les budgets et le seuil de 15°.

CI `37236866063` sur `9febfb3a606d39d840140918ae8c1b62b3470312` : tests/build
Windows 3.11 et Linux 3.13 PASS ; contrats Windows PASS, Linux SKIP. Cette
portée logicielle ne qualifie pas le vêtement.

Coupon natif v3 : sauvegarde/réouverture exacte et ancres conservées. Carré et
bande atteignent TARGET_REACHED avec minimums natifs 23,793971234° et
15,874234372° ; le coin aigu reste NEEDS_CORRECTION. Calcul 0,294 s,
lancement 4,313 s. Ces cas synthétiques ne qualifient pas le maillage réel.

Le diagnostic réel v4 dure 118,672 s, lancement 127,688 s. Les dix pièces
originales sont construites : 15 515 sommets et 28 794 triangles. La variante
des dix pièces est REFUSED par le contrôle global à 2°, avec un minimum
d'angle de 1,490237725°. Son payload refusé est conservé et n'est pas utilisé.
Le sous-ensemble original de six pièces reste refusé par
METRIC_RECOVERY_IMMUTABLE_SOURCE_MESH_QUALITY à zéro itération ; la recherche
de correction des contacts n'est pas démarrée. Aucun gain global du refus
anticipé n'est établi par cette récupération interrompue avant itération.

Les entrées, les 501 fichiers figés, MAIN et le corps sont conservés. Le
précontrôle v4 garde les identités du clone v3 et ne crée pas une nouvelle
observation des trois bases SQLite. La revue indépendante confirme les refus :
les faces originales sous 15° passent de 36 à 24, mais leur minimum matériel
tombe de 4,483887° à 2,560347°. Pour la variante, 30 faces deviennent 26 et le
minimum passe de 4,057463° à 1,490443°. Le rollback conserve la baseline des
manches lorsque la nouvelle trajectoire s'arrête au premier raffinement ;
le transport binary32 ne cause pas le refus à 2°. La scène est sauvegardée,
sans réouverture exécutée. Le conditionnement réel et les propositions CDT
doivent être investigués puis corrigés avant de rejouer les contrôles affectés,
sans changer les sources, les appuis, le corps ou les seuils.

Qualification NONE : contacts et couverture non admis, physique, enfilage,
drapé, fitting complet, mouvements du vêtement et revue artistique à réaliser.
Aucune préversion finale, nouvelle installation ou qualification du runtime
connecté n'est produite par ces contrôles.

### Suite — restauration et correction de représentation du dos

Le noyau CDT restauré reprend exactement les trajectoires source53 sur les
deux manches acceptées et le devant gauche, avec tous les arrêts source
conservés. Les neuf replays natifs sont revus ; les trois pièces restent sous
le critère régulier de 15°. Cette restauration corrige la régression V4,
sans admission du maillage complet.

La cage du dos suit maintenant les hauteurs mesurées et reste conservée
par le second consommateur après validation matérielle. Son témoin local
passe de `[0,015424 ; 0,903090]` à `[0,995835 ; 1,002274]`, avec un résidu
maximal de 0,00183330 cm par rapport à l'arc direct. Les 1 055 tests intégrés
de source57 passent, ainsi que la revue indépendante des 88 tests ciblés
et quatre sondes adverses. Le
[reçu exact](automation-cage-restoration-evidence-20261004.json) distingue
ces preuves des anciennes campagnes et de l'acceptation du manteau.

Le devant intérieur, le col, les contacts et la couverture restent à traiter.
Le mannequin accepté et les patrons sont conservés. Aucune aisance globale,
physique, fitting ou revue artistique n'est admise par ce seul témoin du dos.


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
