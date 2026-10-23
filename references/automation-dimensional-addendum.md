# Complément approuvé : patronage dimensionnel et transformations

Demande utilisateur du 7 octobre 2026, intégrée au programme en cours. Les
constats portent sur l’essai 0704 identifié ci-dessous ; les corrections
postérieures restent distinguées et ne sont pas rejouées.

Intègre ce complément au travail en cours sans interrompre une opération active, abandonner les corrections engagées ni redémarrer le projet. Termine l’étape active jusqu’à un point cohérent, puis prends en compte ce diagnostic dans la suite du plan. Ne relance pas un essai déjà exécuté sans avoir identifié ce que le nouvel essai doit vérifier.

Je veux que le patronage adapte les patrons à la morphologie du mannequin par des calculs génériques : agrandissements ou réductions locaux, longueurs, carrure, épaules, emmanchures et aisance. Le mannequin accepté reste la référence.

Un diagnostic en lecture seule a été effectué dans une conversation latérale sur l’essai dev.2026100704 :
- Run : run.dcc0c3d66da54b47b5401ed92e9d9968
- Tentative : attempt.909d6d9bd3864a7e8ebce726b451b553
- Racine : G:/projets/atelier-3d/work/garment-automation-v1/program-reviewed-design-main-v1/execution-project
- Candidat : .a3d/blender/pattern-preparation/attempt-8409424b26cc4d28a7e160974f3ea138

Ces observations portent sur cet essai. Réconcilie-les avec tes éventuelles corrections plus récentes, sans refaire ce qui est déjà résolu.

Constats vérifiés :
1. Les vues neutral-front.png et neutral-side.png montrent les épaules, le haut du torse et des portions des bras traversant le vêtement.
2. Le maillage source est construit et son angle minimal atteint 15,03875°. Après placement, l’angle minimal tombe à 0,285883° et les étirements principaux locaux vont de 0,006285 à 5,972842. Le placement introduit donc de fortes déformations.
3. La correction s’arrête sur ANCHOR_RESERVE_TIME_BUDGET après 60,698 secondes. Le noyau conserve un essai de translation à +2,75 cm, avec une réserve minimale de 0,24835 cm pour 0,3 cm requis sur ses points protégés. Le wrapper n’applique pas cet essai non admis : metric_recovery=NOT_EXECUTED et contact_search=NOT_STARTED_INADMISSIBLE_ANCHORS.
4. Les guides d’épaule utilisent bien des points de peau, mais construisent des plans et des transitions. Dans le code 0704, torso_sections.py:47–75 translate un guide inférieur au-dessus du début d’emmanchure ; shoulder_guides.py:10–32 et 40–84 construit les plans matériels. Cela ne garantit pas la couverture de toute la surface anatomique.
5. Le couplage des coutures rapproche les bords par moyenne de leurs positions proposées. Le rapport des guides montre encore jusqu’à 6,126 cm d’écart col/devant après placement rigide, ensuite ramené à zéro par couplage. Il faut mesurer la déformation introduite par cette étape.
6. Le col a réellement été agrandi de 48,83 à 55,22 cm, avec sa hauteur de 7 cm conservée. Mais garment_guides.py:433–459 utilise une section horizontale du cou et une ellipse auxiliaire à deux niveaux : le périmètre corrigé ne garantit pas l’adaptation au relief sur toute la hauteur.
7. Le rapport patronage-runtime-review-v11 laisse des correspondances de mesures manquantes. Il est antérieur à la variante de col : ne pas le présenter comme une évaluation actuelle du package.

À intégrer dans la suite du développement :

A. Produire un tableau dimensionnel du candidat exact :
mesure corporelle → aisance approuvée → trajet correspondant sur les lignes de couture du patron → capacité disponible → écart → statut de correspondance.

Inclure carrures devant/dos, longueur et pente d’épaule, longueurs du buste, profondeur et parcours d’emmanchure, tête de manche, tour de bras, longueur de manche, base du cou et forme sur la hauteur du col. Pour le devant ouvert, mesurer la couverture et l’ouverture voulues sans inventer un tour fermé ni additionner les couches.

B. Distinguer deux corrections :
- Déficit de matière démontré : proposer une variante 2D locale calculée.
- Capacité suffisante mais mauvais placement : corriger les guides en conservant la métrique du tissu.

Ne pas déduire un manque de tissu de la seule présence de pénétrations. Ne pas appliquer un agrandissement global sans justification dimensionnelle.

C. Réutiliser les noyaux de patronage et de récupération métrique existants. Préserver les raccords, les crans, le droit-fil, les ouvertures et le découpage ; déclarer explicitement les différences de longueur prévues pour l’embu. Les changements de coupe restent des variantes à présenter.

D. Mesurer les déformations et les contacts après chaque transformation :
guide initial → placement rigide → couplage des coutures → récupération métrique.
Cela doit identifier précisément l’étape qui dégrade le résultat. Corriger séparément le coût du calcul de réserve pour permettre aux étapes suivantes de s’exécuter, sans relâcher les critères.

E. Vérifier notamment les cas : patron réellement trop petit, patron suffisant avec mauvais guide, épaule inclinée, col de même périmètre mais de forme différente, devant ouvert.

Conserve les décisions déjà approuvées : mannequin masculin à 180 cm, manteau ample, variantes acceptées des manches et du col, devant intérieur entièrement visible. Maintiens les autorisations Blender et les revues humaines prévues.

Le prochain résultat attendu est une explication mesurée des zones à agrandir, réduire ou seulement repositionner, puis une correction générique vérifiable. Continue les travaux autorisés et indépendants pendant cette intégration ; ce message complète le plan en cours.
