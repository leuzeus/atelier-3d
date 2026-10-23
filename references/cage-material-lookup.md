# Recherche de correspondances dans une cage UV

Le calcul des sections de matière utilise les triangles source réels et le
guide déclaré. Le profilage a localisé un coût dominant : chaque sommet
source évalué parcourait toutes les cellules de la cage UV. Le
[diagnostic conservé](automation-material-section-profile-evidence-20261005.json)
concerne des calculs portables incomplets, sans fitting ni exécution Blender.

**Statut : backend expérimental, inactif par défaut.** Le rejeu sur les entrées
réelles n'a pas démontré de gain ; il a réduit la progression avant le budget
de 15 secondes. Le consommateur public conserve donc le scan exhaustif.

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
requêtes à coordonnées entières restent également sur ce parcours. Un
coefficient entier est utilisable uniquement si sa conversion flottante est
exacte et finie (`float(v) == v`). Les différences sont calculées dans leurs
types d'origine avant cette conversion ; les valeurs originales restent dans
le calcul final. Il n'y a ni nouvelle tolérance de boîte UV, ni approximation
des coordonnées.

Tous les candidats conservés sont transmis dans l'ordre de la compilation
originale, même lorsque les identifiants ne sont pas triés. Le calcul exact
examine toutes les superpositions et garde son refus d'ambiguïté. Des bornes
plus étroites que le prédicat d'origine ne permettent aucune exclusion.

## Identité, budget et domaine

L'instance conserve une copie immuable de la cage et de sa compilation.
`matches(frame, compiled)` permet une vérification explicite pour un réemploi.
Le consommateur de mesure crée une instance locale par appel expérimental ; aucun cache
global ou résultat d'un autre guide n'est utilisé. Ses contrôles de source
avant/après le calcul restent présents.

La construction, la recherche et le calcul exact gardent le même contrôle de
temps. Les budgets de faces, points et secondes ne sont pas augmentés. Les
guides en sections d'arcs suivent leur parcours existant. Une cage hors du
domaine de l'accélération garde le calcul exhaustif et ses limites.

Le noyau accepte `use_cage_lookup=True` pour un essai explicite. La valeur par
défaut reste `False` ; le parcours public des mesures ne l'active pas. Le
résultat précise le backend effectivement utilisé. Un argument non booléen est
refusé. Ce paramètre ne donne aucune admission physique ou de fitting.

Cette correction accélère une recherche géométrique ; elle ne complète pas
une homologie manquante, un chemin branché ou une couverture ouverte. Les
contrôles de matière, de contacts, d'aisance et les décisions humaines restent
distincts. Voir [le contrat de généralité](garment-automation-generality.md).

## Vérification

La première suite ciblée de 59 tests passe sous Python 3.11 et 3.13 sur le
commit `af78094`. Le rejeu courant de 79 tests couvre aussi les coefficients
entiers exacts, le défaut de production exhaustif et la capacité transverse
générique ; il passe sous les deux Python. Les comparaisons
avec le parcours exhaustif couvrent des domaines distincts, points de bord et
`nextafter`, rotations, cisaillements, changements d'échelle, orientations
mixtes, superpositions conflictuelles, coordonnées extrêmes et budgets épuisés.
Le consommateur compare toutes les données de la courbe de matière sur deux
cadres source, hors le seul champ identifiant le backend différent, sans
mutation des entrées.

La revue indépendante a aussi effectué 1 152 comparaisons pures avec un ordre
de compilation inversé et des coordonnées extrêmes, sans candidat admissible
omis ni différence de résultat/refus. Cette exploration est rapportée par le
réviseur sans reçu de fichier séparé ; les logs de la suite ciblée constituent
la preuve enregistrée. Leur portée reste le noyau et son consommateur portable,
sans qualification de la capacité complète du manteau.

Sur le premier panneau source réel, l'index conserve environ 9 269 cellules
sur 11 922 pour une requête typique. La poitrine atteint seulement 568 faces
sur 5 242 avant l'arrêt ; taille et hanches restent également incomplètes.
Les preuves négatives sont conservées séparément et aucun gain n'est annoncé.
Le choix de structure de recherche reste à reprendre avant activation en
production ; augmenter implicitement le budget n'a pas servi à ce diagnostic.
