# Évaluer le réglage des mannequins par mensurations

La demande du 3 octobre 2026 ajoute au développement l'évaluation des contrôles
de stature, poitrine, taille, hanches, largeur d'épaules et longueurs des membres.
Les deux bases réalistes Blender CC0 sont éditables, mais leur éditabilité ne
constitue pas un système paramétrique de mensurations.

## Capacités constatées sur les candidats

Les bases extraites de Human Base Meshes v1.4.1 n'ont ni shape keys, ni groupes
de sommets, ni armature, ni drivers. Le modificateur Multires des originaux
ajoute des détails ; il ne règle pas les mensurations. Les régions sculptées
sont conservées et peuvent alimenter une segmentation anatomique sourcée.
La preuve native de cette inspection est conservée sur G: avec le candidat.

La mesure sans segmentation a inclus une partie des bras dans une section
de poitrine. Le profil doit utiliser la segmentation source ou les poids d'un
rig qualifié, conserver les sections ambiguës et ouvrir la revue anatomique.
Les noms de régions/os fournissent des guides, jamais une validation physique.

## Dérivation à qualifier

Conserver le corps original et préparer une variante séparée liée à ses
empreintes. Utiliser un cadre commun, des régions et une cage/rig contrôlés.
Une échelle selon la stature ne règle ni les tours ni les membres séparément.
Pour les tours, limiter les déformations régionales, puis remesurer le mesh
évalué aux sections homologues. Pour épaules et membres, déplacer les repères
anatomiques et adapter les poids/cages, puis vérifier les articulations et les
contacts dans la pose utilisée. Ne pas confondre longueur d'os et longueur
anatomique mesurée sur la surface.

Avant chaque variante, enregistrer les cibles en cm, le mesh/pose de départ,
les contrôles admis, budgets de déplacement et de déformation, tolérances de
mesure et nombre maximal d'itérations. Conserver le meilleur candidat admissible,
les résidus par mesure et les défauts localisés. Une cible incompatible, un
contrôle absent ou une proportion extrême doit donner un refus utile ; une
approximation ne doit pas être présentée comme la mensuration obtenue.

Tout changement du corps invalide profil, enveloppe de collision, placement et
preuves dépendantes. Les patrons approuvés restent inchangés. Une incompatibilité
de coupe exige une proposition de variante distincte et sa revue.

**État actuel :** inspection des contrôles et profil géométrique en développement.
Réglage indépendant des mensurations, rig déformant, enveloppe et fitting non
qualifiés. Le catalogue ne doit pas annoncer ces capacités avant leurs gates.

## Procédure codée de stature et de surface d'épaule

`a3d.body_dimensions.variant_by_stature` calcule une variante uniforme en cm,
dans le cadre déclaré, à partir de la stature mesurée. Le plan des pieds, les
faces et l'original sont conservés. Les repères suivent la même transformation,
et `profile_mesh` remesure la variante. Le reçu lie le calcul, la géométrie,
la pose et le cache ; il reste `HEIGHT_ONLY`. Les tours obtenus ne sont pas
des cibles approuvées. Il n'y a ni retouche géométrique par IA ni résolution
indépendante de poitrine/taille/hanches dans cette fonction.

`a3d.shoulder_surface.measured_surface_shoulders` calcule les sorties vers
le haut depuis les centres articulaires sur les triangles natifs évalués.
Il refuse une source ou une pose différente et une sortie ambiguë. Le guide
du haut du torse consomme les points de surface liés au nouveau cache ; les
centres articulaires restent disponibles pour le rig. Cette correction de
repère ne garantit pas à elle seule l'absence de pénétrations du vêtement.

Les appels natifs doivent enregistrer les artefacts et reçus exacts, préserver
les admissions du projet, et refaire métriques et contacts sur chaque variante.
Un contrôle indisponible doit rester un refus utile, sans boucle de retouches
improvisées de l'agent. Ces fonctions sont en développement et ne sont pas
encore publiées dans une nouvelle installation du plugin.
