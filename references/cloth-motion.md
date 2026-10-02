# Lire le déplacement Cloth sans le confondre avec une instabilité

`max_displacement_cm` contrôle la plus grande distance euclidienne d'un sommet
depuis sa position au début de la phase. Le maximum rencontré pendant la phase
déclenche le refus dès qu'il dépasse ce budget. Ce contrôle reste inchangé.
Un bas de panneau qui se rapproche du corps peut parcourir une grande distance :
un FAIL de budget ne prouve donc pas seul une explosion numérique, une coupe
trop petite, une vitesse excessive ou un défaut du solveur.

## Mesures natives 0.5.9

Chaque ligne `frames` conserve `max_movement_cm`, `max_seam_gap_cm` et `motion`.
L'image qui déclenche le refus est enregistrée avant l'arrêt. Lire ces valeurs
avec `inspect_sewing_failure(component_id, attempt_dir)`, via le code exact
de `studio_blender_operation`, même après restauration du checkpoint.

- `motion.max_excursion` : maximum depuis le départ de phase.
- `motion.max_increment` : maximum entre `previous_frame` et `frame`, sur les
  positions effectivement évaluées de ces deux images. Ce n'est pas une vitesse
  interne du solveur ni une mesure de ses sous-pas. L'image 1 est comparée au
  placement initial, repéré comme image 0.
- Les deux maxima peuvent désigner des sommets différents. Ne jamais soustraire
  deux maxima scalaires pour calculer un déplacement incrémental.
- Chaque maximum contient `index`, `source_vertex_index`, `piece`, `from_cm`,
  `to_cm`, `delta_cm`, `distance_cm`, `rest_uv_cm`, `named_edges`, `pin_weight`.
  Les indices source d'un essai local renvoient au mapping complet ; pour un
  probe ils appartiennent au coupon synthétique, conformément à `mapping_domain`.
- Le diagnostic d'échec conserve aussi `geometry.motion.pieces`, avec un maximum
  de chaque type par pièce. L'historique conserve seulement les deux maxima
  globaux, sans recopier toutes les positions à chaque image.
- `budget_cm` est le seuil de la recette exécutée ; `budget_exceeded` ne modifie
  ni la recette ni le statut FAIL. Géométrie absente/non finie : UNAVAILABLE.

Un ancien diagnostic avec positions initiales/finales permet de retrouver
l'excursion en lecture seule. Sans positions de l'image précédente, l'incrément
reste `NOT_RECORDED`. Les octets et SHA historiques restent intacts. Un seuil
historique absent reste null ; aucun seuil actuel n'est substitué.

## Choisir la prochaine hypothèse

1. Distinguer stade probe/vêtement et vérifier les paramètres réellement exécutés.
   Comparer les compteurs de déformation à une même image ; des arrêts à des
   images différentes ne donnent pas un classement de stabilité.
2. Localiser le maximum : bas libre, couture ou appui. Lire excursion ET incrément,
   écarts des coutures et déformations ; aucun de ces signaux seul n'établit la cause.
3. Utiliser `inspect_sewing_placement` pour les ancres source, positions et poids,
   distances aux partenaires, contacts et trajets. Un appui conserve son emplacement
   initial : renforcer un appui loin de sa cible peut empêcher la couture de fermer.
   Un pin de poids faible n'est pas une attache au corps ou au partenaire de couture.
4. Choisir une seule variation traçable de placement OU appui, avec bornes en cm
   ou en poids et durée déclarée. Rebuild natif si placement/pins changent ; passer
   les précontrôles et examiner les pixels avant Cloth. Conserver coupe, collider,
   topologie prévue et seuils. Un refus géométrique interdit l'essai Cloth.
5. `mount` et `drape` ont déjà leurs profils indépendants. Adapter une phase sur
   une hypothèse distincte exige une nouvelle preuve locale ; ne pas multiplier
   les essais de rigidité ou relever le budget pour obtenir un PASS.
6. Les fitting_tacks restent locaux et temporaires. Retirer ces attaches et
   refaire local sur la recette correspondante avant full/freeze. Un appui
   temporaire proposé pour le montage doit également être retiré et sa stabilité
   vérifiée ; une simple proposition ne prouve pas cette transition.

Une proposition de placement reste une hypothèse jusqu'à son essai. Une correction
de coupe exige un déficit homologué et le board exact de sa variante ; des repères
supposés/proxy ne suffisent pas. Aucun nouveau board n'est demandé pour une coupe
inchangée. Ni fixture PASS, ni release publiée ne qualifie le vêtement consommateur.

## Comparer deux méthodes d'assemblage

Des surfaces déjà préformées en 3D puis dépliées en repos 2D ont un point de départ
différent des patrons approuvés placés par flat/cylinder. Des racines de manches
construites sur les sommets du buste partagent déjà son emmanchure ; des pièces
indépendantes nécessitent un montage correspondant. Ne pas remplacer implicitement
la coupe source pour reproduire une silhouette préformée.

Une union indexée des seuls partenaires permanents peut donner une continuité
géométrique malgré des écarts résiduels, puis être suivie d'une relaxation.
Ce résultat n'est pas une convergence de tous les ressorts. Le contrat actuel
exige full PASS puis les distances weld_gap avant union ; A06 et autres closures
restent réversibles. Ce correctif ne change pas cette politique.

Un éventuel assemblage géométrique assisté serait une méthode à proposer
explicitement, avec limites de déplacement, déformation, topologie, contacts,
relaxation et revue humaine. Il n'est pas implémenté ici. L'ordre buste/jupe/capuche
peut guider un futur montage, mais trial_pieces conserve des pièces entières :
un panneau buste-jupe ne devient pas un petit coupon par une simple sélection.

## Vérification ciblée

`python -B -m unittest tests.test_sewing_diagnostics -v` vérifie les maxima distincts,
le mapping local/source, la non-mutation et les données historiques manquantes.
`tests/native_motion_smoke.py` provoque un dépassement réel de budget sur un coupon
dans Blender : dernière image, incrément, recette et mesh préservés, nettoyage.
Les régressions natives de conservation après restauration et local/full/freeze
restent applicables. Les fixtures générées sous `work/` ne sont pas distribuées.
