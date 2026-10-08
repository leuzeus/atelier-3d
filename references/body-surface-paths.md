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
