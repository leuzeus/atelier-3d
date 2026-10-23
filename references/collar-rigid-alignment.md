# Seed rigide du col avant le couplage source

`a3d.rigid_guide_alignment.prepare_role_rigid_seeds` prépare une proposition
rigide pour le rôle explicite `collar`. Le caller existant
`source_seam_coupling.couple_source_seams` la demande déjà lorsque des
sémantiques explicites sont fournies, avant la moyenne des cohortes de couture.
Aucun caller, schéma, gate ou patron n'est modifié par cette capacité.

## Entrées et ordre

Le caller a préalablement validé le composant, ses coutures, la recette, les
guides et les identités du maillage auxiliaire, puis construit leurs partitions
communes. L'API interne reçoit ces `states`, les `witnesses` source et la même
instance `_Budget` que la préparation. Elle ne remaille ni ne resample.

Le chemin historique `inner_front` reste identique dans
`_prepare_front_rigid_seeds`. Le col utilise ensuite un snapshot des positions
partenaires proposées par ce chemin. Une vue des états fournit ces positions
à `_complete_rows` : `states`, contrôles originaux et témoins ne sont pas
mutés. Les témoins sont recalculés par leurs chaînes et partitions source
existantes, avec leur orientation déclarée ; aucune recherche par proximité
n'est faite. Les coordonnées du devant intérieur avant son seed ne sont pas
réutilisées comme cible du col après son déplacement.

Toutes les relations permanentes déclarées du col doivent avoir exactement un
témoin complet et tous leurs partenaires préparés. Le reçu localise leurs IDs,
les contrôles utilisés et les empreintes des positions partenaires. Les
relations `closure` et `detachable` sont listées comme exclues. Une relation
col–col, y compris une relation unaire, demande un solveur conjoint distinct et
produit `COLLAR_JOINT_SEED_NOT_SUPPORTED`. Une pièce absente, une partition
incomplète ou un témoin ambigu produit `INCOMPLETE_CORRESPONDENCES`.

## Calcul et préservation

`proper_rigid_fit` conserve son calcul Horn/Jacobi, ses bornes numériques IEEE,
son plafond de rotations et ses refus de rang. Le seed ne contient qu'une
rotation propre et une translation : aucun facteur d'échelle ou reflet.
Il transforme tous les contrôles originaux du col avec le même mouvement,
y compris les contrôles intérieurs. Les IDs, UV, triangles, supports source,
paramètres de chaînes, crans et annotations source restent conservés. Une
annotation transportée n'acquiert pas le statut de pin physique ou de
contrainte spatiale validée.

Une seule proposition est calculée. Elle est appliquée uniquement si son
résidu RMS pondéré diminue strictement ; sinon les positions originales sont
conservées sans retry, seuil supplémentaire ou projection. Les résidus par
relation, le nombre de contrôles et le déplacement du seed sont rapportés.
Une incompatibilité qui demande une déformation reste un résidu mesuré ;
elle n'autorise pas une mise à l'échelle ni une acceptation. Les tolérances
source et critères finaux existants restent inchangés.

L'instance de budget n'est ni recréée ni remise à zéro. Aucun contrôle ou
triangle supplémentaire n'est produit ; les réservations existantes de
préparation sont conservées, avec contrôles de délai pendant le calcul,
transport, diagnostics et hashes finaux. La somme des correspondances du col
est contrôlée avant construction des lignes contre `max_controls` existant.
Les empreintes avant/après lient source, sémantiques, contrôles, témoins et
structures d'identité effectivement utilisées. Les fonctions d'évaluation
déjà préparées ne sont ni exécutées ni sérialisées par le seed.

## Portée des résultats

Une proposition appliquée porte `PARTIAL_RIGID_SEED_APPLIED`,
`PARTIAL_TEST_ONLY`, `qualification: NONE` et `whole_piece_admission: false`.
Même un résidu nul n'admet ni placement, couverture, métrique ou contacts.
Le reçu distingue `MEASURED_ONLY_NO_ACCEPTANCE_BOUND` des étapes
`metric_after_coupling`, `contacts` et `interior_propagation`, toutes
`NOT_ASSESSED`. La moyenne des cohortes pourra encore déformer la métrique :
elle exige ses propres contrôles sur une nouvelle référence complète.

La capacité ne résout pas la propagation d'un déplacement de bord vers
l'intérieur et ne qualifie pas les 48 faces non conformes du champ auxiliaire
historique. Aucun nouvel essai réel, calcul de champ, observer, Cloth ou
fitting n'est exécuté dans cette unité. La revue indépendante du candidat et
une nouvelle référence complète contrôlée précèdent l'exécution réelle.

## Vérification portable

Les tests ciblés couvrent des cols et partenaires congruents, le partenaire
`inner_front` déjà placé, les partitions complètes dans les deux directions,
les relations non permanentes, les témoins manquants ou mutés, le rang
insuffisant, la conservation des distances et des décalages UV, ainsi que le
budget partagé et l'expiration pendant les derniers travaux. Les chemins sans
sémantiques conservent leurs résultats historiques exacts. Pour le chemin
`inner_front`, les positions et reçus de pièces sont exacts ; l'empreinte du
module modifié change volontairement et invalide les preuves dépendantes.
Ces fixtures restent des preuves de code, sans admission de vêtement.
