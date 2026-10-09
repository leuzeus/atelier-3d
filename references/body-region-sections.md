# Supplément de mesures des bras et enveloppes des mains

Le service `a3d.body_region_sections` mesure la géométrie capturée du corps dans
un supplément séparé. Il ne réécrit ni le mannequin approuvé, ni ses mensurations,
ni sa cible anatomique. Une classification « ample » ne fournit aucune valeur
d'aisance à ce service.

## Entrées et authentification

La politique suit `schemas/body-region-sections.schema.json`. Elle désigne les
références exactes du profil, de la géométrie et des triangles natifs, leurs
empreintes sémantiques, la pose, la source et les régions de faces. Chaque région
déclare ses repères de début/fin, les fractions et les deux bornes du domaine
échantillonné, les faces source et l'axe du cadre corporel à projeter dans le plan.
Cet axe doit être explicite et non parallèle à la normale du membre.

Les domaines disponibles sont `SHOULDER_TO_ELBOW_ONLY` et
`WRIST_TO_ELBOW_ONLY`. L'ordre des deux repères correspond à celui des fractions.
Un poignet ou un centroïde articulaire fournit un repère de plan ; sa distance
à un autre repère ne devient jamais un tour anatomique.

`measure_project_body_regions(project, specification_path)` vérifie les fichiers
et une origine native réellement enregistrée dans SQLite. Il accepte un corps
créé par `prepare_body_target` ou introduit dans le laboratoire courant par
`introduce_body_target`. Le second parcours vérifie aussi le descriptor de
contexte, le reçu de cible, la liaison, les artefacts et la géométrie exacts.
Une déclaration client signée, un label `MEASURED` ou une copie de reçu sans
origine canonique ne satisfait pas cette vérification.

La fonction portable `measure_body_regions(profile, geometry, triangles,
specification, adapter=None, source_geometry=None)` ne vérifie pas SQLite. Son
résultat annonce explicitement cette limite. Elle sert au calcul et aux tests.

## Contours réellement mesurés

Le plan passe par le point déclaré du segment et est perpendiculaire à son axe
source. L'intersection utilise les triangles natifs authentifiés. Les segments
sont joints par leurs identités de sommets ou d'arêtes ; aucune proximité ne
fusionne deux surfaces distinctes.

Le domaine doit produire un seul contour simple fermé contenant l'axe sourcé.
Une section vide, ouverte, branchée, coplanaire, ambiguë ou composée de plusieurs
boucles reste refusée. Un domaine refusé n'est pas déplacé pour obtenir une
mesure. Le périmètre est celui de ce contour de peau, sans boîte englobante ni
enveloppe convexe. La tolérance numérique et sa borne sont rapportées ; l'erreur
de discrétisation du maillage n'est pas estimée.

Les identifiants des sections sont `region.id + '.section.' + index`, où l'index
désigne la liste ordonnée des fractions déclarées. Par exemple, pour une région
`forearm.left` orientée poignet vers coude aux fractions `[0, 0.5, 1]`, le
poignet est `forearm.left.section.0`. Un contour oblique reste exprimé en
coordonnées mondiales avec sa normale et son centre. Il ne reçoit pas de hauteur
horizontale fictive.

La couverture vaut `DECLARED_SAMPLES_ONLY`. Un maximum observé sur trois plans
n'est pas un maximum certifié sur tout l'avant-bras. Un budget épuisé produit
`INCOMPLETE` et laisse les sections non exécutées sans périmètre.

## Enveloppe conservatrice de la main

`hand_envelopes` nécessite `hand_source` : références et empreintes de l'adapter
original et de la géométrie source. La topologie et les régions de faces doivent
être conservées. Toutes les régions déclarées `hand.left` ou `hand.right` dans
`region_to_bone` sont incluses, avec la paume et les doigts. Le centre de main
capturé doit correspondre au centroïde des régions `centers` de cet adapter.

La projection dans le plan normal à poignet → centre de main produit une
enveloppe convexe contenant tous ces sommets de peau. Sa portée est
`CONSERVATIVE_PROJECTED_WHOLE_HAND_SKIN_HULL`. Le champ `hull_perimeter_cm` reste
distinct de `girth_cm`, qui n'existe pas dans ce résultat. Cette projection
concerne la pose capturée ; elle ne démontre pas le passage physique d'une main
articulée dans une manchette. Une enveloppe qui dépasse la capacité nominale
constitue un signal conservateur, pas une impossibilité physique implicite.

## Lecture du supplément sauvegardé

`body_region_descriptor(project, specification_path, supplement_ref)` vérifie
le fichier exact puis remesure toutes les entrées canoniques. Il compare le
résultat complet, y compris les empreintes du code. Un supplément dont les
valeurs ont été modifiées puis resignées est refusé.

- `body_region_section(project, specification_path, supplement_ref, section_id)`
  retourne uniquement une section de peau `MEASURED`, son plan, son contour,
  son périmètre et ses identités source/pose/profil.
- `conservative_hand_envelope(project, specification_path, supplement_ref,
  envelope_id)` retourne une enveloppe de main complète avec sa portée distincte.
- `verified_region(profile, geometry, triangles, specification, supplement,
  region_id, adapter=None, source_geometry=None)` remesure les entrées portables
  avant de retourner une région au calcul d'enfilage.

La lecture ne crée aucune décision humaine ni qualification d'enfilage ou de
fitting. Les règles numériques d'aisance et leurs chemins matériels homologues
restent des entrées séparées à examiner.

## Vérification

Les tests portables couvrent un cadre tourné et translaté, l'immutabilité,
l'invalidation de la pose/topologie/régions/repères/code, les sections ouvertes,
coplanaires ou multiples, les budgets, la portée de la projection de main et
le refus d'une origine native absente.

Le driver `tests/native_body_region_sections.py` s'exécute avec Python ordinaire
sur une politique existante et des données natives déjà capturées. Il écrit dans
un nouveau répertoire G: extérieur au projet, puis vérifie les sources et SQLite
inchangés. Aucun processus Blender ni nouvelle capture native n'est exécuté.
Le rapport conserve le statut des mesures, y compris les sections refusées.
