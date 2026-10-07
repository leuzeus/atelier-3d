# Variantes de patrons pour une intention d’aisance explicite

`a3d.pattern_ease_variant` prépare une proposition séparée. Il consomme un dossier compilé exact, les packages source, une décision numérique explicite et une politique de gradation versionnée. Le résultat conserve les identifiants des pièces et des bords nommés, les types et orientations des raccords, les crans, les couches et le sens du fil. Les faces et indices restent identiques sauf densification explicitement déclarée et tracée. Le corps et les originaux restent immuables. Aucun résultat ne vaut acceptation de la variante, homologation anatomique, simulation, fitting ou décision artistique.

La façade `prepare_project_pattern_ease_variant(project, compiled_dossier_path, design_decision_path, policy_path, output_dir)` recompile les sources et exige les décisions humaines canoniques `ease-design.<component_id>`. Chaque décision doit référencer exactement les fichiers de décision, corps, dossier, proposition numérique et revue. Elle écrit uniquement dans un nouveau répertoire sous `variants/`, sans attacher les archives au projet de production ni inscrire une preuve dans son état canonique. Les fichiers source sont contrôlés avant et après le calcul ; les versions précédentes sont conservées.

| Mode déclaré | Transformation | Limite |
|---|---|---|
| `AFFINE_SOURCE_UV` | Facteurs U et V bornés, autour d’un sommet source explicitement choisi pour chaque pièce. | Des facteurs de largeur différents sur manche et manchette peuvent rendre leur raccord permanent incompatible. Le meilleur candidat et ses résidus sont conservés, avec refus de packaging. |
| `WIDTH_BY_V_STATIONS` | Facteur U interpolé entre stations V déclarées, autour du centre des bornes U source ; V et le fil longitudinal sont conservés. | Sans option de densification, chaque station doit correspondre à une hauteur présente dans les sommets source. Une loi théorique sans sommet exporté ne crée aucune largeur locale. |
| `WEIGHTED_SOURCE_UV` (branche de développement) | Déplacement affine pondéré par sommet source, avec bords protégés explicitement déclarés à poids nul. | Les poids, ancres et bornes sont des données de recette. Les faces triangulaires source définissent le transport des annotations ; aucun sommet proche ne remplace une correspondance exacte. Une famille locale peut rester incapable d'atteindre la cible. |

Le domaine de développement `ASSEMBLED_SOURCE_PATH_TARGET_ONLY` accepte une
cible absolue d'un cycle source fermé par des ponts permanents, avec une
référence corporelle authentifiée et une aisance totale explicitement revue.
Il n'invente ni décomposition mouvement/style/sous-couches ni tour corporel
horizontal. Le trajet UV conserve `open_material_span` ; la preuve de cycle
assemblé est recalculée séparément, avant et après gradation. Le consommateur
historique de fitting fermé et ses critères ne changent pas.

`a3d.boundary_grading_policy` prépare les familles locales depuis une ligne
source entièrement attachée et ses vrais partenaires. Les protections sont
explicites pour chaque pièce ; les points hors de la zone d'encolure gardent
leur poids nul. La bande accumule l'expansion sur les intervalles dont les
partenaires peuvent bouger. Cette première méthode couvre une ligne constante
en V, avec un cycle permanent et une couverture complète des attaches. Une
ligne ouverte, une attache détachable, une rangée incomplète ou une autre
paramétrisation demande une méthode dédiée. Ce domaine est commun aux patrons
qui présentent cette construction ; aucun identifiant de vêtement ou placement
3D propre au projet n'est codé dans le noyau.

Le profil `SOURCE_ARC_QUADRATIC_TAPER` peut diminuer progressivement les poids
le long du vrai trajet d'encolure d'un partenaire (`4t(1-t)`), avec les bords
protégés toujours à zéro. Les trajets ouverts uniques sont reconstruits depuis
leurs indices source ; les branches, boucles ou parties déconnectées sont
refusées. Une pièce entièrement protégée reçoit des paramètres fixes ; ses
intervalles peuvent être transportés rigidement dans la bande sans allonger
leurs coutures. La barrière géométrique du solveur conserve un meilleur
candidat aux contours simples et aux faces non inversées ; un essai refusé
ne le remplace pas. Les différences finies et la recherche de pas restent
bornées. Le contrôle terminal de temps inclut le diff et les hashes avant
de déclarer une proposition admissible pour revue.

Les décisions numériques de ce domaine passent par
`a3d.source_path_intent.review_source_path_intent`, qui authentifie le choix
humain canonique, les fichiers exacts, le corps et le cycle matériel. Les
archives proposées restent séparées et exigent une revue des patrons avant
adoption. La visibilité du devant central et son retrait entre couches restent
des contrôles distincts du dimensionnement de l'encolure. Ces extensions ne
sont pas encore chargées dans l'installation 0701.

