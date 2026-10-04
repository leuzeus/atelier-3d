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
