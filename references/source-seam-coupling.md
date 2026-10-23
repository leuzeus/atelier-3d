# Couplage des guides par les coutures source

`a3d.source_seam_coupling.couple_source_seams(data, frames, seam_recipe,
subdivisions=8, budgets=None)` prépare des cages auxiliaires pour un seul
composant, en centimètres. Il retourne `(cages, report)` et conserve toutes les
entrées. Il n'exécute aucune opération Blender.

`data` contient le composant source complet et ses pièces, faces triangulaires,
bords nommés et coutures. `frames` sélectionne explicitement les pièces à
coupler ; chaque pièce doit avoir un partenaire permanent parmi cette sélection.
`seam_recipe` doit nommer exactement toutes les coutures de `data` et le même
composant. Les relations externes à la sélection restent dans le rapport comme
non traitées. Un sous-ensemble source et une recette réduite cohérente sont
possibles, mais ne rendent pas visibles les relations exclues de leurs entrées.

La V1 accepte les cadres existants `uv_cm/target_cm/triangles`,
`arc_sections/u_direction`, ou `origin_cm/u_axis/v_axis` avec un éventuel
`offset_uv_cm`. Les axes du cadre plan doivent être orthonormaux. Les cadres
hybrides et `native_bend`, qui demandent une évaluation native, sont refusés.
Les sorties contiennent uniquement `source_ref`, `uv_cm`, `target_cm` et
`triangles`.

Le noyau reprend le raffinement barycentrique entier des faces source. Pour
chaque couture permanente interne, il réunit les fractions d'arc normalisées des
coins et contrôles de bord des deux partenaires. Une orientation `reverse`
inverse la véritable chaîne du partenaire. Les axes UV des deux pièces peuvent
être différents. Un contrôle manquant subdivise exclusivement le triangle qui
porte le segment de bord source correspondant. Aucun nouveau domaine, ngon,
triangulateur ou rapprochement par distance n'est utilisé.

Les identités de coin et de segment proviennent des indices source et des
paramètres de ces segments. Le seul regroupement numérique admis concerne
l'arrondi des calculs binaires des paramètres normalisés, à 32 ULP de l'échelle
unitaire. Deux contrôles distincts d'une même chaîne qui deviennent
indiscernables sont refusés. Une subdivision qui ne produit plus de triangles
UV représentables est également refusée.

Le rapport conserve les paramètres, les indices de contrôle, les segments et
faces source, ainsi que les fractions communes. La cible d'un groupe transitif
de coins ou contrôles raccordés est la moyenne non pondérée des propositions
originales distinctes. Les corrections ne sont jamais calculées à partir de
cibles déjà modifiées. Les contrôles intérieurs suivent l'échantillonnage des
guides originaux sur le raffinement source ; cette approximation n'est pas une
garantie de conservation continue de tout champ analytique d'entrée.

L'admission des longueurs réutilise `seam_report` et la tolérance relative
explicitement déclarée dans la recette source. La V1 refuse une aisance de
couture déclarée non nulle : elle ne calcule pas sa distribution. Cette
tolérance d'entrée ne remplace aucune limite finale de déformation, de contact
ou de soudure. Le noyau conserve l'aire UV et le découpage source ; ses cages
ajoutent seulement les subdivisions auxiliaires nécessaires.

Les budgets configurables sont `max_source_points`, `max_source_triangles`,
`max_controls`, `max_triangles` et `max_seconds`. Par défaut : 20 000 points
source, 20 000 faces source, 70 000 contrôles, 131 072 triangles de cage et
60 secondes. Les plafonds absolus sont respectivement 80 000, 32 768, 70 000,
131 072 et 120 secondes. La sélection est limitée à un composant de 16 pièces
et 128 relations ; le raffinement conserve les limites du helper source
existant. Les budgets, les entrées et les sorties sont liés par leurs empreintes
dans un rapport qui se reconstruit à l'identique après sérialisation JSON.

## Contrôle purement géométrique sur MAIN

Un contrôle en mémoire sur `packages/coat-v1.garmentpkg`, les six guides de
`preparation/source-guide-proposals-policy-v6.json` et la recette de
`preparation/native-source-v8/garment.coat/recipe.json` a raccordé les quatre
pièces du torse, le devant intérieur et le col : 13 relations internes et
4 relations externes de manches conservées comme non traitées. Aucun fichier
MAIN, historique, package, corps ou état canonique n'a été modifié.

Le contrôle a ajouté 356 contrôles de bord. L'erreur maximale de conservation
d'aire UV est de 9,10 × 10⁻¹³ cm². Les écarts aux contrôles communs sont nuls ;
708 évaluations aux extrémités et au milieu de chaque intervalle de cage
atteignent un écart maximal de 2,56 × 10⁻¹² cm. Les écarts de longueurs source
du col, de 1,87 à 3,32 × 10⁻⁷ cm, restent explicitement rapportés sous le contrat
de recette existant.

Les écarts initiaux des guides atteignent 20,15 cm et la correction maximale
atteint 10,52 cm. Il reste donc nécessaire de mesurer la déformation et les
contacts de la proposition obtenue. Les empreintes de cette sortie en mémoire
sont `719ffabe5b82772f823ef34f919c0e48192b5dce1a7643da01824075d0d0bdb7`
pour les cages et
`68ff65cc9b6b7894fe3115228d27b8e2754d949dc6676ac122ed090fb5c5c5e8`
pour le rapport. Ces empreintes décrivent cette préparation historique précise.

Le statut reste `qualification: NONE`, `anatomical_homology: NOT_QUALIFIED`,
`front_coverage: NOT_REVIEWED`. Les contrôles métriques et de contact sont
obligatoires, la simulation et le fitting ne sont pas exécutés. Ce contrôle ne
qualifie ni la couverture du torse ouvert, ni l'enfilage, ni le vêtement complet.

Tests ciblés : `python -m unittest tests.test_source_seam_coupling`.
