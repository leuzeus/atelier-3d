# Recherche de correspondances dans une cage UV

Le calcul des sections de matière utilise les triangles source réels et le
guide déclaré. Le profilage a localisé un coût dominant : chaque sommet
source évalué parcourait toutes les cellules de la cage UV. Le
[diagnostic conservé](automation-material-section-profile-evidence-20261005.json)
concerne des calculs portables incomplets, sans fitting ni exécution Blender.

`a3d.cage_lookup.CageLookup` prépare une recherche générique à partir de la
cage déjà validée. Le nom du vêtement, les identités de pièces et les mesures
du corps ne sélectionnent pas son algorithme. Le consommateur conserve
`_compile_cage` et le calcul barycentrique `_cage_point` existants.

## Exclure uniquement une correspondance impossible

L'index regroupe les plages des coefficients réellement calculés des cellules :
origines UV, différences des coordonnées et dénominateurs. Les dénominateurs
positifs et négatifs sont séparés. Pour un point, les intervalles suivent le
même ordre d'opérations que les expressions `beta`, `gamma` et
`1-beta-gamma`. Chaque opération arrondit ses bornes vers l'extérieur avec
`math.nextafter`.

Un groupe est écarté seulement si une de ces plages ne peut pas satisfaire
le prédicat barycentrique existant. Une borne non finie, un dénominateur
contenant zéro ou un autre cas non prouvé conserve le parcours complet. Les
entrées entières restent également sur ce parcours. Il n'y a ni nouvelle
tolérance de boîte UV, ni approximation des coordonnées.

Tous les candidats conservés sont transmis dans l'ordre de la compilation
originale, même lorsque les identifiants ne sont pas triés. Le calcul exact
examine toutes les superpositions et garde son refus d'ambiguïté. Des bornes
plus étroites que le prédicat d'origine ne permettent aucune exclusion.

## Identité, budget et domaine

L'instance conserve une copie immuable de la cage et de sa compilation.
`matches(frame, compiled)` permet une vérification explicite pour un réemploi.
Le consommateur de mesure crée une instance locale par appel ; aucun cache
global ou résultat d'un autre guide n'est utilisé. Ses contrôles de source
avant/après le calcul restent présents.

La construction, la recherche et le calcul exact gardent le même contrôle de
temps. Les budgets de faces, points et secondes ne sont pas augmentés. Les
guides en sections d'arcs suivent leur parcours existant. Une cage hors du
domaine de l'accélération garde le calcul exhaustif et ses limites.

Cette correction accélère une recherche géométrique ; elle ne complète pas
une homologie manquante, un chemin branché ou une couverture ouverte. Les
contrôles de matière, de contacts, d'aisance et les décisions humaines restent
distincts. Voir [le contrat de généralité](garment-automation-generality.md).

## Vérification

La suite ciblée de 59 tests passe sous Python 3.11 et 3.13. Les comparaisons
avec le parcours exhaustif couvrent des domaines distincts, points de bord et
`nextafter`, rotations, cisaillements, changements d'échelle, orientations
mixtes, superpositions conflictuelles, coordonnées extrêmes et budgets épuisés.
Le consommateur compare le dictionnaire complet de la courbe de matière sur
deux cadres source, sans mutation des entrées.

La revue indépendante a aussi effectué 1 152 comparaisons pures avec un ordre
de compilation inversé et des coordonnées extrêmes, sans candidat admissible
omis ni différence de résultat/refus. Cette exploration est rapportée par le
réviseur sans reçu de fichier séparé ; les logs de la suite ciblée constituent
la preuve enregistrée. Leur portée reste le noyau et son consommateur portable,
sans qualification de la capacité complète du manteau.