L’option `densification` utilise `SOURCE_BOUNDARY_V_STATIONS` et la politique de faces `SOURCE_TRIANGLE_BOUNDARY_SUBDIVISION`. Elle insère des points aux niveaux V explicitement déclarés sur les deux bords existants d’une même couture permanente de manche. Le nombre de points par pièce et la longueur minimale des nouveaux segments sont bornés. Les points sont interpolés sur les segments source immuables ; leur bord, fraction d’arc, paire de sommets source, fraction de segment et nouvel indice sont enregistrés. Les anciens sommets gardent une correspondance exacte. Cette première option exige un contour de coupe égal au contour cousu et une marge nulle ; d’autres marges demandent une politique de coupe explicite.

Les triangles source doivent couvrir leur contour une fois, avec une orientation et des incidences cohérentes. Seuls ceux adjacents aux bords insérés sont subdivisés, puis chaque face source référence ses triangles de variante. Le contour final et la couverture des triangles sont vérifiés par le validateur de cage existant ; aucun triangulateur nouveau n’est introduit. `topology_changed=True` décrit l’insertion réelle. Cette charge utile peut être consommée par les guides de membres existants ; cela ne qualifie ni sa métrique 3D ni les contacts. Il faut comparer le meilleur candidat sans insertion et celui avec insertion au **même niveau V nominal**, en mesurant le polygone réellement exporté, la bosse, les raccords et les déplacements.

Les chemins de gradation sont des chemins **nominaux de conception** déclarés par bords et fractions d’arc. `SOURCE_V_CM` impose une hauteur V explicite et recalcule les fractions sur les vrais bords transformés avant de contrôler le chemin et ses raccords ; ce mode exige une longueur V conservée. `NORMALIZED_ARC_PATH_VARIANT` garde les fractions normalisées, avec un libellé distinct et aucune hauteur V implicite. La politique choisit `BOUNDS` pour préserver une dimension déjà dans la plage approuvée ou `TARGET` pour chercher la cible centrale. Une manchette déjà admissible à cette comparaison nominale conserve ainsi ses 25 cm sans réglage artificiel vers le centre de la plage.

Un `nominal_basis_ref` facultatif référence le fichier exact ayant servi à déclarer ces niveaux. La façade authentifie également ses références d’entrée avant et après le calcul. Choisir un V partagé par les deux extrémités d’une proposition oblique crée un contrôle horizontal nominal distinct ; sa longueur ne remplace jamais celle de la courbe oblique ni son homologie en attente.

Ces chemins peuvent dimensionner les manches et manchettes depuis une cible numérique approuvée, tout en gardant l’homologie réelle `PENDING`. Le tour corporel et son aisance pour le torse ou le col ouverts restent une enveloppe spatiale de référence. Le code ne les transforme pas en une circonférence textile fermée ; couverture et chevauchement restent `NEEDS_DATA`. La planche `review-patterns.svg` superpose les vrais polygones source et proposés et les segments nominaux mesurés ; son agencement visuel ne modifie aucune coordonnée UV.

Le solveur borné utilise les résidus mesurés sur les coordonnées réellement exportées, un Jacobien par différences finies, un système amorti et une recherche de pas. Tous les bords permanents sont remesurés après transformation. Les coutures d’une même pièce doivent également conserver des incréments d’arc homologues après application de leur orientation. Les facteurs, budgets, critères dimensionnels, causes d’arrêt, candidat conservé et diff pièce par pièce figurent dans la proposition. Un budget épuisé produit `INCOMPLETE_BUDGET`, conserve le meilleur candidat et interdit la construction des archives. Les critères de contact, de métrique en placement et de fitting existants restent indépendants.

La politique de crans est `PRESERVE_MATERIAL_POINTS` par défaut. Le vrai point source est retrouvé sur la frontière avant gradation, puis transporté par l’interpolation de ses sommets effectivement exportés. Sa fraction est recalculée sur le nouvel arc : conserver un chiffre ne garantit pas la conservation du point matériel. Pour une couture unaire, `seam_side_positions={"a":fA,"b":fB}` représente les deux fractions remappées, sous le même identifiant de cran ; elles doivent correspondre à l’orientation de couture. Une incohérence de partenaires interdit les archives. Le diff distingue les identifiants conservés, les annotations JSON modifiées et les points matériels conservés, avec coordonnées et résidus. Les pièces sans cran applicable n’ont pas de contrainte fictive.

`NORMALIZED_ARC_FRACTIONS` est un autre choix explicite de variante à revoir. Il conserve les fractions et mesure le déplacement matériel qui en résulte ; tout déplacement est signalé `NORMALIZED_ARC_NOTCH_REPOSITIONING_PROPOSED`, avec acceptation non accordée. Ce mode ne prétend jamais préserver les crans matériels. Les propositions antérieures ne comportant pas cette observation restent historiques et ne servent pas de preuve de conservation des crans.

Les archives sont créées par le constructeur de packages existant seulement si les contraintes nominales, raccords permanents et patrons manufacturiers sont compatibles. Leur charge utile géométrique est déterministe pour les mêmes données et paramètres ; leurs UUID et dates de manifeste restent ceux du constructeur existant. Les textes descriptifs des sources sont préservés comme historique et doivent être revus pour la variante. Une archive créée demeure `PATTERN_PROPOSAL_ONLY` ; il faut ensuite examiner les patrons exacts, recompiler les entrées et guides, revoir les homologues et la couverture, puis rejouer la préparation native avant toute qualification physique.
