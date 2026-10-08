# Paramètres matériels des guides de torse

Le commit `70282c523d290e03830708b5304db661032ef8c8` conserve les coordonnées
matérielles utilisées pour construire les sections du torse et des épaules.
Il ne modifie ni le mannequin accepté, ni les patrons, ni les tolérances.
La correction et les captures restent des résultats de préparation : le
vêtement n'est pas admis au placement, à la simulation ou au fitting.

## Défaut corrigé

Le producteur calcule chaque rangée aux coordonnées U du patron. Le consommateur
historique recalculait ensuite les longueurs de la courbe 3D, puis les utilisait
à la place des U initiaux. Cette substitution changeait la forme du guide et
créait des ruptures U presque confondues entre rangées. Les fusionner par
proximité aurait masqué le problème et changé le domaine matériel.

`SOURCE_MATERIAL_U_V1` transporte les U explicites et partitionne les faces
source originales à leurs changements U/V. Les intersections rationnelles sont
arrondies une fois. Les validateurs existants vérifient frontières, propriétaires
et couverture ; les cellules non représentables restent refusées.

Le mode historique `POLYLINE_ARCLENGTH_V1`, choisi par défaut, conserve ses
résultats exacts sur les deux parcours comparés au commit `6d0110d`. Le nouveau
mode est une hypothèse différente, sélectionnée explicitement dans une policy
V2. Son noyau est indépendant du vêtement ; son producteur est actuellement
limité aux découpages de torse appariés avec sections mesurées et épaules.
Voir [le contrat](generic-anatomical-placement.md).

## Rejeu des quatre panneaux avant enveloppe régionale

Le noyau intégré reproduit exactement les UV, les XYZ et les triangles du POC.
Les quatre panneaux utilisent ensemble 17 555 contrôles et 33 596 triangles,
en 12,937 secondes dans un budget partagé de 120 secondes.

| Pièce | Étirement minimal | Étirement maximal | Écart intérieur maximal observé entre carte et cage |
| --- | ---: | ---: | ---: |
| Dos gauche | 0,5371 | 2,8208 | 0,1191 cm |
| Dos droit | 0,5103 | 1,7208 | 0,0981 cm |
| Devant gauche | 0,7416 | 1,5367 | 0,03765 cm |
| Devant droit | 0,7457 | 1,5453 | 0,03811 cm |

Le support des patrons est conservé, mais ces déformations restent refusées.
L'écart intérieur porte sur quatre points échantillonnés par triangle : ce
n'est pas une borne certifiée sur tout le domaine. Les écarts au placement
historique atteignent environ 3,60 cm ; aucune équivalence de forme n'est affirmée.

Les planches comparables sont sous
`work/garment-automation-v1/program-portable-anatomical-0802-v2/preview/torso-material-u-comparison-v1/` :

- `arc-length/board-overview.png` et `arc-length/board-details.png` ;
- `material-u/board-overview.png` et `material-u/board-details.png`.

Elles utilisent les mêmes caméras, limites de projection et corps opaque.
Face, dos, profil, trois-quarts et gros plans ont été affichés pendant le travail.
Les images montrent davantage de tissu le long des épaules, mais le haut du dos
et une partie de la poitrine restent occultés. Il s'agit de projections des
coordonnées enregistrées, sans rendu Blender ni simulation.

## Qualification logicielle

L'export immuable du commit 70282c5 passe **2 157 tests**, zéro SKIP, en
444,768 secondes, et **14 contrats**. La revue indépendante a fait corriger
une comparaison historique facultative qui pouvait refuser une nouvelle cage
valide ; elle retourne désormais `NOT_COMPARABLE` lorsque son ancien domaine
ne couvre pas les contrôles. Cela ne dispense d'aucun contrôle de matière.

Les reçus sont sous `program-material-sections-validation-v1/` sur G:.
La revalidation publique de l'adoption est passée de la révision 99 à 100
en 40,811 secondes, en conservant l'epoch, les composants et les décisions
humaines. Aucune opération Blender n'a été exécutée.

