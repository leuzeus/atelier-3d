# Identité exacte des échantillons de bord

Le sampler source peut relier deux paramètres homologues légèrement différents
à une même clé de stockage déjà existante. Il conserve alors les coordonnées
exactes et la provenance du dernier échantillon écrit à cette clé. Cette
identité s'applique aux interpolations et aux sommets source conservés.

Le contrôle local rejoue la route de clé du sampler et exige des coordonnées
exactement reproductibles depuis la provenance. Les chaînes admissibles sont
les coutures déclarées avec leur orientation et les parcours libres réellement
construits par le sampler. Il refuse les chaînes adjacentes inventées, les
coordonnées modifiées, les clés et indices divergents et le remplacement d'un
arrêt source exact par une interpolation dans le fallback.

Ce contrôle prouve la cohérence route, paramètre, UV et clé. Il ne prouve pas
seul qu'un paramètre auto-cohérent est le dernier écrivain canonique. Le
parcours public de gradation rééchantillonne ensuite la source et compare les
coordonnées préparées exactes à leurs clés conservées : une modification
conjointe du paramètre et des UV reste refusée. Aucun epsilon UV, fusion de
contrôles source ou nouvel arrondi n'est ajouté.

La validation du 5 octobre conserve deux lots séparés sous chaque Python :
115 tests de bord/préparation/couture et 66 tests des consommateurs du profil,
soit 181 tests sous Python 3.11 et 181 sous Python 3.13. Le package exact de
capuche–empiècements passe le contrôle d'identité de ses 570 sommets, sans
modification de ses entrées. Une revue indépendante ne relève aucun défaut
P2 ou supérieur restant dans ce correctif.
[Preuves et limites](automation-boundary-lineage-evidence-20261005.json).

Le gradage complet conserve le refus
`SELECTED_SOURCE_SEGMENT_HAS_NO_EXISTING_SEAM_OWNER`. Le profil synchronisé
actuel ne propose pas de sélection des seuls côtés couplés. Le correctif de
provenance ne qualifie donc ni la triangulation native, ni le placement. La
recette historique reste refusée pour angle 1,794312° sous son seuil final
de 2°. Un profil compatible doit être préparé et vérifié séparément ; aucun
fallback ne doit convertir ce maillage en résultat admis.
