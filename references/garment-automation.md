# Automatisation des vêtements : développement V1

Le plan autorisé le 3 octobre 2026 vise une préparation depuis des patrons
approuvés, les rôles explicites des pièces et un mannequin choisi. Les patrons
et leur métrique restent immuables. Le placement, la couture, le drapé, le fitting
et la revue artistique gardent des preuves distinctes.

Point de départ : Atelier 3D 0.6.9, commit
`a7efe4ee9cc3bfe6b6c91ea4798e7b4854d59900`. Développement isolé sur G:, branche
`codex/garment-automation-v1`. La scène et le checkout de production sont conservés.
Installation autorisée après les gates ; publication supplémentaire non autorisée.

## Contrat du planificateur

`a3d.garment_planner.plan_assembly` consomme
`garment-automation.schema.json`. Chaque pièce a une identité, un composant,
un rôle, un côté, des bords nommés et une couche. Les liaisons ont des identités
distinctes et les types `permanent`, `closure`, `detachable`, `free_contact` ou
`temporary_support`. Toutes les entrées portent une référence et une empreinte.
Le consommateur vérifie les fichiers réels et la revue de construction avant
production ; le planificateur pur vérifie la cohérence structurelle.

Les coutures permanentes déterminent les groupes physiquement couplés, tandis
que le graphe intérieur→extérieur détermine l'ordre spatial. Les panneaux d'une
même couche sont traités ensemble, sans créer plusieurs Cloth interdépendants.
Une couture traversant des couches exige une méthode conjointe explicitement
supportée. L'indicateur de capacité ne constitue aucune preuve de qualification
native : un outil ne doit l'exposer qu'après validation de son exécuteur.

Le résultat contient l'ordre déterministe, les sources, les groupes, toutes les
liaisons, les dépendances, colliders du corps, groupes internes à figer, étapes
et budgets. Les groupes externes voient les groupes internes figés ; aucune
interaction textile bidirectionnelle n'est promise. Le corps est un repère de
préparation avant son introduction physique explicite.

Le plan refuse avant simulation : ordre cyclique ou incomplet, pièce manquante,
double couture permanente du même bord nommé, couche incohérente, groupe couplé
non supporté et cycle créé par la contraction des groupes. Il donne une cause,
les identités touchées et un remède. Les intervalles partiels doivent avoir des
bords source nommés distincts dans cette première version ; aucun chevauchement
n'est inféré par proximité. Un plan produit n'accorde aucun PASS de simulation.

## Ordre de réalisation et preuves

| Lot | Capacité | Gate attendue |
| --- | --- | --- |
| 0 | Plan déterministe, graphes et admissions | Tests des groupes couplés, couches, refus, identités et invalidation |
| 1 | Deux mannequins CC0, import et sélection | Binaires/licence/hash, aperçu, package hors ligne et exclusions |
| 2 | Profil anatomique commun | Sections mesurées, segmentation, repères/confidence, cache invalidable |
| 3 | Placement sémantique | Guides réutilisés, métrique conservée, vues et contacts |
| 4 | Correction locale bornée | Journal, meilleur candidat, stagnation et annulation |
| 5 | Exécution multicouche | Cas exécuté, coutures traversantes conservées, collisions explicites |
| 6 | Simulation reprenable | Convergence mesurée, interruption, checkpoints et réponses compactes |
| 7 | Performance et parcours utilisateur | Temps par phase, interventions et aperçus |
| 8 | Qualification du candidat | Tests portables et essais natifs isolés avec critères préalables |
| 9 | Installation et rechargement | Package/version/runtime réellement chargé et empreintes |
| 10 | Acceptation dans « Ouvrir Atelier 3D » | Nouvelle instance isolée, deux bases/import/sélection, robe 15 pièces, revue humaine |

Les états de développement sont enregistrés dans les preuves sur G:. Les essais
natifs de développement utilisent des fixtures, jamais la scène personnelle.
Le relais vers le chat d'acceptation inclut runtime, lanceur, entrées, critères
et limites ; un message automatique ne donne pas permission de contacter ce chat.

## État du catalogue et du profil

Deux bases réalistes de Dan Ulrich, provenant du bundle officiel Blender Human
Base Meshes 1.4.1 sous CC0, remplacent les candidats Nora/Theo exclus par
l'utilisateur. Le catalogue reste `DEVELOPMENT_CANDIDATE`, sans admission de
fitting. Le package n'admet que leurs deux fichiers `.blend` nommés ; une scène
personnelle, un fichier supplémentaire ou une licence/empreinte modifiée sont
refusés. La sélection copie le mannequin et son adaptateur dans le projet.

