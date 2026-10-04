# Validation d’Atelier 3D

## Programme en développement — 2026-10-04

L'unité suivante poursuit l'accord numérique d'aisance ample. Son
[suivi séparé](references/automation-ease-followup-20261004.md) distingue la
variante calculée des patrons, les guides et l'acceptation encore requise.
Source figée 43, code `49ade3c` : 868 tests portables PASS en 103,96 s,
29 contrats JSON PASS, zéro FAIL et trois SKIP. Les groupes textiles natifs
v16 passent en 36,28 s et le cas natif de cage source v2 en 4,03 s.
Le [reçu de cette unité](references/automation-ease-evidence-20261004.json)
conserve les empreintes et la portée de chaque essai. La campagne 41 de
857 tests reste historique. Ces essais sont limités au logiciel et aux cas
synthétiques. Les valeurs numériques et les deux nouveaux
patrons de manches sont acceptés dans leurs portées distinctes ; la couverture
du devant et le fitting restent à vérifier.
La compilation MAIN v8 produit sept chemins proposés et refuse la poitrine :
un segment de l'ancienne préparation native ne suit pas le vrai bord source.
Les témoins de coutures résolvent les ambiguïtés d'arrondi sans élargir les
tolérances. Les chemins proposés restent non qualifiés pour le fitting.

Les observations suivantes concernent l'intégration antérieure sur la source
37 ; leurs preuves et limites restent conservées.

