# Trajets ouverts sur la peau du corps cible

`a3d.body_surface_paths.propose_body_surface_paths` propose des chemins ouverts
sur les arêtes originales du corps, à partir d'une spécification explicite.
Le noyau ne dépend d'aucun vêtement : régions, extrémités, repère et budgets
sont des données. Il ne modifie pas le mannequin ni les mesures canoniques.

Chaque extrémité est un sommet source déclaré ou l'extrême unique d'une
frontière corporelle authentifiée. Le domaine est limité à des régions source
explicites. Le solveur conserve les sommets ordonnés, les faces porteuses et
les coordonnées 3D, puis mesure la longueur de la polyligne, la corde et la
descente dans le repère du corps. Les domaines disjoints, coordonnées non
finies, budgets dépassés et alternatives numériquement ambiguës sont refusés.

La méthode mesure une polyligne d'arêtes. Son erreur par rapport à une
surface lisse n'est pas estimée ; elle n'est pas une géodésique lisse qualifiée.
L'authentification native appartient aux rapports d'entrée, la correspondance
de patronage appartient à la revue humaine. Une longueur calculée ne devient
ni une position de couture ni une aisance implicite.

Le 7 octobre 2026, les deux propositions d'épaule du mannequin masculin accepté
ont été présentées sur une planche à quatre vues puis acceptées comme trajets
corporels : 13,1680 et 13,1878 cm, avec une descente de 2,0678 et 2,0615 cm.
Le départ suit quelques arêtes du contour du cou avant de traverser l'épaule.
Les coutures d'épaule source mesurent environ 18,4391 cm ; leur correspondance
et la position d'épaule du manteau ample doivent encore être établies.
Aucun manque de tissu ou excédent de coupe n'est déduit de cette soustraction.

La revue indépendante a corrigé la conservation des minima et des alternatives
de coût proche sur toute la chaîne des prédécesseurs. Les 79 tests ciblés
passent, dont onze tests du noyau ; le rejeu des artefacts exacts conserve les
entrées et les deux trajets. Ce noyau source n'est pas encore installé dans
le runtime connecté 0704.

[Preuve du code et décisions humaines](automation-body-surface-path-evidence-20261007.json).

## Préparation par le plugin

L'opération existante `studio_prepare_body_path_review` conserve ses quatre
arguments : projet, profil corporel, spécification et dossier de sortie neuf.
La spécification peut déclarer `surface_exploration` en plus des cycles source.
Elle donne sa version, ses demandes `paths`, les budgets du graphe et
`max_output_bytes`. Chaque demande contient `id`, `domain_region_ids`, `start`
et `end`. Les sélecteurs de frontières utilisent l'alias `source` et un ID de
cycle déclaré dans la même spécification. Le repère vient du profil natif
authentifié ; aucune coordonnée d'extrémité libre n'est ajoutée.

La revue réutilise les contrôles de corps natif réouvert, pose, source,
triangulation, adapter et fichiers d'origine. Elle fige `source-paths.json`
avant l'exploration, puis produit `surface-paths.json` et un diagramme bleu
ouvert `surface-paths.svg`. Les projections rouges des cycles source restent
séparées. La référence au snapshot est acyclique et vérifiable par empreinte.

Les budgets parent couvrent lecture, calcul et publication ; le délai de
l'exploration commence avant la copie et la sérialisation du snapshot source.
Le scan supplémentaire d'arêtes est chargé au budget cumulé. Le plafond de
sortie couvre le bundle et son marqueur final. Une interruption conserve les
rapports mais n'accorde pas un marqueur de publication complète.

Cette préparation crée des fichiers de revue. Elle ne modifie ni le profil
corporel ni SQLite, n'exécute pas Blender et ne reporte aucune décision
anatomique existante sur un résultat différent. Sans cette option, les sorties
et le comportement historiques sont conservés, avec les nouvelles identités
normales du code. Vérifier la version du runtime : cette capacité n'est pas
disponible dans le build 0704 connecté lors du développement.

L'appel du handler public en processus de développement sur le corps accepté
termine en 1,904 s. Il conserve profil et état SQLite, authentifie l'origine
native et reproduit exactement les deux trajets déjà examinés : mêmes
sommets, points, faces porteuses, longueurs et repère. Ce rejeu ne réattribue
aucun gate. Trente tests ciblés passent ; le P2 de démarrage du sous-délai
est corrigé et la revue finale ne relève aucune autre anomalie P1/P2.

[Preuve de l'opération publique](automation-body-surface-facade-evidence-20261007.json).
