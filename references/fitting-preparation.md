# Enveloppe auxiliaire, pose commune et matières régionales — 0.6.5

Une présence de corps dans la scène ne déclare ni pose commune ni enfilage.
Le diagnostic `donning.missing` précise l'absence d'enveloppe, de colliders et
d'épaisseurs, de repères/pose et de chemins de mesure homologues. Sans collider,
la collision est `NOT_EXECUTED_NO_COLLIDER`. Le montage libre reste lisible.

## Enveloppe depuis la référence native

Investiguer d'abord les colliders disponibles : identité source, pose, dimensions,
fermeture, normales et couverture du corps choisi. Un ancien mannequin fermé
peut néanmoins avoir des bras ou mains dans une autre pose. Ne pas le rebaptiser
`target` ni diminuer le squelette pour obtenir un passage.

Préparer `prepare_body_reference(selection_path)` selon
[le contrat de corps source](clean-construction-fitting.md). Son reçu natif,
son artifact et leur SHA sont les entrées de `fitting-envelope.schema.json`.
Le Studio accepte ensuite :

```json
{"operation":"prepare_fitting_envelope","arguments":{"envelope_path":"fitting/envelope.json"}}
```

La description répartit explicitement tous les meshes du corps entre régions.
Une région peut être partitionnée par proximité aux segments des os **évalués**
du reçu, pour séparer les deux jambes ou l'avant-bras. Cette proximité est une
construction géométrique auxiliaire, pas une classification anatomique validée.
Chaque région fournit un hull ; un padding explicite et une union voxel limitée
produisent une enveloppe fermée. Seul cet auxiliaire est remeshed. Le corps cible,
les patrons et la scène live restent inchangés. Une partition vide est rapportée,
sans inventer de géométrie pour un os sans points source.

L'opération vérifie normales vers l'extérieur, volume signé positif, absence
d'arêtes non manifold, couverture de **tous** les sommets du corps dans la
tolérance, épaisseurs réellement assignées et limites natives. Elle écrit un
`.blend` contenant uniquement l'auxiliaire et un reçu avec régions, bornes,
couverture, source, pose et empreintes. L'enveloppe est
`NOT_VALIDATED_GEOMETRIC_PROXY` : la couverture d'un squelette ne prouve pas la
silhouette d'un corps habillé. Examiner ses pixels avant utilisation.

Après le full libre courant, importer l'auxiliaire avec
`introduce_fitting_context(component_id,recipe_path,fit_path,source_blend,source_sha256)`.
Dans la fiche fitting, conserver le corps exact sous `body.role=target`, et
déclarer l'auxiliaire sous `envelope.role=proxy`. Déclarer sa même géométrie,
ses épaisseurs et son rôle `mannequin` dans la recette. Un auxiliaire natif lié
à une autre géométrie de corps est refusé.

## Préparer puis appliquer une pose continue

```json
{"operation":"prepare_fitting_pose","arguments":{"component_id":"garment.coat","recipe_path":"sewing/free-assembly.json","pose_path":"fitting/common-pose.json"}}
```

`fitting-pose.schema.json` référence le reçu du corps. Chaque cadre relie des
bords source nommés (origine, axe, transverse) aux endpoints des os évalués.
Les centres et distances sont mesurés sur la géométrie courante ; le cadre
transverse cible est un vecteur explicite dans le même espace monde. Déclarer
la provenance et la tolérance de différence de longueur. Une différence au-delà
de cette tolérance est refusée ; la normalisation de l'orientation ne met pas le
vêtement à l'échelle et ne corrige pas une longueur de manche inadéquate.

Le champ combine les déplacements rigides des groupes de panneaux et un raccord
continu par distance sur le graphe du vêtement et de ses coutures permanentes.
Les pins fixes ont une influence nulle. La fermeture A06 reste réversible ; elle
ne participe pas aux liens permanents du graphe. Chaque pas vérifie les mêmes
seuils de qualité/stretch, le budget de déplacement et la séparation des partenaires
de couture. Un refus ne modifie pas la scène ni SQLite. Aucun solver de recherche,
scale global, projection sur le corps ou changement de FlatRest n'est appliqué.
Une relaxation optionnelle bornée peut projeter les seules contraintes de longueur
des arêtes structurelles, avec une petite marge **à l'intérieur** des seuils.
Elle maintient aussi la borne d'écart des partenaires permanents, sans les fusionner.
Elle doit aussi respecter la tolérance explicite des cadres mesurés. Elle ne
change pas les seuils et ne force aucun contact. Toute non-convergence est un refus.

