# Correspondances et placement conjoint — 8 octobre 2026

## Demande et état

Relier les correspondances anatomiques aux positions réelles du col, du haut
du torse et des épaules ; obtenir un candidat qui respecte simultanément les
patrons, les attaches, la matière et les contacts. Conserver les refus et
afficher les comparaisons avant/après.

**Le diagnostic public est raccordé. Le placement conjoint n'est pas admis.**
Les essais déplacent effectivement les coordonnées dérivées, mais leurs
sorties échouent aux contrôles. Ils ne modifient ni le corps masculin accepté
à 180 cm, ni les patrons, ni les relations source, ni les quinze attaches
fixes. Aucun Blender, Cloth, drapé ou fitting n'est exécuté par ces essais.

## Raccord public

`source_boundary_bindings` produit les supports barycentriques bilatéraux,
leur provenance source et leurs graines anatomiques authentifiées. Le
dispatcher les mesure après le placement, avec la continuation explicite
`SEEDED_SURFACE_PATH_LIFT_V2`. Les sommets sont traités par leur étoile native
complète ; les ambiguïtés sont conservées. L'option ne crée pas de nouvelles
attaches et ne transforme pas le diagnostic en admission.

107 tests ciblés passent. La revue indépendante est favorable pour cette
portée. Trois replays sans option donnent les mêmes rapports que le dispatcher
historique `680ea40`. Deux régressions de revue sont corrigées : respect d'un
petit budget de déplacement même sous la tolérance de résidu, et refus d'un
quotient non représentable au lieu d'une correction infinie.

Le commit exact `c063d15c0d7dd159dde8308194c291edfa212952` passe ensuite la
validation intégrée sur export immuable : **2 256 tests, aucun SKIP, 14 contrats**.
Les reçus sont dans `program-joint-boundary-integrated-validation-v1/` ; ils
qualifient ce code logiciel sur l'environnement testé, pas le vêtement.

## Comparaison réelle des correspondances

Le producteur est exécuté avant et après l'essai 02 sur les mêmes supports,
UV, propriétaires, graines et domaines.

| Mesure locale | Avant | Après essai 02 |
|---|---:|---:|
| Supports bilatéraux | 355 | 355 |
| Supports sans domaine déclaré | 32 | 32 |
| Chemins atteints | 122 | 156 |
| Départs sans nappe unique | 201 | 167 |
| Réserve conservée au plan terminal | 49 | 91 |
| Correction directionnelle maximale | 3,7754 cm | 1,4160 cm |
| Écart maximal des six coutures de col | 9,1028 cm | 0,1540 cm |

83 chemins sont résolus et 49 sont perdus. Cette progression n'est donc pas
monotone. Les 32 domaines manquants concernent le devant intérieur ; le domaine
de ses voisins n'est pas adopté implicitement. Ces reçus précèdent les deux
derniers correctifs de diagnostic et conservent leurs identités de code.

## Causes vérifiées

- **Col :** l'extrusion verticale d'une courbe ascendante crée du cisaillement.
  Sur le témoin étudié, les deux directions matérielles ont chacune une norme
  de 1 mais font un angle de 44,55 degrés, au lieu de 90. Les déformations
  principales sont environ 0,536 et 1,309. Conserver les seules longueurs des
  fibres ne prouve donc pas la conservation de la matière.
- **Couplage expérimental :** un contre-exemple de deux panneaux possède une
  solution 3D isométrique connue, à attaches conservées. Le solveur peut pourtant
  retenir leur effondrement parce que son score favorise la fermeture des
  coutures. Une absence de convergence ne prouve pas des patrons impossibles.
- **Contacts :** les corrections ponctuelles ne suffisent pas. L'audit exhaustif
  des 4 978 faces du col et du haut du torse de l'essai 04, contre le corps
  entier, détecte 1 217 paires d'intersection transverse sur 844 faces textiles.
  Le dernier état refusé compte encore 1 131 paires sur 793 faces. Aucun cas
  non mesurable ou dépassement de budget n'est rencontré dans cet audit.
- **Discrétisation :** une pénalité identique par sommet donne un poids de
  contact par unité de surface très variable. Les changements de coordonnées
  et l'équilibrage Jacobi sont algébriquement vérifiés ; ils ne résolvent pas
  seuls le défaut de stratégie non linéaire.

## Essais conservés

Les essais de développement utilisent le Python scientifique existant et
NumPy/SciPy, hors runtime du plugin. Ce n'est pas une nouvelle dépendance
installée implicitement. Les UV et triangles de chaque essai sont conservés
entre son entrée préparée et ses candidats. L'essai 03b possède une autre
discrétisation explicite et ne reçoit aucune preuve des essais précédents.

