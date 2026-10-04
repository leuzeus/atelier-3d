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

## Comportement du contrôle

[garment_fit.py](../a3d/garment_fit.py) compare les dimensions source aux cibles
explicites. Le parcours de projet recompiles les sources et vérifie les fichiers
ainsi que la provenance native du corps préparé ou introduit.

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

Si le placement comprime une coupe suffisante, le code corrige les guides ou
le placement en conservant les patrons. Si la capacité des patrons ne permet
pas l'aisance voulue, une variante séparée du patron est préparée avec les
mesures et les raccords affectés, puis présentée pour décision. Le corps cible
approuvé ne rétrécit pas pour masquer le défaut.
