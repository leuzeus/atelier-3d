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
