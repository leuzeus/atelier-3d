# Cage de torse partitionnée aux sections mesurées

Statut : candidate portable, `qualification: NONE`. Le vêtement complet, les
contacts, Cloth, le fitting et la revue artistique restent à contrôler sur leur
candidat exact. Le raccord du devant intérieur et du col n'est pas corrigé par
cette unité.

## Cause et correction bornée

L'investigation `program-source-guide-strain-investigation-v1/report.json`
(`65751d07fda403d4f262c08fcde24c52ca93a1f1d5cfaa2fff9b621fbcf11162`)
isole un défaut de représentation du dos. L'arc mesuré directement donne des
étirements principaux de `[0.9959157598, 1.0023458775]` au témoin natif 10499.
La cage uniforme précédente donne `[0.0154238653, 0.9030902360]` aux mêmes UV ;
les contrôles impliqués n'ont reçu aucune correction de couture. Des faces de
la cage traversent plusieurs sections mesurées, avec un intervalle V de 14,2 cm.

`guide_cage_sampling.section_cage_state` conserve le raffinement source déjà
déclaré, à huit subdivisions dans le parcours actuel du torse. Il découpe ses
triangles aux V exacts des sections mesurées. Les intersections possèdent des
identités rationnelles communes ; les cellules sont triangulées de manière
déterministe en conservant leurs contrôles de bord collinéaires. Chaque cible
provient exclusivement de `_section_point`, l'évaluateur existant. Il n'y a ni
nouvelle coordonnée de support, ni placement propre à ce vêtement.

La partition complète aux U des deux courbes bordant chaque bande a été
essayée puis refusée. Sur le dos réel, deux U proches produisent un triangle de
déterminant `1.8318679906315083e-14 cm²`, inférieur au seuil existant de cage
`1e-10 cm²`. Les reçus `initial-witness.json` et
`partition-refusal-witness.json` conservent cet essai distinct. Les ruptures
proches ne sont pas fusionnées et le seuil n'est pas diminué. Le coordinateur
a ensuite autorisé le prototype V obligatoire, sans union des U des arcs.
L'interpolation U reste une hypothèse mesurée ; aucune exactitude globale de
la surface bilinéaire n'est affirmée.

## Conservation et validation au second consommateur

`source_seam_coupling._prepare_piece` préserve une cage reçue après validation
réelle, plutôt que de la remplacer par le maillage uniforme. Les contrôles
portent sur les coordonnées finies, les indices, les faces dupliquées, le sens
des faces, les coins source exacts, la couverture de chaque segment source,
les propriétaires des arêtes, les liens des sommets, l'inventaire complet,
l'aire source et le support de chaque face par une face source originale.
Un marqueur dans `source_ref` ne dispense jamais de ces contrôles.

Le support matériel réutilise la règle de membership de `_cage_point` ; sa
tolérance arithmétique existante n'est pas remplacée. Pour les bords obliques,
les contrôles calculés sont arrondis une seule fois depuis leur position
rationnelle source. La validation intersecte les intervalles d'arrondi
IEEE-754 exacts des deux coordonnées et le segment source : elle n'ajoute
aucun epsilon géométrique et ne rapproche aucun contrôle. Les insertions de
couture utilisent la même formule source en arithmétique rationnelle avant
arrondi. Les paramètres adimensionnels normalisés restent ceux des helpers de
couture existants.

La V1 refuse une cage dont une face traverse plusieurs faces source originales,
même si son domaine global est valide. Elle n'attribue pas une provenance
fictive. Une superposition de triangulations nécessiterait une unité distincte.

Les longueurs et coins homologues du torse, les orientations explicites, les
moyennes non pondérées et les cohortes transitives restent inchangés. Le code
peut insérer les partitions homologues manquantes par les helpers existants.
Les pièces extérieures à cette première cage restent hors de son couplage.

## Budgets et empreintes

Les budgets déjà déclarés du couplage sont transportés par les deux raccords
privés du dispatcher et du placement sémantique. Les valeurs par défaut restent
20 000 points source, 20 000 faces source, 70 000 contrôles, 131 072 triangles et
60 secondes ; les plafonds existants restent inchangés. Les bornes du
raffinement initial sont contrôlées avant allocation, puis seuls les nouveaux
contrôles et triangles sont comptés. Un plafond exactement atteint n'est pas
facturé une seconde fois. Un dépassement ou une cellule non représentable
produit un refus et aucune qualification.

La validation filtre une fois les arêtes de bord, puis vérifie la deadline à
chaque candidate de segment. Elle réutilise le validateur existant de liens
de sommets sur chaque étoile incidente avec un contrôle de deadline avant et
après ; ce validateur n'expose pas de callback interne. Les allocations et
triangulations ont les plafonds existants. Un parcours d'étoile reste un appel
synchrone fini, borné par le nombre maximal de faces ; le contrôle postérieur
refuse un dépassement au lieu d'enregistrer une qualification.

Le helper est importé statiquement depuis les modules privés : l'inventaire
récursif des runs le lie automatiquement. Le coordinateur ajoute séparément
`guide_cage_sampling` à `garment_guide_policy.CODE_SOURCES`, à sa couverture
AST et au témoin portable de préparation. L'inventaire de distribution, la
capture du runtime et les scripts de validation parcourent déjà tous les
modules Python. Aucune interface publique, règle d'autorisation ou schema
n'est modifié.

## Preuves et limites

Les nouvelles preuves sont séparées sous
`G:/projets/atelier-3d/work/garment-automation-v1/program-guide-cage-sampling-v1`.
Le témoin réel du dos est rejoué depuis le dossier V9 et les observations
natives V3, sans modifier leurs fichiers, les patrons ou le mannequin.
La cage V donne `[0.9958346522, 1.0022739779]`, avec un écart maximal de
`0.0018332986 cm` aux trois positions évaluées directement sur l'arc. Elle
conserve 6 144 contrôles et 11 907 triangles. Le second consommateur conserve
exactement les UV, les cibles et les triangles reçus avant tout nouveau
couplage. Le reçu final précise les identités et les durées effectivement
mesurées ; ce résultat local n'est pas une mesure de gain global.

Les tests ciblés couvrent le défaut d'interpolation V, les coins et les bords,
les sections, l'immuabilité, le déterminisme/JSON, les repères tournés et U
inversé, les trous, faces incohérentes, contrôles étrangers, bowties, doublons,
provenance traversante, budgets exacts, refus sur deadline et refus de cellules
exactes trop petites. Les tests existants des moyennes, des relations externes
et de la métrique restent appliqués.

Le maximum `21.7758496643` du devant droit provenait du déplacement de bord
vers le devant intérieur. Cet alignement reste une autre unité ; la présente
preuve n'affirme pas sa correction. La qualité du maillage physique source 54
est également un contrôle indépendant. Une revue indépendante, un replay
natif et les gates du candidat complet restent nécessaires avant admission.