| Essai | But | Résultat |
|---|---|---|
| 01 | Couplage matière et coutures | Refus ; limitation par un pas global de déplacement. |
| 02 | Contraintes de déplacement conjointes | Refus ; raccords rapprochés mais matière et contacts incorrects. |
| 03 | Initialisation isométrique | Refus de préparation avant création du candidat. |
| 03b | Initialisation corrigée et contacts ponctuels | Refus ; déformations et pénétrations persistantes. |
| 04 | Départ extérieur, fermeture progressive | Refus ; intersections mesurées sur les surfaces. |
| 05 | Pondération par aire et résolution en déplacements | Refus ; la fermeture reste obtenue au prix de déformations. |

Les planches de l'essai 04 utilisent le même corps opaque et les mêmes caméras
avant/après. Le col change effectivement de position, mais le haut du dos et
les emmanchures restent dans le corps. Une amélioration de certains raccords
ne devient pas une acceptation du candidat.

## Correction isolée de la matière du col

Le solveur local/global à factorisation QR récupère la métrique du col en
43,188 secondes, après 8 700 itérations. Les 929 triangles sont dans l'intervalle
`[0,98 ; 1,02]`, avec des extrema de 0,989572 et 1,019933. Les treize attaches
sont strictement conservées, ainsi que les UV et la triangulation ; le
déplacement maximal est de 4,427263 cm, sous la borne de 20 cm. Une vérification
indépendante à 70 chiffres depuis les valeurs binaires enregistrées confirme
le verdict. Le noyau métrique produit confirme aussi les 929 mesures et la
couverture des treize faces source.

Le candidat est une graine géométrique distincte, conservée dans
`collar-feasibility/attempt-02-longer-qr/`. Les captures avant/après sont dans
`collar-feasibility/preview/`. Il n'est pas admis : les intersections du col
passent de 59 paires sur 38 faces à 110 paires sur 61 faces. Les plis visibles
ne constituent aucune décision artistique humaine. La récupération de matière
doit maintenant être combinée à des contacts portés par les faces.

La revue du helper a identifié deux limites de généralisation : délai terminal
non recontrôlé, et distance UV droite utilisée comme condition nécessaire sur
un domaine potentiellement concave. Une nouvelle version préserve le helper
d'origine, contrôle les délais et la taille des matrices, et utilise des
chemins d'arêtes source. La réussite du candidat initial reste rattachée à son
code et à son délai réel ; elle n'est pas transférée à un nouveau solve.

## Contradiction des attaches dérivées et réserve corrigée

L'audit des quinze points fixes est nécessaire avant un nouveau couplage.
Les treize points du col sont à plus de 0,424 cm du corps. Les deux points de
manche sont à 0,2480228 et 0,2496064 cm : ils contredisent la réserve de collision
de 0,3000000026077032 cm lorsqu'ils restent immobiles. Ce constat utilise des
témoins rationnels sur les triangles corporels fermés et ne dépend pas d'une
classification intérieur/extérieur.

Ces deux points proviennent du calcul `trajet + attachment_offset_body`. Une
nouvelle proposition conserve le trajet, sa fraction, le point source et la
direction du décalage ; elle ajoute **0,07 cm** à ce décalage. Les distances
obtenues sont **0,3058948 et 0,3078479 cm**. La certification de distance couvre
les 21 160 triangles corporels pour chaque cible, avec une marge numérique
explicite de 0,001 cm au-delà de la réserve. La recherche bornée ne prétend pas
trouver un déplacement minimal.

La variante `anatomy-poc/attachment-clearance-variant-v1/` traduit rigidement
les deux cages de manches et fournit une nouvelle liste de quinze contraintes,
dont les treize contraintes du col sont identiques. La métrique est remesurée
après les arrondis et les nouvelles cibles réellement sauvegardées sont
recertifiées. Les anciennes cages et contraintes restent intactes ; aucune
adoption canonique, décision humaine ou opération Blender n'est enregistrée.

## Diagnostic de progression ciblé

L'audit informatif demandé par les instructions de session réutilise ces
preuves. Il distingue les buts du couplage des guides (2 % et 0,05 cm, déclarés
dans `public-band-continuity-preview-v1/guide-policy.json`) des contrôles natifs
de préparation et d'assemblage. Ces valeurs n'ont pas été inventées par le
dernier prototype et aucune borne approuvée n'est modifiée pour le faire passer.

Le blocage prioritaire est technique : protéger la métrique réelle pendant la
correction des contacts, après vérification de compatibilité des attaches.
Les résultats logiciels, métriques locaux et contacts restent séparés. Le
vêtement complet n'a pas exécuté son acceptation. Le diagnostic ne déclenche
aucune réforme des règles ni répétition de la suite logicielle inchangée.

## Col : matière et réserve satisfaites simultanément

Le candidat isolé 06 conserve les treize attaches exactes, les UV, les
triangles et les treize faces source. Les **929 triangles** respectent
l'intervalle `[0,98 ; 1,02]`, avec des extrema de **0,9901752636 et
1,0198719840**. Le déplacement maximal depuis la cage initiale véritable est
**4,2332445108 cm**, sous la borne de 20 cm. Le dernier calcul prend
**32,906 secondes** sur les 90 autorisées.

