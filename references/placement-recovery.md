# Reprise du placement à partir d'un refus mesuré

La reprise conserve les patrons, le corps accepté, les types de raccord et les
critères finaux. Elle produit un nouveau candidat avec une identité de run
actuelle. Un diagnostic historique n'autorise ni l'exécution Blender ni le
rejeu d'une tentative dont le code a changé.

## Diagnostic et maillage dérivé

`a3d.placement_recovery.diagnose_placement_recovery` consomme les cinq entrées
exactes : maillage, correction, recette, vêtement source et préparation, avec
leurs empreintes et des budgets explicites. Il recalcule la qualité REST,
localise les stops et les relations permanentes, puis propose les prochaines
actions. Le résultat reste `DIAGNOSTIC_ONLY`, `admitted: false` et
`qualification: NONE`. Il ne reconstitue pas l'identité du payload antérieur à
la correction à partir du maillage final.

Les déficits du score de recherche peuvent mélanger distance signée à la
surface et témoins exploratoires de plans de triangles. Ils ne constituent
donc pas une mesure indépendante de profondeur de pénétration. L'admission
utilise toujours les contrôles natifs complets de contacts.

`a3d.meshing_profile.prepare_recovery_profile` prépare une nouvelle recette et
une préparation synchronisées. Les budgets de sommets ne peuvent pas augmenter
et le seuil d'angle ne peut pas diminuer. Les contours, coutures et placements
source restent inchangés. Le rapport exige un nouveau raccordement natif du
mapping par IDs source et UV ; la proposition seule n'est pas un maillage
qualifié. Les limites de travail et de temps sont explicites.

## Réserve des stops avant leur protection

L'option `anchor_reserve_correction` du contrat `pattern-preparation` active
`PERMANENT_COMPONENT_BODY_AXIS_TRANSLATION_V1`. Elle déclare la référence
exacte du profil corporel, `BODY_FRAME_UP`, la réserve issue de
`PLAN_COLLISION_CLEARANCE` et les budgets de déplacement, pas, itérations et
temps. Sans cette option, le parcours historique reste inchangé.

Le profil et la géométrie doivent appartenir à un même reçu natif terminé de
`prepare_body_target` ou `introduce_body_target`. Le corps effectivement évalué,
son cache, sa pose et la capture de collision doivent correspondre à cette
géométrie. Les fichiers et surfaces sont contrôlés avant et après les mesures.
Un simple `prepare_body_reference` ne fournit pas cette preuve anatomique.

La V1 recherche une translation positive commune selon l'axe haut mesuré du
corps. Elle déplace l'union des composants textiles complets reliés par des
coutures permanentes qui portent les stops. Elle conserve les partenaires et
la métrique matérielle ; une fermeture détachable n'élargit pas cette union.
La qualité REST inchangée doit passer avant la recherche. Les stops sont
mesurés contre toute la surface réelle, fermée et orientée du corps. Cette
mesure des stops ne remplace pas les contrôles ultérieurs des triangles du
vêtement, des couches et des coutures.

Cette V1 est volontairement bornée : elle refuse les supports physiques
déclarés, les pins de recette, une propriété source fusionnée ou ambiguë, un
corps substitué, un signe ambigu ou une mesure indisponible. Une correction
selon un autre axe ou une relaxation indépendante des stops demande un domaine
déclaré et qualifié supplémentaire. Il n'existe aucun ID de pièce, indice de
sommet ou déplacement propre à un vêtement dans le noyau.

Le résultat `ANCHORS_ADMISSIBLE_ONLY` permet de continuer la récupération
métrique puis la correction de contacts. Il ne produit pas `READY`. Si la
réserve n'est pas obtenue, ces recherches suivantes ne démarrent pas.

## Budget commun et admission

Les deux solveurs acceptent une `protected_stop_reference` explicite pour
figer les stops numériques à leur nouvelle entrée d'étape. Cette option exige
aussi `displacement_reference`, toujours égale au guide original. Les pins
physiques restent à leur position originale. Les références incohérentes,
périmées ou modifiées sont refusées.

Les budgets de déplacement cumulés ne se réinitialisent donc pas entre réserve,
récupération métrique et correction de contacts. Chaque recherche conserve ses
budgets de temps et d'itérations déclarés ; ils ne constituent pas un budget de
temps global de Cloth. Les contraintes de cordes, UV, coutures et métrique
restent actives. Seul le validateur final de préparation, inchangé, peut rendre
le candidat `READY`. Cloth, enfilage, drapé, fitting et revue artistique restent
des étapes distinctes avec leurs preuves actuelles.

## État de qualification

Les tests portables couvrent les noyaux, le raccordement natif simulé, les
refus et la compatibilité sans option. Ils ne qualifient pas la recherche sur
le vêtement réel. Le [programme](automation-program.md) conserve les reçus
des essais natifs et le dernier stade effectivement atteint.
