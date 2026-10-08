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

La prochaine correction porte sur la récupération de métrique avant couplage,
la prévention des effondrements et les contacts portés par les triangles.
Les quinze pièces, la boucle, l'enfilage, Cloth, le fitting, le mouvement et la
revue artistique restent des acceptations séparées à exécuter.