L'artifact préparé contient les positions et cadres mesurés, liés au mesh courant,
à sa map, à la recette structurelle et au corps exact. Sa préparation ne vaut pas
acceptation anatomique. Déclarer son `{path,sha256}` sous `recipe.fitting_pose` puis
appeler `prepare_sewn_stage(...,stage="fitting")`. Cette mutation garde son
checkpoint et vérifie à nouveau les identités, pins, qualité et contacts avant
de créer une copie versionnée. Elle refuse un mélange avec `fitting_placement`.
Un contact profond doit être diagnostiqué ; le champ ne force pas le passage.

Exécuter ensuite un local avec `purpose="fitting"`, dans cette pose, avant le
full. Aucune qualification d'un coupon ou d'une fixture ne se transfère à l'asset.
Les sections homologues et chemins fermés avec aisance restent à mesurer pour
qualifier la capacité de la coupe. Le drapé et la silhouette doivent être revus
de face/profil/dos sur le corps choisi.

## Intention au board et qualification dans Blender

Au board, décrire par patron la matière présumée, le droit-fil, les couches,
renforts, plages hypothétiques de masse/épaisseur et la tenue des plis visée.
Nommer quelques profils partagés : tissu principal, doublure éventuelle, renfort
local. Une image ne donne pas une solution unique des coefficients physiques.
Décrire les hypothèses dans les caractéristiques/construction des pièces et le
dossier technique. Ne pas créer un optimiseur ou un coefficient arbitraire pour
chaque panneau de même matière. Ne pas modifier un board approuvé uniquement
pour calibrer une recette technique sans changer sa conception.

Dans chaque phase de recette, `regional_stiffness` est facultatif :

- `profiles` : jusqu'à huit profils partagés, IDs, provenance, `status=hypothesis`,
  poids `structural_weight`, `shear_weight`, `bending_weight` entre 0 et 1 ;
- `default_profile` et `assignments` : correspondance explicite par ID de patron ;
- `reinforcements` : ID de patron, bord nommé, profil, largeur en cm ; transition
  linéaire depuis le bord sur les coordonnées **2D du repos**, indépendante de la pose ;
- `ceilings` : maxima tension/compression/cisaillement/flexion, au moins égaux
  aux bases de la phase et dans les plages RNA de Blender.

Le backend configure les trois groupes natifs de rigidité. Le groupe structural
est partagé entre tension et compression. Les poids sont des contrôles Blender,
pas des constantes de tissu mesurées ; aucune physique chaîne/trame indépendante
n'est promise. Les maxima, groupes et poids exécutés figurent dans le rapport et
le snapshot vérifié pendant la simulation. Le local remappe les indices source ;
les stages conservent les descriptions source et reconstruisent les poids.
Tout coefficient tronqué et toute modification des groupes exécutés sont refusés.
Une recette sans groupes garde le fonctionnement uniforme.

Calibrer un petit coupon par profil, puis le sous-ensemble réel dans la pose
qualifiée. Garder géométrie, masse, maillage, pins, gravité et seuils fixes ; varier
un paramètre à la fois. Distinguer profil de montage et comportement final, ainsi
que facettes d'affichage et résistance physique. Changer la recette invalide les
preuves techniques qui la référencent, sans demander une nouvelle approbation du
découpage inchangé. Préserver les limites de couture/contact/stretch/consolidation.

Références primaires : [groupes de rigidité Cloth](https://docs.blender.org/manual/it/5.1/physics/cloth/settings/property_weights.html),
[propriétés natives ClothSettings](https://docs.blender.org/api/5.2/bpy.types.ClothSettings.html).
