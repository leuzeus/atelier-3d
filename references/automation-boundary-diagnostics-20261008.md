# Frontières du col et sections des membres — 8 octobre 2026

Cette étape poursuit les causes des pénétrations avec les sources et le corps
acceptés. Elle produit des diagnostics et des captures de candidats refusés.
Elle n'accorde aucune admission du vêtement.

## Col et raccords au torse

Le producteur générique relie six coutures, 198 événements et 192 segments aux
UV source, au guide pilote, au trajet corporel mesuré, à ses arêtes natives et
aux cibles homologues exactes. Aucune pièce ou sélection de contrôle n'est
codée dans l'algorithme. Les références du cas réel restent dans ses données.

Sur les 137 contrôles partenaires existants, 134 correspondances locales sont
calculées : 124 préservent la réserve à la surface ponctuelle sélectionnée et
dix demandent une correction. Les trois autres contrôles appartiennent au
devant intérieur, dont le domaine régional n'est pas déclaré. Sur l'ensemble
des événements, 15 départs exactement au sommet restent refusés. Leurs
incidences natives sont enregistrées, sans choix au plus proche.

Les 27 segments sous 0,3 cm se répartissent en dix à gauche du devant, dix à
droite, quatre sur un raccord du devant intérieur et trois sur l'autre. La
distance minimale reste 0,2307805 cm. Aucun de leurs supports ne dépend des
13 attaches fixes arrière ; ces attaches sont toutes à au moins 0,4241351 cm
du corps. L'absence de contradiction directe avec les attaches ne prouve pas
la faisabilité d'une correction satisfaisant simultanément matière et contacts.

Le [noyau interne de continuation](surface-path-continuation.md), commit
`341c7983bfe966283c39147bd96d1333100bd17a`, reproduit sur l'export immuable les
174 succès et les 15 refus du POC. Les points, barycentriques, faces, triangles
et traversées sont identiques ; les différences scalaires restantes sont des
arrondis inférieurs à 8,89 × 10⁻¹⁶ cm. Ce replay dure 2,531 secondes et utilise
65 695 événements, sous son budget partagé de 120 secondes et 100 000 événements.
Le noyau n'est pas encore raccordé au dispatcher ; aucune cage n'est déplacée.
Le même commit passe 2 222 tests, sans SKIP, en 455,000 secondes, ainsi que
14 contrats JSON. Les empreintes de l'export restent inchangées. La revue
indépendante clôt les trois cas limites reproduits et corrigés : direction
sous-normale, normale retournée liée au cache et dernier succès hors délai.

## Manchettes : ce qu'un meilleur centrage résout et aggrave

À V10 à droite, une translation de section de 0,8763 cm supprime l'intersection
planaire observée avec le bras, à périmètre constant. À gauche, le centrage
seul reste insuffisant ; une forme locale non circulaire à huit côtés entoure
la peau avec le même périmètre de 26,3114 cm. Cette seconde expérience ne
crée pas un tube ni un transport des coordonnées matérielles U.

Les deux marges locales atteignent environ 0,089 cm. Elles ne qualifient pas
la réserve physique : les réglages de collision de 0,3 cm restent inchangés
et leur enveloppe native n'est pas évaluée par ce POC.

Le tube recentré préserve les UV, la triangulation, les coutures longitudinales
unaires, les rangées distales et les manches. Son bord proximal se déplace
d'environ 0,54 cm ; son raccord à la manche n'est pas qualifié.
L'interpolation affine des centres conserve la forme
et le périmètre de chaque section dans les bandes partitionnées, mais ne
préserve pas les longueurs entre les sections. Les étirements deviennent
0,9162–1,2201 à gauche et 0,9179–1,2187 à droite. Le tube reste **REFUSÉ** et
n'est pas adopté comme correction de production. La forme locale à huit côtés
conserve son périmètre total, mais une arête change de 0,805 cm ; elle ne
constitue pas davantage une preuve de conservation matière.

À V20, les périmètres corporels convexes de 29,9845 et 29,9998 cm dépassent les
29 cm source. Cette borne dépend de l'axe, du plan et de la correspondance
longitudinale imposés ; elle ne prouve pas qu'un autre drapé est impossible.
Aucune nouvelle variante de coupe n'est soumise à l'utilisateur.

## Preuves et reprise

Les quatre vues et les gros plans ont été affichés, ainsi que le graphique des
sections et le candidat refusé. Les dossiers locaux sont
`program-neck-boundary-continuation-v1/` et `program-cuff-section-placement-v1/`.
Le [manifeste de preuves](automation-boundary-diagnostics-evidence-20261008.json)
relie les reçus, revues et captures aux fichiers exacts.

Prochaine intégration : produire les correspondances depuis les références
publiques, traiter les sommets et les domaines manquants, construire la
correspondance intérieure du torse et résoudre ensemble forme, matière,
attaches et contacts. L'application indépendante des centres est exclue par
le refus mesuré. Aucun avis humain supplémentaire n'est nécessaire pour ces
investigations techniques ; les changements de conception et l'acceptation
artistique du candidat complet restent des décisions humaines.

Le projet reste RECONSTRUCTING, sans opération Blender en attente. Le runtime
connecté demeure dev.2026100801. Placement complet, enfilage, Cloth, fitting,
mouvements, revue artistique et livraison restent ouverts.
