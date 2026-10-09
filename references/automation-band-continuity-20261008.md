# Continuité des bandes anatomiques et captures du col

Le commit `376a39e477aeadbb9abb48deb67b1122a378e3c5` corrige deux défauts de
représentation des bandes suivant un trajet mesuré. Le corps, le patron du col,
le trajet accepté et sa phase restent identiques. Les deux options sont
explicites et génériques ; aucune coordonnée propre au manteau n'est ajoutée au
code. Le comportement historique reste rejouable.

## Cause et correction

Le champ historique projette la direction de hauteur perpendiculairement à
chaque segment du trajet. Au changement de segment, la direction saute : sur
le col examiné, deux positions matérielles séparées de 0,0000002 cm produisent
un écart spatial de 1,2632 cm. Les fibres conservent pourtant leur longueur.
Ce contrôle seul ne pouvait donc pas détecter les plis superposés.

`BODY_DIRECTION_CONSTANT_V1` conserve une direction corporelle unitaire sur
toute la bande. `PATH_KNOT_PARTITION_V1` découpe ensuite les triangles de
contrôle aux changements de segment du trajet. Les intersections rationnelles,
les propriétaires des faces et les contrôles de frontière existants conservent
le domaine matériel source. Le maillage dérivé change ; les patrons ne changent
pas. Voir [le contrat et ses limites](generic-anatomical-placement.md).

## Comparaison isolée avant couplage

| Variante | Contrôles / triangles | Étirement minimal | Étirement maximal |
| --- | ---: | ---: | ---: |
| Historique | 477 / 832 | 0,01697 | 23,34977 |
| Champ constant, cage historique | 477 / 832 | 0,35835 | 5,73891 |
| Champ constant, partition du trajet | 457 / 789 | 0,53609 | 1,30867 |

La dernière variante conserve 376,007902418151 cm² de matière à l'arrondi près.
Elle reste **non admise** : 729 de ses 789 triangles sortent encore de la bande
diagnostique de ±2 %. Ni les contacts, ni le couplage complet, ni Cloth ou le
fitting ne sont validés par ce replay. Aucune réussite de coupon n'est transférée.

Les 27 images enregistrées couvrent les trois variantes, avec face, dos, profil,
trois-quarts et guides seuls. Les mêmes limites de projection sont calculées sur
l'union des cages, puis appliquées aux trois variantes. Le corps reste opaque
dans les vues principales. Les pixels du dos montrent la disparition des plis
superposés ; l'acceptation visuelle appartient à l'utilisateur.

Fichiers locaux sur G:, sous `work/garment-automation-v1/` :

- `program-band-continuity-v1/preview/initial/board-isolated.png` ;
- `program-band-continuity-v1/preview/constant-path-knot-partition/board-isolated.png` ;
- les manifestes des vues et leurs empreintes dans ces mêmes dossiers ;
- `program-reviewed-design-main-v1/execution-project/preparation/anatomical-placement-0801-v1/band-transverse-field-replay-v1/manifest.json`,
  avec corps, patrons, code, cages et métriques exacts.

La compilation publique complète de cette variante produit ensuite
`preparation/public-band-continuity-preview-v1/guides.json`. Elle reste refusée
avant les templates natifs, à la révision 99 inchangée. Le col conserve ses
extrema 0,53609 / 1,30867 après insertion des correspondances et couplage
(723 contrôles, 1 055 triangles). Les attaches ont un résidu nul. Le couplage
reste incomplet après huit itérations : l'écart maximal de raccord vaut encore
16,95694 cm et les enveloppes régionales du torse restent partielles.

Seize vues supplémentaires du candidat complet de dix pièces sont dans
`program-band-continuity-v1/preview/assembly/`, avec gros plans montrés à
l'utilisateur. La capuche, les empiècements, la ceinture et la boucle ne figurent
pas dans ces captures. [Reçus et empreintes](automation-band-continuity-evidence-20261008.json).

## Torse : correctif distinct encore ouvert

L'enveloppe régionale applique actuellement le déplacement complet à un contrôle
mesuré, et aucun déplacement au voisin sans projection ou hors domaine.
Sur le devant droit, deux voisins séparés de 0,001399 cm reçoivent 0 et
12,595823 cm de déplacement. Les rayons rasants peuvent aussi amplifier fortement
la réserve. Un lissage arbitraire ferait perdre cette réserve sans résoudre
l'absence de correspondance.

Un POC synthétique à 35 contrôles et 48 faces démontre un champ scalaire borné
par le gradient matériel complet. Il conserve les zones non mesurées comme
inconnues, et refuse interface incompatible, triangle effilé et métrique
initiale incorrecte. Il utilise SciPy hors produit ; ce résultat ne constitue
pas une nouvelle dépendance ni une capacité livrée du plugin.

Le torse dispose déjà d'une partition aux sections V. Les étirements bruts des
deux dos (19,73 et 8,34) précèdent l'enveloppe : l'interpolation dans l'autre axe
doit être diagnostiquée avant d'adopter un solveur régional sur le vêtement.

## Limites de livraison

L'export immuable du commit 376a39e passe **2 137 tests**, zéro SKIP, en
438,861 secondes, et **14 contrats**. La revue indépendante des deux capacités
ne relève aucun défaut bloquant. Le contrôle ajouté à sa demande compare
432 points intérieurs de triangles à l'évaluateur analytique, dans les deux
axes, les deux sens et un repère tourné. Le rejeu public de l'adoption inscrit
la révision 99 en conservant l'epoch, les composants et les décisions.
Les reçus sont dans `program-band-continuity-validation-v1/` et
`program-band-continuity-v1/revalidation/` sur G:.

Les nouveaux calculs et images sont portables. Le runtime connecté reste 0801 ;
le stage 0802 préparé antérieurement ne contient pas ce nouveau correctif.
Aucune opération Blender, installation ou relance ne résulte de ces captures.
Les décisions anatomiques et de coupe déjà acceptées restent conservées.

La correction du torse, des épaules et des manches, le couplage et les contacts
finaux restent ouverts. La construction des quinze pièces et de la boucle,
l'enfilage, Cloth, le fitting, les clips, la revue artistique du candidat exact,
le package et la préversion finale restent à qualifier.