Les observations actuelles et leurs limites sont détaillées dans
[le programme](references/automation-program.md) et
[les preuves d'automatisation](references/automation-validation.md).
Elles ne remplacent aucune qualification du vêtement complet.
Le [reçu d'intégration](references/automation-evidence-20261004.json) conserve
les identités des campagnes et la vérification des octets du code commité.

- Source figée 37, octets conformes aux attributs Git : 795 tests portables PASS
  en 105,57 s (106,73 s de lancement).
  Empreinte `2bee3c9b90f19fe3c64dd71c01bbb590d861d6d6151eaf6a64947bb64d93ec3a`.
  Les 14 contrats de templates/fixtures et sept entrées actuelles sont validés
  par PowerShell Test-Json. Les campagnes historiques restent distinctes.
- Textile natif v14, même source 37 : groupes ordonnés, bande unique, groupe
  couplé et réconciliation sans replay PASS en 40,09 s. Portée TEST_ONLY ;
  les entrées de production sans fiche d'aisance revue restent refusées.
- Compilation publique v3, même source 37 : 15 textiles et une boucle couverts,
  six chemins proposés, deux manches non homologues refusées. Guides reconstruits
  strictement à l'identique ; SQLite et corps conservés. Fitting incomplet.
  Les anciennes campagnes 36 et antérieures conservent leurs reçus séparés.
- Source figée 32 : admission native du corps exact PASS ; quatre substitutions
  refusées. Groupes textiles v12 PASS en 35,16 s, y compris refus des entrées
  de production sans contexte d'aisance. Portée identité et coupons uniquement.
- Enfilage de prise source v5 : cinq images Cloth exécutées et réouvertes,
  erreurs sous .001 cm, poids libérés et cache valide. La bande reste éloignée
  du corps ; aucun passage physique du manteau principal démontré.
- Préparation principale v8 : 15 pièces générées, trois composants refusés.
  Épaules et haut du torse pénétrants, déformation métrique dépassant les limites,
  ceinture avec réserve insuffisante. Aucun Cloth ni fitting principal exécuté.
- Coupe ample retenue par l'utilisateur ; valeurs numériques encore proposées
  dans cette intégration antérieure. Le mannequin accepté ne change pas. Toute gradation produit une
  variante séparée à examiner avant construction et acceptation.

## Préversion textile 0.7.0-rc.2 — 2026-10-03

Les contrôles logiciels du commit publié, l'inventaire du paquet et les
empreintes sont consignés avec la release et la CI. Les essais natifs de
développement suivants sont liés aux modules et artefacts effectivement
contrôlés, avant le changement de version ; ils ne qualifient pas une nouvelle
installation Codex ou le vêtement complet.

- Procédure codée de stature : originaux et topologie conservés ; variantes
  évaluées à 180,00000189 et 180,00000392 cm, pieds conservés et réouverture
  vérifiée. Profils et points de peau des épaules remesurés sur les variantes
  exactes. Portée `GEOMETRY_ONLY` / `HEIGHT_ONLY`, pas de fitting exécuté.
- Intégrité des repères de surface : source, pose, profil complet et cadre
  liés au reçu ; triangles incomplets, étrangers, dupliqués, mal orientés et
  corps ouverts refusés. Ces contrôles ne valent pas revue anatomique humaine.
- Torse : après la correction bornée de préparation, métriques PASS sur les
  quatre panneaux des bases d'origine à 169/164 cm. Contacts corps FAIL :
  pénétration maximale 6,987 / 6,109 cm pour un seuil de 0,05 cm. Les vues
  examinées confirment les pénétrations. Self-contacts non évalués après ce
  refus ; Cloth non exécuté. Aucun transfert aux corps cibles à 180 cm.
- Réglage indépendant des tours, enfilage, construction complète des 15
  pièces textiles avec boucle rigide, fitting, mouvement et acceptation
  artistique restent à réaliser ou à qualifier.

Les reçus locaux sont `work/garment-automation-v1/body-target-runtime-v2/` et
`native-upper-torso-skin-v1/`. Ils restent exclus du paquet public. Voir
[les contrôles de mensurations](references/mannequin-measurements.md).

## Préversion textile 0.7.0-rc.1 — 2026-10-03

La préversion conserve les contrôles et les patrons approuvés. Les vérifications
logicielles du candidat versionné sont consignées avec la release et la CI du
commit publié. Les essais natifs ci-dessous précèdent le changement de version :
ils restent limités aux fichiers et scénarios effectivement contrôlés. Une
installation du paquet versionné dans Codex n’est pas revendiquée.

Sur le candidat versionné du 3 octobre 2026 : **443 tests Windows PASS**
(58,174 s) et **14 contrats JSON PASS** par PowerShell `Test-Json`.
Le journal reste local dans `work/release-0.7.0-rc.1-20261003/` du checkout
principal. Linux est vérifié séparément par la CI GitHub ; aucun WSL local
n’a été utilisé.

- Catalogue : sélection et référence statique des deux bases CC0 vérifiées dans
  une instance Blender isolée ; repos et mouvement court du rig préparatoire.
  Qualité générale des déformations et fitting non qualifiés.
- Coupon couplé : convergence après 38 images sur un plafond de 96, portée
  COUPLED_COUPON_ONLY. Aucun transfert de ce PASS au vêtement complet.
- Torse : métrique des quatre panneaux PASS sur les deux mannequins, aucun
  chevauchement entre panneaux dans le scénario ciblé. Les contacts avec le
  corps restent refusés : distance signée minimale -5,584 cm / -4,204 cm et
  raccord maximal 24,914 cm / 26,961 cm, au-delà du plafond initial de 12 cm.
  Les corrections rigides coordonnées testées sont rejetées.
- Ceinture : métrique du panneau source unique PASS sur les deux bases ;
  fermeture, boucle rigide, enfilage et fitting non exécutés.
- Limites : montage complet des 15 pièces textiles, fitting, stabilité longue,
  animation, revue humaine et import Unreal restent non qualifiés.

Les reçus natifs restent locaux sous `work/garment-automation-v1/` ; ils ne sont
pas inclus dans le paquet public. Les détails et étapes restantes sont dans
[le contrat de développement](references/garment-automation.md).

## Release 0.6.8 — 2026-10-03

La version 0.6.8 inclut la préparation et l'assemblage PATTERN_SEWN, les
contrôles après l'étude OpenSew, la complétude des pièces, la consigne
d'autorisation du code Blender et le catalogue des templates ComfyUI.
Les mentions « non publié » des sections historiques ci-dessous décrivent
l'état lors de leurs essais ; ces changements sont regroupés dans 0.6.8.

L'installation locale via le gestionnaire natif Codex est confirmée :
260 fichiers identiques au stage par SHA-256, démarrage du serveur installé,
29 outils, diagnostic plugin PASS et ping valide. Les preuves de cette
installation restent locales dans `work/install-0.6.8-20261003/` et ne sont
pas jointes au paquet public. La vérification native du nouveau contrôle de
complétude sur la scène vivante reste NOT_EXECUTED.

## Complétude des pièces Blender — correction locale du 2026-10-03

Le [signalement détaillé](BUG-2026-10-03-completude-pieces-blender.md) porte
sur la réconciliation des pièces attendues avec le candidat Blender et sur
l'affichage de sa portée. Selon les artefacts cités du projet
`work/robe-bleu-nuit-nouveau-20261003`, le résultat observé couvre le manteau
10/10, mais seulement 10/15 pièces textiles du vêtement. Les deux demi-capuches,
les deux empiècements et la ceinture restent absents de ce résultat ; la boucle
rigide doit être suivie séparément. Aucun nouvel inventaire de la scène vivante
n'a confirmé son état actuel.

**Correction implémentée dans les sources ; vérification native non exécutée.**
Le [contrôle de complétude](references/piece-completeness.md) couvre identités
et multiplicités par composant, provenance du candidat courant, absences et
doublons, visibilité distincte de présence et blocage des jalons globaux.
Il expose un bilan dans les résultats MCP et une page de revue près des images.
L'inspection inclut les candidats non READY qui portent seulement
`a3d_source_component_id`. Un compte d'objets ou un PASS local ne constitue
pas un verdict global.

Les tests `tests/test_piece_inventory.py` utilisent un adaptateur Blender
simulé et des packages/boards synthétiques : 10/15 avec cinq absences exactes,
doublon malgré un compte total correct, toutes les pièces dans un seul objet,
maillage connecté, exclusions, visibilité, provenance, gel des identités et
invalidation des preuves. Les patrons approuvés et la scène réelle ne sont
pas modifiés. La vérification de cette correction dans Blender reste à
exécuter avant de revendiquer une qualification native.

Vérifications du 2026-10-03 : **370 tests Python PASS** (58,600 s), dont
14 tests de complétude. Après les dernières corrections de restitution et
de portée de scène, **29 tests ciblés complétude/protocole PASS** (4,705 s).
Le contrôle reproduit aussi les cinq absences exactes depuis le maillage
sauvegardé de l'essai signalé. Sa page de revue et son résultat JSON restent
dans `work/piece-completeness-20261003/`, avec une mention explicite de portée
historique. Ces résultats ne qualifient pas la scène vivante ni le vêtement.

## Installation locale 0.6.7 — 2026-10-03

La version 0.6.7 regroupe les changements documentés ci-dessous, sans publication.
Les 17 tests ciblés de protocole MCP et de hooks Windows passent après la mise à
jour des trois manifestes (9,763 s). Cette vérification porte sur l'installation,
sans nouvelle qualification physique. Le reçu du gestionnaire natif, les
empreintes du paquet et le diagnostic du serveur installé sont conservés dans
`G:/projets/atelier-3d/work/install-0.6.7-20261003/`.
Une instance MCP déjà chargée nécessite le redémarrage de Codex pour utiliser
la nouvelle version ; la scène Blender et les projets ne sont pas réouverts.

## Renforcements après l'étude OpenSew — 2026-10-03, non publiés

La [recette et les contrats renforcés](references/opensew-improvements.md)
décrivent la métrique par face, l'enfilage, les couches, les contacts discrets,
les repos et la migration des preuves historiques. Les résultats ciblés
actuellement vérifiés sont les suivants ; ils ne qualifient pas le fitting réel.

| Preuve | Résultat | Périmètre |
| --- | --- | --- |
| [Suite finale](G:/projets/atelier-3d/work/opensew-implementation-20261003/unit-final.log) | 355 tests PASS, 49,665 s | Régressions et nouveaux contrôles ; 15 contrats JSON passent séparément. |
| [dressing-05](G:/projets/atelier-3d/work/opensew-implementation-20261003/dressing-05/result.json) | PASS_GEOMETRIC_DRESSING_ONLY | Ouvertures, côtés et couches mesurés ; sélection de l'unique boucle contenant l'axe sourcé, sections parasites exclues explicitement, ambiguïtés refusées. Facultatif ou partiel jamais promu en READY complet. |
| [contact-08](G:/projets/atelier-3d/work/opensew-implementation-20261003/contact-08/result.json) | PASS des cas ciblés | Intersections de faces, mouvements entre frames, tangences, couches, IDs localisés, corps modifié et budgets ; corps statique et échantillonnage discret, sans promesse de collision continue exhaustive. |
| [physics-03](G:/projets/atelier-3d/work/opensew-implementation-20261003/physics-03/result.json) | PASS_COUPONS_ONLY | Vrais Cloth courts avec repos plat et consolidé, métriques/contacts évalués, réglages sans shrink ni ressorts permanents, repos conservé à la réouverture. |
| [bending-03](G:/projets/atelier-3d/work/opensew-implementation-20261003/bending-03/result.json) | PASS_BENDING_EFFECT_COUPONS_ONLY | Quatre Cloth de 12 frames ; effet géométrique mesuré de la flexion à paramètres identiques par paire, aucune calibration matérielle. |
| [preparation-01](G:/projets/atelier-3d/work/opensew-implementation-20261003/preparation-01/result.json) | Cinq préparations READY / PASS_PREPARATION_ONLY | Contrat version 2 et reprise ; enfilage historique explicitement NOT_ASSESSED, aucun fitting déduit. |
| [assembly-03](G:/projets/atelier-3d/work/opensew-implementation-20261003/assembly-03/result.json) | Quatre cycles PASS_MECHANICS_ONLY | Buste, asymétrique et perturbations ; 128 frames admises. Déformations principales 0,951997–1,042167 ; auto-collision, sans appuis temporaires en détente/drapé. |
| [regional-02](G:/projets/atelier-3d/work/opensew-implementation-20261003/regional-02/result.json) | Audit réel exécuté, refus maintenu | Reprise exacte, poignets et orientations géométriquement admis ; col ouvert, passage buste manquant, contacts et angles insuffisants. Aucun Cloth réel. |
| [Variante auxiliaire](G:/projets/atelier-3d/work/opensew-implementation-20261003/envelope-candidate-01/result.json) | Construite et mesurée, NOT_QUALIFIED | Séparation thorax/cervicales, corps et vêtement inchangés. Profondeur col 7,30→0,95 cm ; maximum global 3,91 cm au buste, refus conservé. |

Le vêtement réel reste `NOT_QUALIFIED`. Le [bilan local complet](G:/projets/atelier-3d/work/opensew-implementation-20261003/bilan.md)
lie les masters, audits, vues et limites exactes. Les 447 fichiers du témoin
source et la scène interactive sont préservés. Les sections
ci-dessous conservent les preuves des étapes précédentes ; leurs nombres et
anciens PASS ne sont pas des résultats de cette nouvelle campagne. Au terme de
cette campagne, la version installée était restée inchangée ; une installation
locale 0.6.7 a ensuite été demandée séparément. La scène interactive et les
projets consommateurs restent inchangés.

## Préparation native des patrons — 2026-10-03, non publiée

L'entrée `prepare_pattern_assembly` audite le dossier approuvé, dérive un
maillage triangulaire gradué, applique une préforme sourcée et produit les
mesures, mappings, recette, vues et master. Elle n'exécute aucun Cloth.
Les statuts `READY`, `NEEDS_CORRECTION` et `NEEDS_CLARIFICATION` restent distincts
du fitting, du comportement et de l'acceptation finale.

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 309 tests en 53,808 s | [unit-delivery.log](G:/projets/atelier-3d/work/pattern-preparation-20261003/unit-delivery.log) ; sources/crans, préformes, flexion distincte de l'étirement, déformations refusées, migration, références périmées et régressions |
| Contrats PowerShell | PASS : 15 contrôles | [contracts-delivery.json](G:/projets/atelier-3d/work/pattern-preparation-20261003/contracts-delivery.json), dont schéma et template de préparation |
| Buste : deux devants, dos, deux manches | READY préparation | 1 550 sommets, 2 704 triangles ; déformations principales 0,98083427–1,04167634 |
| Variante sans manches asymétrique | READY préparation | 1 030 sommets, 1 804 triangles ; déformations principales 0,99999142–1,00000741 |
| Perturbations déterministes | READY préparation | Jusqu'à 1,5 mm et ±1° ; réserve mesurée minimale 6,906131185 mm pour 4 mm requis dans `fixtures-native-bend-02` |
| Même source à une autre résolution | READY préparation | 2 251 sommets, 4 020 triangles ; arc/mapping reconstruits |
| Reprise vers assemblage après réouverture | PASS | Géométrie préparée consommée exactement, sans reset ou nouvelle préforme |
| Contact profond, appuis fixes contradictoires, longueur incompatible, source périmée | Quatre REFUS ATTENDUS | [fixtures-native-bend-02](G:/projets/atelier-3d/work/pattern-preparation-20261003/fixtures-native-bend-02/result.json) ; cinq préparations READY et candidats refusés sans remplacer la préparation active |
| Chaîne d'assemblage précédente | PASS de régression, quatre fixtures | [assembly-native-bend-regression](G:/projets/atelier-3d/work/pattern-preparation-20261003/assembly-native-bend-regression/result.json) ; montage/fermeture/consolidation/détente/drapé synthétiques, preuve distincte des préparations ci-dessus |
| Coupon Bend natif et repos | PASS de configuration et reprise | [native-bend-02](G:/projets/atelier-3d/work/pattern-preparation-20261003/native-bend-02/result.json) : backend, six refus attendus, remeshing et réouverture avec Rest Shape Keys ; aucun Cloth exécuté |
| Adjacences de couture et signe de collision | PASS des contrôles ciblés | [native-bend-contact-03](G:/projets/atelier-3d/work/pattern-preparation-20261003/native-bend-contact-03/contact-result.json) et [collision-sign-01](G:/projets/atelier-3d/work/pattern-preparation-20261003/collision-sign-01/result.json) ; préparation READY obligatoire pour Bend, partenaires permanents directs proches seulement, signe aux coins et refus de contact profond |
| Copie réelle : préparation courbe et migration | EXÉCUTÉES / NEEDS_CORRECTION | [real-native-bend-02](G:/projets/atelier-3d/work/pattern-preparation-20261003/real-native-bend-02/report.json) : opération native complète en 214,078 s, 20 100 sommets, 36 978 faces ; 447 fichiers source inchangés |
| Cloth, fitting, comportement et export de la nouvelle préparation réelle | NOT_EXECUTED / NOT_QUALIFIED | Aucun PASS historique ou de fixture transféré |

Sur la copie réelle finale `real-native-bend-02`, les déformations principales valent
**0,84124046–1,18970266**, dans les bornes conservées [0,8 ; 1,25]. Six panneaux
restent sous l'angle demandé de 15° dans leur maillage à plat : centres 10,158°,
devants 11,664°, dessus de manches 12,739°. Les deux côtés ont un minimum
source de 15,188°, ramené à 14,768° après mise en volume : huit panneaux
présentent donc au moins un angle hors cible source ou 3D. Le raffinement borné restaure la meilleure
triangulation lorsqu'une tentative la dégrade. Ce résidu caractérise le
raffineur actuel ; il ne démontre pas une impossibilité de coupe.

Le témoin antérieur `real-delivery`, dont les panneaux de buste étaient plans,
avait des déformations principales de 0,99249–1,00545 et un écart maximal
de 27,3958 cm à l'épaule, au-delà du budget initial de 20 cm. Sa faible
déformation ne démontrait donc pas une mise en volume appropriée au mannequin.
Il reste conservé pour comparaison avec la préparation courbe.

La variante intermédiaire `real-volume-01`, conservée dans le
[bilan historique](G:/projets/atelier-3d/work/pattern-preparation-20261003/bilan-volume.md),
utilisait `arc_sections` et comptait 2 696 recouvrements BVH conservateurs.
Le résultat final conserve ce guide complexe pour le buste et utilise le
modificateur Blender `SIMPLE_DEFORM/BEND` sur neuf panneaux : huit de manches
et poignets, plus le col. Les paramètres, repères et évaluations natives sont
tracés ; Garment Tool n'est pas utilisé. Les correspondances UV et longueurs
d'arc restent sourcées. Flexion et étirement sont mesurés séparément : le
coupon Bend conserve des déformations principales 0,999742–1,000002 avec un
dièdre maximal de 4,50010°. Cette preuve géométrique n'est pas un essai Cloth.

Après les variantes exploratoires, la préparation complète `real-native-bend-02` a
exécuté l'entrée native, produit ses artefacts et son master versionné, puis
vérifié l'invariance des 447 fichiers source. Le déplacement maximal vaut
**18,7791 cm sur 30 cm** autorisés et l'écart maximal, à `epaule-r`, vaut
**15,97230934 cm sur 20 cm** autorisés. Ce budget de montage ne vaut pas une
fermeture dans la tolérance finale de soudure. Le guide utilise le périmètre
disponible des patrons et des repères R21 sourcés ; ses sections brutes et
lissées sont rapportées séparément. Les essais de courbure trop contraints
restent refusés.

La flexion géométrique du nouveau candidat est mesurée sur 53 873 arêtes
intérieures de panneaux : dièdre médian 1,03578°, percentile 95 à 6,92530°,
maximum 15,08718°, contre 0° sur les métriques planes source. Ces angles
décrivent la mise en volume ; ils ne constituent pas une preuve physique.

Le **col** conserve un décalage signé de **−6,879800685 cm**, soit une pénétration
profonde, avec la limite conservée de **0,05 cm**. Le BVH conservateur signale
**2 715 recouvrements non adjacents**
à examiner ; ce compte n'est pas une preuve exhaustive d'intersections.
La revue liée aux sources de l'enveloppe auxiliaire manque également.
Le résultat reste `NEEDS_CORRECTION`, sans Cloth ni fitting qualifié, malgré
le rapprochement géométrique amélioré. Le corps n'a pas été remodelé et aucun
seuil n'a été relevé. Les adjacences exclues du BVH sont uniquement des paires
permanentes déclarées, directement partenaires et dans la tolérance ; une
chaîne transitive ne permet pas de masquer un recouvrement. La correction du
signe par rayons vise les coins numériquement incertains ; toute ambiguïté
reste refusée. Le candidat réel ne contient aucune ambiguïté de signe signalée.

Les douze vues réelles finales ont été ouvertes et examinées : face, profil,
dos et trois quarts en neutre et filaire, puis deux raccords d'emmanchure dans
les deux styles. Le buste est courbé, mais l'enveloppe dépasse largement au
haut du buste et aux épaules ; les emmanchures sont béantes, avec des pointes
et des dessous de manches fragmentés. Douze vues des deux fixtures finales
ont également été examinées. Cette revue de pixels ne fournit ni approbation
artistique, ni acceptation humaine, ni reçu de validation de l'enveloppe lié
aux sources.

Les mesures historiques 7,81148 cm sur la variante posée et 9,57230 cm sur le
témoin libre relu concernent d'autres géométries. Le montage libre déjà passé
reste une preuve de ses contrôles d'origine ; il n'a jamais qualifié le fitting.
La nouvelle mesure principale du témoin ancien (0,54836–3,67280) utilise un
contrôle de déformation différent des anciens ratios d'arêtes et ne doit pas
être présentée comme un ancien résultat physique déjà accepté.

Les preuves restent sous `work/pattern-preparation-20261003/`. Le
[bilan livré](G:/projets/atelier-3d/work/pattern-preparation-20261003/bilan.md)
relie le master final, la recette, les rapports et les douze images. La recette générique et la table
fichier/fonction/migration sont dans
[references/pattern-preparation.md](references/pattern-preparation.md).
Les essais exécutent le code officiel généré pour le MCP dans Blender 5.2.2 LTS
autonome, avec profils et temporaires sur G:. Ils ne prouvent ni installation
ni rechargement du plugin dans la conversation connectée. La scène interactive
est restée ouverte et non sauvegardée par cette tâche.

## Refonte PATTERN_SEWN locale — 2026-10-03, non publiée

Les modifications antérieures du dépôt sont conservées. La version distribuée
n'est pas changée par cette refonte. Essais autonomes sous Blender 5.2.2 LTS,
profils, temporaires, clones et preuves sur `G:`. Aucun test ne commande la scène
Blender interactive ni les projets consommateurs.

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 263 tests | Contrats, géométrie, migration, revue d'enveloppe, gel final et régressions existantes |
| Contrats PowerShell | PASS : 14 contrôles | Inclut le nouveau template `pattern-assembly` |
| Buste à cinq panneaux | PASS mécanique | Préforme, montage, fermeture, consolidation, détente, drapé ; 360 → 300 sommets |
| Même buste, placement perturbé | PASS mécanique | Translations déterministes jusqu'à 1,5 mm par axe déclaré, rotations ±1° ; mêmes patrons, écart initial max 5,124 mm |
| Vêtement asymétrique sans manches | PASS mécanique | Interfaces basses, dégagements d'emmanchures et ouverture conservés ; 324 → 284 sommets |
| Variante asymétrique perturbée | PASS mécanique | Même coupe et mêmes limites que le témoin ; aucun changement du corps |
| Reprise native | PASS | Réouverture du `.blend` après fermeture et poursuite ; seconde fermeture refusée |
| Repos et appuis continus | PASS | `A3D.AssembledRest`, métriques 2D par face, zéro ressort de couture, zéro appui temporaire pendant détente/drapé |
| Gel final sans fitting qualifié | REFUS ATTENDU | Un drapé de fixture sans mesures homologues ne permet pas `freeze_sewn` |
| Parcours historiques stage/interface/rejet | PASS | Reprise, restauration, contact profond, rest/pins ; tangentes spatiales séparées du sens topologique |
| Copie réelle : migration/préforme/montage court | EXÉCUTÉS | Nouveau Cloth, aucun PASS historique transféré |
| Copie réelle : fermeture bornée | REFUS GÉOMÉTRIQUE | Croisements entre panneaux centraux de fermeture ; aucune soudure de ces liens |
| Copie réelle : consolidation/détente/drapé porté | NOT_EXECUTED | Le refus de fermeture arrête la chaîne et conserve le dernier checkpoint valide |
| Fitting, comportement, artistique et export réels | NOT_QUALIFIED | Aucun PASS de fixture ou de consolidation transféré au vêtement réel |

Les quatre fixtures gardent un écart de couture avant consolidation inférieur
à 0,011 mm, avec la tolérance de soudure inchangée de 1,5 mm. Leur stretch final
reste entre 0,9243 et 1,0242 et leur pénétration mesurée aux sommets est nulle.
Les rendus face/profil/dos/trois quarts ont été ouverts : les ouvertures sont
conservées, mais la surface grossière et les plis anguleux ne constituent pas
une validation artistique, matérielle ou anatomique.

Le montage des fixtures utilise quatre segments de deux frames, avec retrait
temporaire 0/33/67/100 %. Chaque segment initialise son propre Cloth sans vitesse
héritée : quatre pas temporels effectifs sont exécutés au total. C'est une
approche quasi statique courte, pas une stabilisation dynamique du montage.
La détente et le drapé exécutent ensuite chacun douze frames continues sur le
maillage consolidé, avec contrôle des paramètres réellement employés.

La copie réelle part du montage libre retenu, **avant application de la pose
0.6.6**. Son contact avec l'enveloppe vaut 9,5723 cm avant ce nouvel essai et
9,5622 cm après le montage court, pour un seuil conservé de 0,05 cm. Cette mesure
ne remplace pas le contact documenté de 7,81148 cm sur la variante posée : ce
sont deux candidats distincts, tous deux incompatibles avec l'entrée portée.
Les six vues réelles, dont les raccords d'emmanchure gauche/droite, ont été
inspectées et montrent ce contact profond. Aucun déficit de coupe n'en est
déduit sans mesures homologues supplémentaires.

Le garde de fermeture relève 232 paires de triangles non adjacents qui se
recouvrent. Des intersections intérieures ont été vérifiées entre les panneaux
`a06-center-l` et `a06-center-r`, reliés par une `closure`, avec des croisements
antérieurs et d'autres induits par le nouveau montage court. Ces panneaux ne
peuvent pas être soudés pour masquer le défaut. La détection BVH est conservatrice
et n'est pas une preuve exhaustive de collision continue.

Les 447 fichiers du témoin réel sont vérifiés inchangés. Les reçus historiques,
les refus, les snapshots de récupération, quatre masters synthétiques et un
master réel versionné restent dans `work/pattern-assembly-20261003/`. Le master
réel correspond au dernier montage conservé après récupération, pas à un
vêtement consolidé ou accepté. Voir la [recette et table de migration](references/pattern-assembly.md).

## État de la version 0.6.6

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 230 tests | Cohortes permanentes, fermeture indépendante, refus de fusion à distance et régressions existantes |
| Contrats PowerShell | PASS : 13 contrôles locaux | Templates, fixtures et configuration locale conservés |
| Pose native de deux panneaux | PASS | Avant correction : couture fixée ouverte de 2 mm ; après : 0 mm, source/pins conservés, résidu de cadre de 2 mm explicitement rapporté |
| Appuis partiels, écart initial, relaxation | PASS | Poids source inchangés, écart fini conservé, fermeture indépendante, budgets et stretch stricts |
| Préparation et application native de pose | PASS | Identités liées, sources conservées, artefact périmé refusé |
| Copie réelle, même pose et recette | PREPARED_NOT_APPLIED | Écart initial 1,75213 mm ; après pose 4,90394 mm avant correction et 1,65213 mm après ; déplacement max inchangé 9,79484 cm |
| Qualité de cette copie après correction | PASS structurel | Stretch 0,804897 à 1,248935 ; 667 groupes de couture, 0 fixe ; aucun excès de borne par paire |
| Lecture du cas historique buste/manches | PASS de lecture | 2365 sommets, 161 paires ; 151 cohortes, dont 4 fixes ; fichier conservé, aucune simulation ou acceptation historique rejouée |
| Chaîne native Cloth synthétique | PASS | Local, full, collisions et consolidation ; gap full 0,33158 mm ; fixture indépendante, aucun transfert à une robe |
| Fitting réel, silhouette et nouvelle image | NOT_EXECUTED | Préparation de pose seulement ; aucune résolution du contact profond ni nouvelle robe produite |

Le test réel relit une copie de preuve et compare la fonction précédente à la
fonction corrigée sur les mêmes données. Il ne sauvegarde pas le `.blend`,
ne lance pas Cloth et vérifie les empreintes du fichier, de SQLite et de la pose.
Son écart maximal dépasse encore le seuil de consolidation de 1,5 mm : aucune
fusion n'est autorisée par ce résultat. Les preuves privées restent dans `work/`.
Les tests natifs autonomes utilisent Blender 5.2.2 LTS et un profil isolé ; ils
ne prouvent pas le rechargement du MCP dans une conversation déjà ouverte.

## État de la version 0.6.5

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 227 tests | Contrats existants, groupes régionaux, provenance/partition et admissions nouvelles |
| Contrats PowerShell | PASS : 13 contrôles locaux | Deux nouveaux descriptifs ; CI sans configuration machine |
| MCP interactif officiel isolé | PASS | Garde actif, reprise/récupération, enveloppe, pose native et coupons ; aucun contournement |
| Corps seul, vrai montage libre cloné | PASS du diagnostic / NOT_QUALIFIED | Liste de manques concrète ; mesh, fichier et SQLite conservés |
| Enveloppe R21 auxiliaire | PASS géométrique | Fermée, normales extérieures, aucun sommet cible extérieur ; corps original inchangé |
| Pose continue sur copie R21 | PREPARED_NOT_APPLIED | 8 pas, déplacement max 9,79484 cm ; stretch 0,807647–1,244358, gap 0,490394 cm, pins fixes conservés |
| Introduction de l'enveloppe | PASS natif sur copie isolée | Exacte, corps conservé, garment inchangé |
| Entrée physique R21 | REFUS MESURÉ | Contact 7,81148 cm au haut du buste, seuil conservé 0,05 cm ; diagnostic retenu et récupération native |
| Coupons régionaux | PASS | Réponse distincte mesurée ; seuls poids de flexion différents, paramètres communs conservés |
| Remappage, transfert, mutations | PASS | Indices source/FlatRest/pins conservés ; poids altérés et plafonds hors plage refusés ; profil uniforme compatible |
| Fitting local/full porté, calibration matière sur robe, revue visuelle et Unreal | NOT_EXECUTED | Prépositionnement du buste encore à qualifier avant physique ; aucun PASS de fixture transféré |

Ces préparations ne modifient ni la coupe, ni le board approuvé, ni les originaux.
La nouvelle enveloppe est un proxy géométrique du squelette, pas une validation
d'anatomie en chair. Le champ de pose est une préparation vérifiée, pas un enfilage
physique réussi. Le refus de contact reste distinct d'une erreur d'intégration.
Voir [la procédure native](references/fitting-preparation.md). Les preuves privées
contenant les assets et références consommateur ne sont pas publiées.

## État de la version 0.6.4

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 220 tests | Identités et contrats, source explicite, récupération et sessions remplacées |
| Contrats PowerShell | PASS : 11 contrôles locaux | Inclut body-source, configuration locale ; CI portable sans configuration machine |
| Reprise via MCP interactif officiel | PASS sur instance GUI isolée | Garde actif, factory_settings témoin refusé, préférences/add-on/timer/connexion conservés |
| Erreurs avant/après changement de scène | PASS | Refus dirty/stale, source/témoin/archive/DB conservés, rollback automatique |
| Échec du rollback et récupération | PASS | Journal ROLLBACK_REQUIRED, opération native dédiée, aucune fabrication de pending |
| Source synthétique animée | PASS | Image explicitement évaluée, snapshot exact, ancien vêtement et dépendance implicite refusés |
| Corps R21 choisi | PASS de provenance et d'évaluation | 28 meshes + 3 dépendances, image 1, hauteur 179,9932 cm ; ancien vêtement exclu |
| Comparaison R21 sélectif/fichier complet | Géométrie mondiale exactement identique | Repères du rig également identiques ; l'original reste inchangé |
| Reprise réelle isolée | Nouveau local/full PASS | Même package/board, coordonnées finales identiques au témoin ; pas de coupe modifiée |
| Introduction native du corps R21 | PASS du transport / NOT_QUALIFIED du fitting | Référence exacte importée, enveloppe existante identifiée séparément, vêtement conservé |
| Fitting, collider anatomique, repères homologues, visuel et Unreal | NOT_EXECUTED / NOT_QUALIFIED | Corps squelettique ajouré ; aucun repère ou collider inventé depuis la hauteur |

Les tests d'intégration utilisent une instance Blender distincte, un port
localhost distinct de 9876 et un profil privé. Les tests natifs autonomes restent
des preuves séparées. Le test autonome de 0.6.3 ne couvrait pas le weak_sandbox
du MCP interactif : son refus au consommateur était une erreur d'intégration,
pas un échec du vêtement. Ce garde n'est pas désactivé pour qualifier 0.6.4.

L'inspection CLI officielle du R21 avait expiré à 120 s. Le catalogue isolé
prend 0,42 s, et l'ouverture isolée avec factory-startup/disable-autoexec 8,23 s.
La cause précise du timeout sous le profil officiel reste non établie ; ces
mesures ne permettent pas de l'attribuer à l'anatomie ou au fichier seul.
La voie native sélective évite cet appel complet et préserve la scène ouverte.
Voir [le corps source](references/body-source.md) et la
[récupération de reprise](references/clean-construction-fitting.md).

Les succès de fixtures ne sont pas transférés au projet consommateur.
Sa scène .012 et son historique restent intacts. Aucune nouvelle construction,
simulation, acceptation visuelle ou modification de coupe n'y a été exécutée.

## État de la version 0.6.3

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 218 tests | Contrats de reprise, pending, groupes/repères/budgets de placement |
| Inspection du full réel .012 | PASS du diagnostic / NOT_QUALIFIED | Pénétration 12,346239 cm séparée de la capacité ; scène/fichier/DB conservés |
| Contact profond réel | Refus avant projection | Pas d'arête ou face effondrée ; source full intacte, diagnostic et restauration natifs |
| Reprise propre réelle | Nouveau local/full PASS | Même package exact, zéro objet au départ, sans mannequin/collider au montage |
| Comparaison au témoin | Écart coordonnée maximal 0 cm | Gap 0,175213 cm ; aucune contamination cumulative établie sur ce cas |
| Historique et approbations | Conservés | Nouvelle identité de construction ; full antérieur refusé avant nouveau local |
| Introduction du proxy réelle | Import exact / NOT_QUALIFIED | Vêtement intact, proxy importé après montage libre ; contact et données manquantes lisibles |
| Placement explicite rigide | PASS sur fixture | Repères non collinéaires, translation/rotation sans scale/projection ; proxy, stale, budget/pin fixe refusés |
| Diagnostic synthétique | PASS / refus structure | Géométrie rejetée mesurée sans mutation ; FlatRest et pins altérés refusés |
| Parcours assembly/fitting historique | PASS sur fixture | Petites récupérations bornées et nouveau local/full de fitting synthétique conservés |
| Fitting réel, enfilage dynamique, visuel et Unreal | NOT_EXECUTED / NOT_QUALIFIED | Proxy et repères anatomiques supposés ne permettent pas de conclure |

Toutes les mutations de qualification ciblent des fixtures sur G:, jamais le
Blender consommateur. La reprise vide construit à nouveau depuis les patrons,
sans copier le résultat complet ou ses reçus physiques. Le test compare ensuite
les mêmes indices aux coordonnées du full témoin. Ce cas reproduit le résultat
exactement ; cela ne prouve pas une absence de défaut dans tous les projets.
Les mesures de contact restent des échantillons signés de sommets, sans prétendre
à une preuve exhaustive d'intersection ou à un fitting. Voir la
[reprise propre et le placement de fitting](references/clean-construction-fitting.md).

## État de la version 0.6.2

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 216 tests | Sources permanentes, référence immobile, budgets et contrat d'orientation inchangé |
| Inspection réelle refusée | PASS du diagnostic | Quatre tangentes lues, 672 segments mesurés ; aucun PASS ni mutation |
| Inspection native sur fixture | PASS / refus de structure | Géométrie rejetée mesurée ; rest et pins édités refusés ; scène/fichier/DB inchangés |
| Préparation locale réelle | Précontrôle PASS | Quatre violations supprimées, déplacement maximal 1,4345 cm ; torse/source/topologie/pins conservés |
| Premier Cloth après correction locale | FAIL à l'image 9 | Poignet droit dépasse 30 cm ; full non lancé |
| Montage des manches avec réserve initiale | Précontrôle PASS, Cloth FAIL | Coutures 0,1875 cm mais étirement 1,2533 > 1,25 ; aucun seuil relevé |
| Montage des manches avec réserve renforcée | Précontrôle PASS | Déplacement 15,6002 cm, écart résiduel 1,7177 cm ; torse fixe avant Cloth |
| Local réel sur les 17 panneaux | PASS / PHYSICS_ONLY | 6 649 sommets, 18 images ; nouvel essai actuel requis |
| Full réel libre | PASS / ASSEMBLY_PHYSICS_ONLY | Écart 0,175213 cm ; étirement 0,818375–1,237923 ; excursion 8,432986 cm < 30 ; angle min. 4,0195° |
| Préparation synthétique et refus | PASS | Références fixes, petit budget et pin fixe refusés ; ni source/rest ni poids édités |
| Parcours historique assembly/fitting | PASS sur fixture | Transfert, full libre, entrée fitting et nouveau local/full ; ancienne qualification conservée |
| Fitting réel, mouvement long, export Unreal, acceptation humaine | NOT_EXECUTED / NOT_QUALIFIED | Aucune mutation du Blender de production dans ces tests |

La fixture réelle part de l'objet consommateur .010 après transfert 0.6.1,
avec copie isolée de l'état et lecture du seul datablock source. Le torse reste
exactement fixe pendant les préparations, puis participe au Cloth complet.
Le package, rest, indices, bords source, coutures et pins restent inchangés.
Le PASS de 18 images ne qualifie pas 48 images ni un corps non mesuré. Voir
[les opérations et leurs limites](references/local-interfaces.md).

## État de la version 0.6.1

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 213 tests | Transfert exact, bindings de stages, refus des preuves périmées, contrats et régressions |
| Contrats indépendants | PASS : 9 distribués + config privée | Options bornées ; recettes historiques compatibles |
| Parcours natif complet | PASS sur fixture | Local libre → copie/transfert → full assembly → entrée fitting → nouveau local/full avec collider |
| Réparation initiale bornée | PASS de placement sur fixture | Contact auxiliaire minuscule réparé ; rest/topologie/pins/coutures conservés, Cloth non qualifié par cette réparation |
| Refus natifs | PASS du refus | SHA/recette périmés, full sans mannequin, pénétration/budget insuffisant, full fitting sans nouveau local, freeze après assembly |
| Références cousues fixes | PASS sur fixture | Positions de référence conservées, ancien mode de conflit encore refusé |
| Régression physique native | PASS sur fixture | Probes, local/full/freeze historiques |
| Transfert réel isolé | PASS | 5 455 coordonnées locales appliquées ; 1 194 sommets actuels inchangés ; sources/rest/mapping sémantique/coupe conservés |
| Assemblage réel de 17 panneaux | REJECTED avant Cloth | Emmanchure devant gauche, segment 17, cosinus −0,956446 < −0,5 |
| Prépositionnements réels supplémentaires | REJECTED | Torse fixe puis col fixe : aucun candidat dans les contrôles de qualité et budgets existants |
| Fitting réel, long mouvement, export Unreal, acceptation humaine | NOT_EXECUTED / NOT_QUALIFIED | Aucune scène de production modifiée ; aucun résultat de fixture transféré comme validation artistique |

Voir [le protocole de reprise et fitting](references/sewn-stages.md). Les essais
réels ont lieu sur une copie isolée de l'état consommateur. Le PASS local de
18 images ne qualifie pas 48 images ou les manches omises. Le collider du
parcours positif est un corps synthétique distinct, explicitement déclaré ;
le corps incompatible n'a pas été redimensionné pour faire passer le test.

## État de la version 0.6.0

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 204 tests | Contrat opt-in, budgets, permanent seulement, binding et mesures finales |
| Contrats indépendants | PASS : 9 distribués + config privée | Recette historique compatible ; aucun seuil physique assoupli |
| Prépositionnement natif guardé | PASS sur fixture | Écart réduit, contours/rest/topologie/pins/package intacts ; fermeture préservée |
| Références fixes contradictoires | PASS du refus | Simulation existante non archivée ; diagnostic et checkpoint conservés |
| Raffinement natif | PASS / refus borné | Ancrages et aire conservés ; budget insuffisant refusé |
| Raffinement du cas réel isolé | PASS technique | Angle minimal 2,2483° → 4,0195°, 6647 → 6649 sommets, contours et sources intacts |
| Diagnostic final de qualité | PASS sur fixture | Qualité FAIL, couture FAIL et contact PASS visibles ensemble ; restauration vérifiée |
| Régression physique native | PASS sur fixture | Probes, local/full/freeze et refus existants |
| Prépositionnement du cas réel isolé | Précontrôle PASS | Fraction 0,125 ; aucun PASS Cloth ou fitting déduit |
| Cloth après prépositionnement réel | FAIL à l'image 48 | Déformations et coutures encore hors limites ; essai expérimental, production intacte |
| Validation visuelle/humaine du nouveau placement | NOT_EXECUTED | À réaliser dans le projet consommateur, après inspection des mesures |

Voir [le contrat expérimental et le protocole d'essai](references/experimental-prefit.md).
La fixture guardée teste l'intégration ; le cas réel est une reproduction isolée
et ne constitue pas une qualification du projet consommateur.

## État de la version 0.5.9

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 201 tests | Maxima distincts, mapping local/source, historique sans incrément, non-mutation et régressions |
| Contrats indépendants | PASS : 9 distribués + config privée | Aucun contrat ou seuil physique assoupli |
| Arrêt natif de déplacement | PASS du diagnostic | Image d'arrêt conservée, excursion/incrément source mesurés ; coupon FAIL demeure FAIL |
| Conservation/restauration native | PASS | Inspection historique intacte après nettoyage/restauration ; aucun full accordé |
| Régression native physique | PASS sur fixture | Probes, local/full/freeze et contrôles de copie inchangés |
| Reproduction isolée du cas réel | FAIL du vêtement, télémétrie mesurée | Arrêt reproduit à l'image 44 ; excursion 30,0746 cm, incrément maximal 2,3367 cm, sommets différents |
| Retrait des deux appuis faibles du dos | Hypothèse rejetée | FAIL à l'image 18 ; pas de recommandation de retrait des appuis |
| Translation initiale de 3 cm | Refus natif | Pénétration initiale ; aucun Cloth lancé |
| Proposition bornée par contacts | Précontrôle PASS, Cloth NOT_EXECUTED | Translation 0,5600 cm ; légère baisse d'écarts au col/épaules, hausse d'un écart latéral ; aucun fitting accepté |
| Fitting, cause physique, production consommateur | NOT_QUALIFIED / NOT_ESTABLISHED / NOT_EXECUTED | Proxy et homologues supposés ; pas de déficit de coupe certifié ni modèle de production modifié |

Voir [les mesures et leurs limites](references/cloth-motion.md).
Les expériences réelles sont des fixtures isolées de diagnostic, pas une
qualification via le dispatcher du consommateur. La continuité obtenue par
une union géométrique de partenaires éloignés ne se transfère pas à une preuve
de convergence Cloth. Aucun mode d'assemblage assisté, préformage anatomique
ou montage progressif nouveau n'est livré par ce correctif.

## État de la version 0.5.8

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 199 tests | Chemins fermés homologues, marge/aisance, incertitude, sections séparées et attaches |
| Contrats indépendants | PASS : 9 distribués + config privée | fitting-plan ajouté ; recette historique compatible |
| Mesure native et déficit connu | PASS sur fixture | Corps cible distinct du collider, 32 cm mesurés, déficit 4 cm, full refusé |
| Proposition bornée | PASS sans mutation | Allocation de capacité en cm et coutures liées ; pas de dessin ou application automatique |
| Bâti closure natif | PASS | Écart contrôlé, durée/force observées, lien closure préservé et freeze sans permanent refusé |
| Essai local avec bâti | PASS sur fixture | Mesh jetable nettoyé, principal/rest/package intacts ; construction seulement, full refusé |
| Corps/fiche périmés | PASS du refus | Pose/géométrie target et SHA fiche vérifiés ; binding des essais actualisé |
| Régression physique | PASS sur fixture | Probes, local/full/freeze inchangés sans bâti |
| Montage/fitting manteau réel | NOT_QUALIFIED | Capacité homologuée, corps cible et assemblage consommateur non acceptés |

Voir [le contrat et les limites du fitting](references/measured-fitting.md).

## État de la version 0.5.7

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 190 tests | Statuts probe/vêtement, intégrité des preuves et régressions |
| Contrats indépendants | PASS : 8 distribués + configuration privée | Probes, seuils et patrons inchangés |
| Échec natif du probe sewing | PASS du diagnostic | 24 images évaluées sur coupon ; recette vêtement 48 ; essai vêtement NOT_EXECUTED |
| Nettoyage et restauration | PASS | Diagnostic, profil, supports, géométrie et preview conservés et vérifiés |
| Qualification locale et full | PASS du refus | Projection PASS synthétique antérieure invalidée ; full refusé pour absence de PASS local actuel |
| Échec local évalué du vêtement | PASS du diagnostic | Régression de conservation et restauration toujours valide |
| Régression native physique | PASS | Probes, local/full et freeze sur fixture synthétique |
| Vêtement réel / défaut Cloth | NOT_ESTABLISHED | Aucun projet consommateur modifié ; retest séparé |

Voir [le protocole et les limites](references/probe-diagnostics.md).

## État de la version 0.5.6

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 189 tests | Tangente locale/chorde globale, historique, intégrité et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun seuil ni contrat de patrons assoupli |
| Rejet natif d'orientation | PASS du diagnostic | Couture/bords, paires, indices, rest UV, positions et cosinus -0,5 localisés |
| Rejet natif de qualité | PASS du diagnostic | Maillage dérivé rejeté avant objet/reçu ; arêtes hors limites conservées |
| Rejet natif de contact initial | PASS du diagnostic | Pièce/sommet/collider, surface et profondeur mesurée conservés |
| Restauration obligatoire / lecture historique | PASS | Diagnostic intact avant/après restauration ; inspection ne libère pas pending |
| Régression native Cloth | PASS | Probes, local/full et freeze sur fixture synthétique |
| Robe de production, faux positif d'orientation ou bug Cloth | NOT_ESTABLISHED | Projet consommateur laissé intact ; aucun fitting qualifié |

Voir [le protocole et la reproduction](references/garment-rejections.md).

## État de la version 0.5.5

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 187 tests | Mesures, admission, contrats et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun contrat de patrons ou seuil modifié |
| Inspection native Blender 5.2.2 LTS | PASS : processus isolé | Deux panneaux effilés, coupons d'emmanchure, bras incliné ; état, fichiers, sélection et frame préservés |
| Comparaison flat/cylinder | PASS du diagnostic | 22 segments traversants → 0 ; écart 24,4131 → 3,9345 cm dans la fixture ; aucun PASS de couture |
| Refus natifs | PASS | Collider modifié et Cloth actif refusés |
| Rapport initial après échec et restauration | PASS | `placement.json` conservé et lié par SHA au diagnostic, aucun déblocage full |
| Régression native Cloth | PASS | Probes, local/full et freeze sur fixture antérieure |
| Montage et fitting de la robe réelle | NOT_EXECUTED | Projet et Blender consommateur intacts ; retest après mise à jour |
| Placement conique / coupon spatial découpé | NOT_IMPLEMENTED | Diagnostic et recette native existante d'abord ; pas de géométrie substituée au patron |

Voir [le protocole](references/sewing-placement.md) et
[les essais 0.5.5](references/validation-placement-0.5.5.md).

## État de la version 0.5.4

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 185 tests | Admission de cadrage, diagnostics, mappings et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun contrat de fabrication modifié |
| Cadrage natif Blender 5.2.2 LTS | PASS : processus isolé | ORTHO/PERSP, sélection/transforms/mesh/fichiers/état préservés ; cas étrangers et éditrices refusés |
| Capture de viewport synthétique | PASS | Pixels issus de Blender ; aucune validation artistique d'un asset réel |
| Vrai échec local après 32 frames Cloth | PASS du test de refus | Qualité hors limites, positions et zones conservées ; essai reste FAIL |
| Nettoyage puis restauration | PASS | Diagnostic encore inspectable, original/mesh/gates préservés, aucun PASS local ni admission full |
| Régression complète native de couture | PASS | Probes physiques, local/full, circuit d'échec et freeze sur fixture synthétique |
| Projet et Blender consommateur | UNTOUCHED | Retest du cadrage et d'un nouvel échec nécessaire après rechargement |
| Coupon limité à une région du patron | NOT_IMPLEMENTED | Étendues de pièces et coutures omises exposées ; supports/découpes régionales non inventés |

Voir [le protocole](references/viewport-diagnostics.md) et
[les essais 0.5.4](references/validation-viewport-0.5.4.md).

## État vérifié en version 0.5.3

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 176 tests | Reçus distincts, immutabilité, récupération et régressions des contrats/hooks |
| Contrats JSON indépendants | PASS : 8 fichiers distribués | Neuvième contrôle local de la configuration privée, exclue du package |
| Trois imports réels 0.4.0 dans Blender 5.2.2 LTS | PASS | Reçu du manteau remplacé par celui de la ceinture, puis manteau densifié par un script guardé |
| Vérification native du checkpoint | PASS | Objet initial, identité composant/package et topologie vérifiés ; contexte et datablocks conservés après lecture |
| Migration et rebuild multicomposants | PASS : fixture isolée | Mesh/rest et voisins préservés, nouveaux mappings, quatre reçus immuables pour trois composants et un rebuild |
| Checkpoint réel du consommateur | PASS : lecture seule isolée | Objet d'import retrouvé dans le checkpoint historique ; aucun fichier consommateur ni Blender ouvert modifié |
| Reprise dirty et ancien runtime en mémoire | PASS : régression 0.5.3 | Anciennes fonctionnalités de reprise conservées |
| Migration réelle et physique du manteau | NOT_EXECUTED | Retest nécessaire dans le projet consommateur après rechargement de l'installation |

Voir [le rapport 0.5.3](references/validation-receipts-0.5.3.md) et
[le protocole de récupération](references/blender-continuity.md).
Les résultats antérieurs restent historiques et ne qualifient pas un asset réel.

## État vérifié en version 0.5.2

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 170 tests | Contrats, hooks, admission, chargement de version, reprise, migration et recettes |
| Contrats JSON indépendants | PASS : 8 fichiers distribués | Un neuvième contrôle local vérifie la configuration privée, exclue du package |
| Continuité Blender 5.2.2 LTS | PASS : deux processus isolés | Modules 0.4.0 réellement chargés puis remplacés, scène dirty sauvegardée en copie, refus d'une scène étrangère |
| Ancien mesh brut et variante densifiée | PASS : fixtures synthétiques | Archivage avec géométrie/rest conservés, mapping nouvellement dérivé, décisions et sources inchangées |
| Inversion cylindrique `mirror_u` | PASS | Formule attendue, rest 2D inchangé et ancien maillage invalidé après changement de recette |
| Régression du cycle de vie Blender | PASS | Erreur après mutation, blocage, restauration et assemblage séparé |
| Projet consommateur et Blender déjà ouvert | UNTOUCHED | Les essais utilisent leurs propres projets et processus ; aucune migration réelle revendiquée |
| Nouvelle simulation physique, fitting et export Unreal | NOT_EXECUTED | Ce correctif ne qualifie pas la robe ni les recettes de production |
| Mise à jour de l'installation active dans Codex | NOT_EXECUTED pour ce correctif | Publication, installation et rechargement sont des étapes distinctes |

Voir [le rapport 0.5.2 et sa reproduction](references/validation-continuity-0.5.2.md).
Les résultats antérieurs ci-dessous restent historiques, sans être transférés à
une nouvelle recette ou à un asset réel.

## Socle vérifié en version 0.5.0

Le socle logiciel, les contrats et des opérations natives Blender ont été
vérifiés. **La qualification de production d'un asset complet reste non exécutée.**
Les contrôles automatisés ne prouvent pas la fidélité artistique des références,
l'ajustement des patrons ou la qualité d'un export de jeu.

| Vérification | Résultat connu | Portée |
| --- | --- | --- |
| Suite Python sous Windows | PASS : 158 tests | Contrats, packages, refus, parcours autorisés, MCP, hooks, board, recette de couture synthétique et profil d’installation Windows |
| Rendu du board synthétique | PASS : pixels examinés | Lisibilité, légende, repères et échelle relative ; aucune qualification d'un vrai vêtement |
| Blender 5.2.2 LTS | PASS : essai natif indépendant | Import, panneaux existants, erreur après mutation, blocage, restauration et reprise |
| Recette native de couture | PASS : fixtures isolées, deux résolutions pour les trois sondes physiques | Gravité, couture, contact réellement sollicité, sous-ensemble local puis complet, consolidation et conservation des ouvertures ; voir le rapport 0.5.0 |
| Revue des rendus natifs | Effectuée sur les fixtures synthétiques | Contact et assemblage de fragments cylindriques ; aucune qualification d'une vraie emmanchure ni d'une robe |
| Distribution 0.5.0 | Archive source vérifiée localement | Voir la release GitHub et les contrôles de version de l’installation locale |
| Installation Codex sous Windows | PASS lors de l'installation locale 0.4.0 | Nouveau serveur : 29 outils et fichiers de runtime vérifiés ; rechargement d'une conversation existante à vérifier séparément |
| Connexion Comfy officielle | PASS lors du diagnostic local antérieur | Découverte du serveur existant ; ne prouve pas la compatibilité de chaque workflow GPU |
| Image de production via Codex Image | NOT_EXECUTED dans les tests du plugin | Fournisseur explicitement simulé ; pas de reçu réel inventé |
| Génération GPU, fitting, bake Cloth complet | NOT_EXECUTED | À qualifier sur références, nœuds et modèles réels |
| Rig, animation et import Unreal d'un vrai asset | NOT_EXECUTED | À qualifier selon la destination |
| Installation Codex macOS/Linux | NOT_EXECUTED | Distincte de l'exécution des tests Python sur ces systèmes |

Les rapports des corrections [0.2.0](references/validation-pipeline-0.2.0.md),
[0.3.0](references/validation-lifecycle-0.3.0.md) et
[0.4.0](references/validation-fabrication-0.4.0.md) et
[0.5.0](references/validation-sewing-0.5.0.md) décrivent les essais locaux.
Les journaux `work/` mentionnés dans ces rapports sont conservés localement et
**ne sont pas distribués**. Pour une preuve publique reproductible, consulter
[les exécutions CI et leur commit](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml).
Ne pas transférer le résultat d'un ancien commit vers un nouveau.

## Reproduire les contrôles logiciels

Depuis la racine du dépôt avec Python 3.11+ :

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/studio.py tools
pwsh -NoProfile -File scripts/validate_contracts.ps1
New-Item -ItemType Directory -Force dist | Out-Null
python -B scripts/package_plugin.py --output dist/atelier-3d-validation.zip
```

Les tests n'appellent aucun moteur de génération et ne nécessitent pas de GPU.
La CI exécute la suite sous Windows/Python 3.11 et Linux/Python 3.13, avec
construction de l'archive. Deux tests cmd/PowerShell sont explicitement sautés
sur Linux. L'installation du plugin dans Codex n'est pas testée par ces runners.

La validation indépendante JSON requiert PowerShell 7 (`Test-Json`). Les schémas
externes des manifestes peuvent être passés à `scripts/validate_contracts.ps1`
avec `-OfficialSchemaDirectory` ; ils ne sont pas téléchargés par la CI.

`tests/native_lifecycle_smoke.py`, `tests/native_sewing_smoke.py` et
`tests/native_continuity_smoke.py` et `tests/native_multigarment_smoke.py` sont des essais
Blender séparés : ils doivent s'exécuter
dans un processus Blender dédié, avec scène vide et son dossier de travail de test,
jamais dans la scène de production ouverte. Examiner ce script avant exécution.
Ils ne font pas partie de `unittest discover` ni des jobs GitHub Actions. Utiliser
`--background --factory-startup --disable-autoexec --python-exit-code 1` pour que
les erreurs Python échouent réellement au niveau du processus. Pour le script
de couture, consulter [les commandes et limites](references/validation-sewing-0.5.0.md).

## Qualification de production à effectuer

Conserver versions, licences, modèles, paramètres et preuves dans le projet.

1. Vérifier les connexions effectives et les nœuds/modèles de chaque template avant
   de lancer un job ; qualifier les limites mémoire et l'usage des images originales.
2. Scénario vêtement : références réelles approuvées, dossier technique, packages,
   vue éclatée Codex Image, proportions et board humainement validé ; placement,
   mannequin de collision, drapé borné et comparaison des pixels aux originaux.
3. Scénario articulé : composants séparés, références multivues cohérentes, jobs
   indépendants, validation d'identité/échelle, assemblage par ancrages et articulation.
4. Provoquer une erreur limitée dans une copie, vérifier le blocage et la reprise.
   Une soumission Comfy incertaine doit être réconciliée sans envoi en double.
5. Vérifier retopologie, UV, matières, rig, poids et dégagements selon le besoin.
   Pour un jeu, inspecter l'import dans le moteur, les animations et le budget.
6. Présenter les livrables et preuves du candidat exact avant la décision finale.

Ces scénarios restent `NOT_EXECUTED` tant que leurs preuves réelles ne sont pas
produites. Un champ `PASS`, une empreinte ou un compte rendu rédigé par l'assistant
ne remplace pas une mesure, une image examinée ou une acceptation humaine.
