# Composition d'une variante de patrons revue

Les fonctions pures de `a3d.pattern_variant_composition` préparent les entrées
d'une variante limitée à une liste explicite de pièces. Elles ne modifient pas
le projet, ses packages, ses décisions ou ses états d'exécution.

`verify_pattern_variant_scope` compare les deux contenus `garment.json` :
inventaire et IDs des pièces, IDs des bords nommés, données globales, coutures,
matière et pièces hors périmètre doivent rester exacts. Seule la géométrie des
pièces explicitement sélectionnées peut changer. Le résultat décrit les pièces
modifiées et les identités comparées ; le consommateur authentifie séparément
les archives et la décision humaine portant sur ces pièces.

`compose_pattern_variant_dossier` conserve l'ordre du dossier original et toutes
ses lignes hors périmètre, puis copie exactement les lignes sélectionnées du
dossier variante. Chaque différence incidente exclue est rapportée avec son
chemin JSON, ses valeurs et les empreintes des lignes. Le calcul ne tolère
aucun epsilon, y compris une différence d'un seul ULP dans un cran. Les crans
sont identifiés par `(seam_id, id)` ; les plis par `id`.

La composition réelle des deux manches acceptées conserve les treize autres
pièces textiles et la boucle. Elle exclut les différences incidentes de dix
lignes du dossier variante, sans remplacer les originaux. Les seules pièces
modifiées dans le package manteau sont `sleeve-left` et `sleeve-right`.

La portée du résultat reste `COMPOSED_INPUTS_ONLY`, `qualification: NONE`.
Construction, fitting, permission et revue humaine restent `NOT_GRANTED` par
ces helpers. L'intégration canonique doit encore vérifier les décisions humaines
existantes et les sources exactes, puis contrôler les contrats complets avant
toute admission. Aucun succès de cette composition ne transfère des preuves
physiques ou une acceptation artistique.