Le profil calcule les contours de sections de la surface dans un repère déclaré.
La segmentation du torse est explicite et liée à la topologie source : un contour
fermé seul pourrait intégrer les bras et ne suffit donc pas à déclarer le profil
complet. Les articulations proviennent des anneaux topologiques entre régions
source. Les repères effondrés ou hors du corps sont refusés. La source, la pose,
la géométrie, les repères et les options invalident le cache lorsqu'ils changent.

Un rig préparatoire propre au plugin peut être créé dans une nouvelle copie.
Il comporte 17 os, des influences issues des régions déclarées et un lissage
borné. Il ne fournit aucun contrôle de mensurations indépendant. Les essais
natifs isolés vérifient le repos, la topologie et un mouvement court ; la qualité
des déformations, les collisions textiles et le fitting gardent leurs gates.
Les huit vues neutres sont des preuves de revue visuelle de développement,
sans transfert d'approbation artistique à l'utilisateur.

## Placement et corrections en cours

Le guide sémantique du torse réutilise `a3d.preform_volume.volume_frames`.
Chaque côté d'une couche peut identifier les pièces approuvées d'ouverture,
devant, côté et dos, ou une paire réelle devant/dos. Le second cas conserve
les ouvertures et les coordonnées miroir des patrons, sans créer de panneau
de côté ou de bande d'ouverture fictifs. Les bords nommés du patron déterminent
les sections et leur direction ; un centre dos ou un ourlet décalé est refusé.
Le profil mesuré fournit le
repère ; aucune coordonnée par vêtement n'est introduite. Les autres rôles sont
signalés comme pièces encore à traiter. Les manches et poignets utilisent une
direction anatomique et des guides développables dont la circonférence et la
longueur proviennent du patron, sans mise à l'échelle au corps. Leur axe UV
longitudinal doit être déclaré pour éviter d'inventer un sens de fil.

Ces guides sont des hypothèses de placement. Les contacts, la capacité réelle
et les gates de métrique restent à mesurer ; ils ne prouvent ni l'enfilage ni
le drapé. La capuche, les empiècements et le traitement des couches
internes gardent leurs implémentations et essais complets à réaliser.

La ceinture possède un guide ouvert autour de la taille mesurée. La longueur
matérielle vient du patron et son axe longitudinal `u` doit être déclaré. Un
petit arc auxiliaire vide sépare les extrémités ; il n'ajoute aucune longueur
au patron. La fermeture, la boucle rigide et le fitting restent distincts et
non exécutés. La ceinture demeure une bande source unique.

Le plan conserve les déclarations de chaque pièce dans `piece_semantics`.
L'axe longitudinal, le sous-rôle de bande d'ouverture et les alias de bords
du guide font partie de son identité et invalident le plan quand ils changent.
Un alias de bord absent du patron est refusé avant placement.

Les guides des quatre panneaux de torse et de la ceinture ont été évalués sur
des dérivations maillées natives pour les deux bases réalistes. Les limites
géométriques des recettes sources sont conservées et passent dans ces cas.
Ces reçus portent sur la géométrie des guides ; les autres panneaux, les
contacts, les coutures fermées et la simulation complète n'en héritent pas.

Pour une paire devant/dos, le guide lissé doit couvrir le demi-tour brut
des deux contours et borner sa variation. La majorante conserve cette couverture
sans réduire le patron ni détendre les gates. Le contrôle natif vérifie ensuite
la métrique et les contacts ; un guide produit ne constitue aucune admission.

L'essai ciblé des quatre panneaux n'a plus de chevauchement entre panneaux après
cette correction, et sa métrique passe sur les deux corps. Le contact initial
avec le corps reste refusé près des épaules. Les cinq corrections rigides
coordonnées testées par corps restent inadmissibles ; le raccord maximal initial
reste supérieur au plafond de 12 cm de la recette du cas. Les patrons et seuils
sont conservés. Une préparation adaptée du haut du torse est encore nécessaire.
Les pièces non traitées et les raccords omis du coupon ciblé restent nommés
dans ses reçus ; aucune qualification ne s'étend au vêtement complet.

