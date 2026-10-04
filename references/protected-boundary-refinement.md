# Raffinement des bords protégés : expérimentation V4 rejetée et restauration

**Statut : régression V4 corrigée par restauration de la trajectoire V3. La qualité régulière de 15° reste non atteinte sur le manteau réel.**

Les deux vrais coins portés par les bords homologues restent distincts. Aucun arrêt source n’est supprimé, rapproché, déplacé ou fusionné. Le manteau, la variante de manches acceptée, le mannequin et les patrons conservent leurs identités et leurs décisions.

## Résultat natif qui invalide V4

La règle expérimentale V4 donnait la priorité à un apex local lorsque le plus court côté appartenait au contour. Elle excluait aussi les circoncentres extérieurs à leur face incidente, même lorsqu’ils étaient dans le patron complet. Cette restriction concernait toutes les faces de ce type, au-delà du seul petit intervalle étudié sur le devant.

Sur la variante acceptée, les premiers candidats conditionnés des manches sont identiques entre V3 et V4. Les deux stratégies ajoutent sept points à leur première passe, puis leurs trajectoires divergent :

| Manche | Candidat initial | Première passe V3 | Première passe V4 | Meilleur V3 conservé |
|---|---:|---:|---:|---:|
| Gauche | 1,490443406° | 2,968378532° | 1,046645922° | 4,061236942° |
| Droite | 1,577553382° | 3,144790262° | 1,062032945° | 4,057463148° |

Le retour au meilleur candidat fonctionne : V4 refuse la dégradation et conserve son candidat initial. Cette conservation laisse toutefois la variante complète sous le seuil de construction de 2°. Elle reste également très loin du critère régulier de 15°. V3 dépassait le seuil de construction de 2° sur ces manches, mais ne satisfaisait pas le critère régulier de 15° ; sa restauration ne constitue donc aucune admission textile ou de fitting.

La cause ciblée est conservée dans le [rapport de régression](G:/projets/atelier-3d/work/garment-automation-v1/program-protected-boundary-native-failure-investigation-v1/cause-report.json), SHA-256 `3e7c2449c1b9312a47646137ce3059a44936668220036de43b759f11c97fc1e8`. Les payloads, sources gelées et historiques natifs V3/V4 restent séparés et conservés. Le rapport ne remplace pas une revue globale de ces payloads.

## Pourquoi le petit triangle à 60° ne suffisait pas

L’intervalle du devant étudié mesure `0,010898330561834733 cm`. Son apex équilatéral peut appartenir au patron et à la face incidente, tout en respectant la séparation existante. Le triangle formé directement avec le petit bord approche 60°.

Les deux autres triangles d’une subdivision de la face peuvent pourtant se dégrader. Pour le témoin matériel 2607, l’angle minimal des trois triangles induits descend à environ `2,395018°`, contre `6,973912°` pour la face avant subdivision. Il s’agit d’un calcul géométrique pur, qui ne prédit pas la topologie finale du CDT global.

Une insertion strictement intérieure subdivise chacun des trois angles source. En particulier, elle partage l’angle source minimal en deux angles strictement plus petits. Exiger que les trois triangles de cette subdivision simple conservent tous l’angle minimal initial ne fournit donc aucun cas admissible. Ce filtre ne devient pas une branche toujours inactive du logiciel ; aucun cas positif artificiel n’a été créé pour le justifier.

## Correctif de restauration

Le bloc de proposition retrouve exactement son comportement V3, avec la même arithmétique et les mêmes opérations float32. Un circoncentre peut servir de proposition globale du CDT lorsqu’il appartient au patron complet, même s’il est extérieur à la face qui l’a proposé. L’ajout local automatique, son helper expérimental et l’exclusion globale des circoncentres hors face sont retirés.

Le fichier `blender/sewing.py` restauré est identique, octet par octet, au fichier de la source 53 : SHA-256 `24372dc8e3e2d9b608a125697cfea2a45c3f2de0253d984a62ae0caf46e3badc`.

Les contrôles de point transporté dans le patron, de séparation, de budgets, de lissage intérieur, de restauration exacte des arrêts source, de comparaison du candidat conditionné et de retour complet au meilleur candidat restent ceux de V3. Aucun seuil, espacement ou budget n’est augmenté. Le contrôle final porte toujours sur les coordonnées matérielles exactement retournées ; le profil régulier courant exige 15° et des arêtes d’au moins 0,001 cm.

## Vérification et prochaine unité

Les 21 tests ciblés exécutés comprennent huit tests révisés de restauration et treize tests existants du conditionnement et du lissage. Ils contrôlent notamment un circoncentre hors face admissible dans le patron, le contre-exemple du petit triangle équilatéral, les arrêts source distincts et exacts après transport float32, la densité, la répétabilité, les budgets, un véritable angle source aigu, `REFINEMENT_STALLED` et la conservation exacte du meilleur candidat après dégradation.

Ces tests utilisent une doublure de transport float32 et des sorties CDT contrôlées. La fixture native comparative est préparée séparément pour les sources historiques 53, 54 et le candidat corrigé : les bords homologues sont préparés depuis les dix pièces exactes de la variante acceptée, puis seules les deux manches et le devant gauche sont triangulés. Le coordinateur exécutera cet essai isolé après gel et revue. Le résultat attendu est la restauration des trajectoires V3 ; un fichier construit ne devient pas un maillage admis à 15°.

Une future proposition locale devra être évaluée par une retriangulation réelle de plusieurs faces sous les budgets déclarés, avec conservation du meilleur candidat et contrôle final complet. Cette comparaison n’est pas intégrée au correctif de restauration. Aucune simulation Cloth, preuve de fitting, revue artistique ou autorisation Blender n’est accordée par cette unité.
