# Classification du vêtement et aisance

Chaque vêtement a une catégorie, une intention de coupe, une configuration de
port et une position dans les couches. Ces informations accompagnent le corps
cible approuvé et les patrons source. Le mot « manteau » ne définit pas à lui
seul combien de centimètres ajouter au tour de poitrine.

| Information | Exemples | Ce qu'elle précise |
| --- | --- | --- |
| Catégorie | Manteau, veste, robe, chemise, accessoire | Famille du vêtement |
| Intention de coupe | Près du corps, standard, ample, surdimensionnée | Volume voulu ; aucune valeur numérique automatique |
| Configuration de port | Fermé, devant ouvert, enveloppant | Ouvertures, fermeture et recouvrements à examiner |
| Position dans les couches | Intérieure, extérieure, seule, ensemble | Corps ou vêtements sous-jacents à prendre en compte |

L'aisance est une différence de longueur entre une capacité utile du vêtement
et la mesure corporelle correspondante. La fiche précise sa valeur minimale,
sa cible et sa valeur maximale, puis répartit la cible entre le mouvement, les
couches portées dessous et le volume esthétique. Les valeurs viennent d'une
décision ou d'une donnée source identifiée ; elles restent à revoir lorsqu'elles
ne sont pas approuvées. Une matière extensible ne justifie pas automatiquement
une aisance négative.

La marge de couture sert à la confection. La réserve de collision empêche le
tissu simulé de traverser un obstacle. Ces deux marges ne remplacent pas
l'aisance du vêtement.

## Mesures requises avant le fitting

Le contrat [garment-fit.schema.json](../schemas/garment-fit.schema.json) déclare
les mesures nécessaires avec leur composant, leur couche et leur repère
corporel. Une même section de taille peut être utilisée séparément pour le
manteau et la ceinture. Leurs longueurs ne sont pas additionnées.

Pour un tour fermé, le chemin suit une chaîne simple de matière à travers des
raccords réellement présents dans les patrons. Ses extrémités utilisent les
bords nommés et leurs fractions de longueur. Le contrôle refuse les passages
hors d'un patron concave, le comptage double, les correspondances incohérentes
et les mélanges de couches. Les recouvrements ou prises de matière sont
déduits explicitement. Une fermeture déclarée donne une capacité nominale ;
sa fermeture physique doit encore être observée.

Pour un devant ouvert, la longueur de matière ne constitue pas un tour fermé.
La couverture du corps, l'écartement et les recouvrements doivent être mesurés
sur le candidat placé. Le devant intérieur conserve sa couche et sa fonction.
Il ne complète pas artificiellement un tour de manteau.

Les tours de bras ou de poignet ne sont pas déduits des articulations du rig.
Un repère de coude ou de poignet sans contour cutané mesuré reste insuffisant.
Le [supplément de sections corporelles](body-region-sections.md) fournit les
plans obliques, leurs contours de peau et les références exactes, sans modifier
le corps approuvé. La fiche peut référencer ce supplément dans `body_regions`
avec une correspondance explicite entre repère et section. Les projections
conservatrices des mains restent des contrôles de passage distincts.

## Comportement du contrôle

[garment_fit.py](../a3d/garment_fit.py) compare les dimensions source aux cibles
explicites. Le parcours de projet recompile les sources et vérifie les fichiers
ainsi que la provenance native du corps préparé ou introduit.

La revue de la silhouette et celle des valeurs d'aisance sont distinctes.
Accepter « ample » ne signifie pas accepter un nombre de centimètres encore
absent. Le projet conserve les décisions humaines `fit-silhouette.<composant>`
et `fit-intent.<composant>`, liées aux fichiers exacts examinés. La seconde
requiert la fiche numérique, le dossier et le profil corporel exacts. Une
modification de ces fichiers invalide sa réutilisation.

Les profils de mouvement d'un candidat de production référencent un
`fit_context` contenant le dossier compilé et cette fiche. Le contrôle refuse
les données manquantes, une capacité incompatible ou une intention numérique
non revue avant toute mutation. Cette admission permet les essais physiques
exploratoires ; le devant ouvert conserve ses contrôles de couverture spatiale
et aucune acceptation de fitting n'en découle. Les coupons de test gardent leur
portée déclarée.