La compilation publique du même commit conserve les quinze guides textiles,
mais refuse le passage aux templates natifs de `garment.coat` après
125,886 secondes. Son état reste à la révision 100. Les dix pièces du manteau
sont présentes dans les vues ; capuche, empiècements, ceinture et boucle n'y
figurent pas. Le rapport reste `PARTIAL_GUIDES`, avec 885 contrôles régionaux
non résolus avant couplage. L'écart maximal de couture reste à 17,1263 cm et
la projection régionale produit encore des déformations extrêmes, jusqu'à
471,12 pour un étirement principal. Les captures montrent ces candidats refusés.

Les fichiers exacts sont `preparation/public-material-sections-preview-v1/`
dans le projet d'exécution ; `program-material-sections-v1/` conserve les
requêtes, résultats, reçus, mesures et captures sur G:. Le refus reste explicite,
sans modification des critères ni transfert des réussites de tests logiciels.

## Diagnostic séparé sans projection régionale

Un essai isolé reprend les guides du col corrigé et les quatre nouvelles cages,
avant la projection régionale. Le couplage existant utilise les mêmes paramètres
de huit itérations et 120 secondes. Il retourne `PROPOSAL_INCOMPLETE` après
89,89 secondes : l'écart maximal des coutures passe de 20,5537 à 17,0981 cm,
mais l'énergie de matière reste à 29,51249. Seule une translation rigide est
retenue ; les attaches gardent un résidu nul.

Cette expérience ne remplace pas la compilation publique ni ses reçus.
Elle montre que retirer les sauts de projection ne suffit pas. Les manches
présentent déjà des extrema de 0,1379–3,0739 à gauche et 0,02587–16,6526 à droite
avant cette projection. Le refus des pas du solveur et les guides des manches
doivent être diagnostiqués séparément, avant de prolonger les budgets.

Le diagnostic suivant localise deux causes supplémentaires :

- Le pire triangle de manche droite traverse un changement de pente du bord
  source. La cage affiche 16,65 d'étirement, tandis que les quatre Jacobiennes
  locales observées sont entre 1,33 et 1,55. Le maillage de contrôle amplifie
  fortement la déformation ; la carte tubulaire reste toutefois non admise.
- Les quatorze pas testés par le solveur diminuent tous l'objectif, mais
  compriment un triangle du dos déjà à sa borne inférieure. Diviser le pas
  ne change pas cette direction inadmissible. Le gradient est cohérent avec
  la différence finie ; une proposition tenant compte des contraintes actives
  est étudiée sans desserrer les bornes.

La provenance des attaches révèle aussi que les trajets d'épaule acceptés
ne sont pas consommés par le producteur du torse. Ses repères intermédiaires
sont décalés de plusieurs centimètres ; les écarts col–torse atteignent
4,78–6,72 cm malgré des longueurs de raccord appariées. Les bords d'épaule
source mesurent 18,439 cm, contre environ 13,18 cm sur le corps : les plaquer
sur le trajet corporel comprimerait la matière. Une proposition doit préserver
cette longueur et rendre explicite sa répartition dans le volume du vêtement.

## Travail restant

La correspondance du haut du torse avec les trajets acceptés, la couverture
régionale, les manches, le couplage et les contacts restent ouverts. Les quinze
textiles, la boucle, l'enfilage, Cloth, le fitting, les mouvements, la revue
artistique, le package et la préversion finale ne sont pas qualifiés.

Le runtime connecté reste 0801. Le stage 0802 antérieur ne contient pas cette
capacité. Les résultats décrits ici ne constituent ni une installation ni une
qualification native. Les décisions anatomiques et de coupe sont conservées ;
aucune nouvelle variante de patron n'attend de validation humaine dans ce lot.

[Reçus, fichiers examinés et empreintes](automation-material-sections-evidence-20261008.json).