`a3d.placement_correction.correct_placement` évalue des déplacements/rotations
rigides de panneaux dans des copies temporaires. Les métriques et seuils restent
fixes. Le meilleur candidat mesuré est conservé ; les propositions moins bonnes,
répétées, hors budget ou rejetées par les gates sont annulées. Un budget de temps,
d'itérations, de propositions, de déplacement et de stagnation borne la boucle.
Les callbacks doivent eux-mêmes borner leur coût ; le temps est contrôlé entre
évaluations. Aucun patron, support, raccord ou corps ne peut être édité par une
proposition. Le coupon natif vérifie les métriques et contacts précis existants,
dont le rejet d'une proposition traversant le corps, sans qualifier un vêtement
complet ni une trajectoire d'enfilage.

## Groupe natif de couches cousues

Le plan d'assemblage peut déclarer `layer_execution` avec le mode
`joint_coupled_single_object`, une référence exacte, la carte source et le
graphe des raccords. Ce chemin ne s'applique qu'à un seul groupe couplé par les
coutures permanentes, avec collision propre dans un objet Cloth. Une fermeture
ou une attache amovible ne relie pas artificiellement deux groupes indépendants.
Les colliders des couches internes déjà figées restent des obstacles externes ;
une couche active ne peut pas être simultanément déclarée comme collider figé.
Une déclaration périmée ou plusieurs groupes indépendants sont refusés.

Le coupon natif comporte deux surfaces superposées reliées sur un bord. Douze
frames évaluées avec collision propre active rapprochent ce bord de 0,30 cm à
moins de 0,001 cm, avec les gates de métrique et contact et la source conservée.
Cette preuve porte sur le coupon exécuté. Le séquençage de plusieurs groupes,
le vêtement complet et les interactions textiles externes bidirectionnelles
ne sont pas qualifiés par ce résultat.

## Convergence mesurée

Une phase Cloth peut déclarer `execution_control` : plafond de temps, minimum
d'images calculées, fenêtre de stabilité et vitesse maximale en cm/s. Le moteur
observe les positions réellement évaluées, vérifie la métrique et les contacts
à chaque image et exige aussi l'écart final de couture. Il s'arrête dès que les
critères mesurés sont atteints. L'épuisement du temps ou des images avant cette
stabilité donne `INCOMPLETE`, jamais un succès repris de l'API.

Sans cette déclaration, le mode historique conserve son budget fixe et annonce
explicitement `convergence: NOT_QUALIFIED`. Une fenêtre courte de vitesse n'est
pas une preuve de stabilité pour tous les mouvements futurs ; les seuils sont
liés au cas déclaré. Le coupon vertical de deux couches atteint ses critères
après 38 images sur un plafond de 96. L'essai précédent limité à 12 images reste
conservé comme incomplet. Les limites de couture et de qualité sont inchangées.
La reprise avec checkpoints, les mouvements du corps et le contrôleur complet
des groupes restent à intégrer et à tester.

## Reprise du développement sous Windows

Le banc interactif utilise une instance Blender dédiée, un port local aléatoire
différent de 9876, et son propre profil, cache et dossier temporaire. Le processus
arrêté à la fin doit correspondre au bootstrap du banc ; aucune instance existante
n'est sollicitée. Une copie identique de l'extension MCP sert seulement de
dépendance locale d'essai et ne fait pas partie de la distribution du plugin.

Les essais vérifient la protection native, plusieurs demandes après rechargement,
le retour à l'état initial après erreur et la récupération du checkpoint. Une
option `--catalog-selection` inspecte puis exporte une référence statique de
chacun des deux mannequins, avec les empreintes source, dimensions réelles et
l'invariance de la scène et de la base de données. Cela ne qualifie ni une
enveloppe de collision, ni le drapé d'un vêtement sur le mannequin.

Le bootstrap indique la racine et la version choisies, les fichiers des modules
sélectionnés et leurs empreintes. Une réponse de préparation ou de transition
peut être réduite si elle possède une référence à son reçu complet enregistré.
Les états de simulation, fitting, comportement, couverture et revue demeurent
explicites ; les tableaux par image et par sommet restent dans ce reçu.
L'absence de reçu conserve la réponse complète.

L'épuisement d'un budget reste `INCOMPLETE` dans les diagnostics et projections
de qualification locale, sans autoriser un essai complet à partir d'un ancien
succès. Le diagnostic distingue la dernière image réellement évaluée de l'image
demandée. WSL est indisponible sur la machine d'essai Windows ; les contrôles Linux
restent non exécutés pour ce candidat.