Le contrôle indépendant du candidat sauvegardé couvre les 929 triangles
contre les 21 160 triangles corporels, sans réutiliser le BVH ou les rejets SAT
du solveur : 3 372 tests fins, **aucune intersection, aucun déficit de réserve
et aucune paire indéterminée**. Le minimum couvert est **0,3010000024792438 cm**
pour une réserve physique inchangée de **0,3000000026077032 cm**. Un recalcul
métrique à 70 chiffres confirme les bornes. La revue ne trouve pas de bloqueur
dans cette portée locale.

La correction combine une récupération métrique QR et des contraintes
scalaires portées par les triangles réellement rencontrés. La bande
d'activation de 0,05 cm maintient les contacts proches pendant la correction
de matière ; une marge de calcul de 0,001 cm évite de viser exactement la
frontière numérique. Aucune de ces valeurs ne réduit la réserve du contrôle
final. L'essai 05, qui la manque de moins de 1e-10 cm sur trois paires, demeure
refusé et conservé avec les essais précédents.

Le candidat est dans `collar-feasibility/attempt-06-computation-margin/`, SHA
`0e0a1f0d6e82353dbc5f3627273ac16c12bf8d95ea0ffa907485b6ec8d65169d`.
La revue est dans `collar-feasibility/review-contact-06/`. Les planches de
`contact-final-preview/final-before/` et `final-after/` ont les mêmes caméras et
un corps opaque. Elles montrent aussi des plis au dos : aucune décision
artistique humaine n'est enregistrée.

Cette réussite locale ne qualifie pas les raccords au torse, les auto-contacts,
le vêtement entier, Cloth ou le fitting. Le helper scientifique est figé et
reste distinct du runtime du plugin.

## Garde générique des attaches fixes

Le [contrôle public optionnel](fixed-attachment-clearance.md) vérifie les
cibles contre le corps entier avant le couplage. Le noyau de vérification et
de proposition fonctionne en Python standard, sans NumPy ni SciPy. Une cible
incompatible conserve son témoin et empêche le lancement du couplage ; une
proposition sur un rayon déclaré ne modifie pas les données canoniques.

Le premier replay réel a été refusé car le wrapper comparait à tort deux
formats d'empreinte géométrique. Le profil utilise les centimètres en pleine
précision ; le collider utilise les mètres arrondis, comme `mesh_digest` de
Blender. Après correction de cette correspondance, le replay 02 détecte
exactement les deux conflits initiaux et vérifie les quinze points de la
variante. Les sources et le refus initial restent conservés. Ce résultat ne
qualifie aucune surface textile.

Un autre essai initialise cinq panneaux plans hors du corps entier. Le
contrôle de 35 762 triangles ne trouve aucune paire dans la réserve, mais les
devants nécessitent 27,60 et 27,17 cm de déplacement, au-delà des 20 cm
déclarés. Cette proposition demeure refusée ; la réserve seule ne suffit pas.

## Preuves et reprise

Toutes les preuves sont sous `work/garment-automation-v1/` sur G: :

- `program-anatomical-placement-joint-v1/` : demandes, préparations, sorties
  refusées, historiques, métriques et planches `preview-02`, `preview-03b`,
  `preview-04` ; aucun écrasement des refus antérieurs.
- `program-anatomical-placement-joint-v1/review/` : revue publique et
  contre-exemple scientifique du solveur.
- `program-anatomical-placement-joint-v1/anatomy-poc/` : diagnostic du col,
  initialisation plane bornée et audit triangle-corps de l'essai 04.
- `program-neck-boundary-continuation-v1/` : replays publics et comparaison
  `joint-attempt-02-public-comparison.json`.

Le runtime connecté reste `dev.2026100801`. Le projet est `RECONSTRUCTING`, la
scène `NOT_REINSPECTED`, avec revalidation source requise par le logiciel
historique. Les changements présents dans le checkout ne sont pas installés.
La reprise native exigera le build exact puis l'opération Blender exacte
autorisée. Aucune nouvelle coupe n'attend de décision humaine dans ce lot.

La CI du précédent HEAD `680ea40` n'est pas verte : un fixture Windows dépend
de la longueur du chemin du checkout, et quatre attentes de digest des membres
échouent sous Python 3.13. Ces échecs restent à traiter ; les validations locales
historiques ne les remplacent pas. Aucune fusion ni préversion finale ne
résulte de ce travail.

La prochaine correction porte sur le couplage du col 06 et des cinq panneaux
partenaires, avec prévention des effondrements et contacts portés par les
triangles. Les coutures restent des relations entre variables, sans transformer
le col entier en nouvelle attache anatomique fixe.
Les quinze pièces, la boucle, l'enfilage, Cloth, le fitting, le mouvement et la
revue artistique restent des acceptations séparées à exécuter.