Le même contrôle précède le montage physique des groupes textiles, les essais
`simulate_sewn`, les étapes physiques de `transition_pattern_assembly` et les
scripts de simulation déclarés. Le programme de groupes porte `purpose` et un
`fit_context` avec le dossier compilé et les fiches couvrant effectivement chaque
composant. Une recette avec colliders porte `physics_purpose` et son contexte
exact. Les expériences utilisent explicitement `TEST_ONLY` ; leurs preuves ne
peuvent pas autoriser le gel ou les mouvements d'un candidat de production.

Avant Cloth, le contrôle lie les patrons de la fiche au package canonique
réellement exécuté et vérifie le contenu source du maillage dérivé. Il compare
le mannequin vivant au profil natif exact : cache, sommets, faces et régions de
peau. Un mannequin déclaré comme support est refusé. Une revue portant sur
d'anciens patrons ne permet pas de poursuivre avec un nouveau package. Les
scripts de simulation revérifient ce contexte après leur exécution. Chaque reçu
conserve l'admission exploratoire et `product_acceptance: NOT_GRANTED`.

| Résultat | Signification |
| --- | --- |
| `FIT_PREFLIGHT_INCOMPLETE` | Intention, cible, chemin de mesure ou couverture spatiale manquant |
| `SOURCE_EASE_MISMATCH` | Capacité nominale hors des limites d'aisance déclarées |
| `SOURCE_EASE_COMPARED` | Comparaisons source disponibles ; revue de l'intention et fitting encore requis |

Le rapport conserve les valeurs manquantes. Aucun de ces résultats n'accorde
une acceptation de fitting. Les contacts, l'enfilage, la simulation, le
mouvement et la revue artistique sont des contrôles supplémentaires.

`studio_compile_production_dossier` expose deux résultats distincts :
`compilation` pour les sources de construction et `fit_preflight` pour cette
comparaison. L'argument facultatif `fit_profile_path` désigne la fiche sourcée.
En son absence, `FIT_METADATA_REQUIRED` signale que l'aisance reste à renseigner.
`READY_TO_PLAN` dans la compilation ne signifie donc pas que le corps et le
vêtement sont compatibles.

Avec `measurement_guides_path`, la même interface prépare les chemins de mesure
depuis les patrons exacts et les guides du corps mesuré. Les sorties conservent
leur statut de proposition, leurs fractions de bord, raccords et sources, ainsi
que les données manquantes. L'argument facultatif `measurement_mesh_refs` associe
chaque composant à la référence exacte de son maillage natif dérivé pour étudier
une section oblique. Le parcours recompile et authentifie les entrées en lecture
seule ; il n'écrit pas de dossier temporaire, ne définit pas l'aisance et
n'accorde aucune revue d'homologie ou acceptation de fitting.

Avec `measurement_guide_policy_path`, les mêmes générateurs reconstruisent
les guides depuis une politique versionnée : paramètres explicites, corps,
géométrie native, rôles, packages et code exacts. Le rapport complet est comparé
avant les mesures. Une politique absente reste `GUIDE_POLICY_MISSING` ; une
coordonnée ou source divergente est refusée. Cette vérification ne qualifie pas
le placement et ne transforme pas un chemin proposé en fitting admis.

Si le placement comprime une coupe suffisante, le code corrige les guides ou
le placement en conservant les patrons. Si la capacité des patrons ne permet
pas l'aisance voulue, une variante séparée du patron est préparée avec les
mesures et les raccords affectés, puis présentée pour décision. Le corps cible
approuvé ne rétrécit pas pour masquer le défaut.

## Bornes nominales des manches et manchettes

`a3d.fit_capacity_bounds` calcule une borne sur toute la famille de chemins
transversaux d'un patron fermé par sa couture permanente d'aisselle. Il utilise
les longueurs d'arc des deux bords source, leurs points de rupture et les segments
de matière intérieurs au patron. Une boîte englobante ou quelques largeurs
échantillonnées ne suffisent pas à ce contrôle.

La comparaison avec une section de peau fournit un signal géométrique. Elle
conserve l'hypothèse de matière plate sans étirement, et indique séparément que
la correspondance complète au bras porté et l'alignement natif de la couture
restent à qualifier. Un signal de capacité insuffisante ne prouve donc pas une
impossibilité physique. Il permet de préparer une proposition chiffrée sans
présenter le placement, l'enfilage ou le fitting comme acceptés.
