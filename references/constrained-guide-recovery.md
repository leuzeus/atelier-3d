# Récupération métrique avec contraintes locales de peau

`recover_guide_metric` réutilise son solveur matière et son quotient des
coutures permanentes. L'option `surface_constraints` ajoute des échantillons
locaux de peau au même système. Sans cette option, le comportement et le
rapport historiques restent conservés. Les UV, faces, découpages, pins et
arrêts physiques ne sont pas modifiés.

Une contrainte relie un indice matériel actif à un point barycentrique d'un
triangle corporel fourni, sa normale orientée et une réserve minimale. Le
document lie le payload, les coordonnées d'entrée, la géométrie, la pose,
les triangles et les sections par leurs empreintes. Il doit couvrir tous les
sommets des pièces sélectionnées. Chaque point soutenu reste dans sa boule
de confiance et sa projection reste dans le triangle déclaré.

Les contributions des partenaires cousus s'additionnent sur leur représentant
commun ; ils ne sont pas corrigés indépendamment. La recherche de pas et le
verdict final vérifient ensemble la métrique et les contraintes locales. Un
score amélioré, une métrique seule admise ou un budget épuisé ne suffisent pas.
Des appuis fixes incompatibles donnent un résultat non admis avant optimisation.

Le document accepte une géométrie corporelle minimale à quatre champs :
`vertices_cm`, `faces`, `source_sha256`, `pose_sha256`. Les plafonds contrôlés
avant les empreintes complètes comprennent 4 096 échantillons/sommets actifs,
100 000 sommets corporels, 200 000 faces/triangles, 600 000 incidences de faces
et 600 000 références de triangles cumulées dans les sections. Les identifiants
sont limités à 128 caractères. Ces limites sont un domaine de calcul portable,
pas une preuve de couverture du manteau entier.

Après une expiration tardive, le meilleur candidat est conservé avec son
observation complète déjà calculée, liée à l'empreinte de ses coordonnées.
Le statut reste `NEEDS_CORRECTION / TIME_BUDGET`. Aucune observation coûteuse
n'est relancée après le délai pour obtenir un succès. La vérification finale
d'intégrité appartient elle aussi au temps de cette option.

Ces contraintes sont des **plans de triangles locaux échantillonnés**. Elles
ne démontrent pas la réserve continue autour du corps. Le noyau vérifie la
cohérence des données fournies ; l'authentification native et la validité des
sections appartiennent à l'appelant. Ses sorties conservent `qualification:
NONE`, `contacts: NOT_ASSESSED`, simulation et fitting non exécutés.

L'adaptateur de production qui prépare ces contraintes depuis les mesures
exactes du candidat reste à intégrer. Aucun nouveau résultat natif du manteau
n'est produit par cette unité. Les modules `material_surface_*` restent les
contrats de transport/interpolation des champs et références matérielles ;
ils ne sont pas remplacés par cet objectif d'optimisation local.

Les 58 tests ciblés passent, dont dix-huit nouveaux. La revue indépendante
a corrigé les expirations tardives, le bornage avant empreinte et l'horloge
après la dernière vérification d'intégrité. Elle est close sans autre P1/P2.
Les cas portent sur des fixtures portables ; ils ne qualifient pas les pièces
du manteau ni deux mannequins natifs de même tour.

[Tests, contrat et portée](automation-constrained-guide-recovery-evidence-20261007.json).
