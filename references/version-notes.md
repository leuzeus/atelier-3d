# Notes de versions et portée des essais

Ces notes proviennent du README avant sa réorganisation du 3 octobre 2026. Elles décrivent les essais et limites aux versions citées, pas une nouvelle qualification du candidat actuel. Les paragraphes initiaux sur le fitting et la reprise interactive précèdent les notes datées de versions.

Consulter [l’historique](../CHANGELOG.md) pour les changements et [la validation](../VALIDATION.md) pour les preuves et leurs limites. Les mentions historiques « non publié » de ces documents restent liées à leurs essais ; les manifestes du checkout indiquent 0.7.0-rc.2.

La [préparation native du fitting](fitting-preparation.md) peut produire
une enveloppe auxiliaire depuis la référence évaluée du corps et un champ de
pose continu depuis les bords nommés des patrons et les os mesurés. Elle conserve
FlatRest, les pins fixes et les seuils physiques. Les recettes peuvent décrire
quelques profils de rigidité partagés et des renforts locaux : poids et maxima
Blender exécutés sont enregistrés et vérifiés. Ces préparations ne constituent
ni acceptation anatomique, ni simulation portée réussie, ni preuve visuelle.
Le diagnostic d'enfilage précise désormais les manques même sans collider.

La reprise vide utilise l'opérateur autorisé par le MCP officiel, sans
réinitialiser les préférences ni perdre ses add-ons ou sa connexion. Le test
interactif isolé vérifie son garde réel, les requêtes suivantes et la récupération.
Le test autonome de 0.6.3 ne couvrait pas ce garde. Une [sélection explicite du
corps source](body-source.md) produit sa pose évaluée figée sans
importer l'ancien vêtement. Elle ne crée pas de collider et ne valide pas les
repères anatomiques ou le fitting.

La version 0.6.3 permet l'inspection de capacité malgré des contacts refusés,
une [reprise native dans une scène vide et un fitting séparé](clean-construction-fitting.md),
avec conservation du témoin et des approbations exactes. Un placement rigide
optionnel exige un corps cible identifié et des repères homologues explicites.
Les pénétrations profondes sont refusées avant une projection destructrice.
La reprise propre du cas réel reproduit exactement les coordonnées du montage
réussi : aucune contamination cumulative n'est établie. Le proxy anatomique
reste NOT_QUALIFIED et le fitting réel n'est pas exécuté.

La version 0.6.2 rend l'inspection d'un candidat géométriquement refusé lisible,
avec les mêmes contrôles d'identité, rest, topologie et pins. Elle ajoute la
[préparation locale et le montage d'un groupe sélectionné](local-interfaces.md)
depuis les coordonnées cousues actuelles. Sur la fixture réelle de 17 panneaux,
le local puis le full sans collider passent à 18 images : écart maximal
0,1752 cm, étirement 0,8184–1,2379 et déplacement maximal 8,4330 cm.
Les seuils physiques restent inchangés. Le fitting réel, la stabilité longue,
la validation humaine et l'import Unreal restent à qualifier.

La version 0.6.1 ajoute le [montage par étapes](sewn-stages.md) :
`apply_sewn_result` reprend un résultat local PASS sans collider dans une copie
native, avec ses indices et reçus ; `simulate_sewn(purpose=assembly)` permet
l'assemblage complet libre ; `prepare_sewn_stage` conserve les coordonnées
cousues pour préparer les interfaces restantes puis introduire le mannequin
identifié pour un fitting distinct. Le parcours complet passe sur fixture.
Le transfert réel de 5 455 sommets passe aussi ; à cette version, l'assemblage réel
de 17 panneaux était refusé avant Cloth pour orientation d'emmanchure. Les essais
bornés de prépositionnement n'avaient pas produit de candidat admissible. Cette version
livre la continuité native sans qualifier le vêtement réel ou son fitting.

La version 0.6.0 permet de tester un [prépositionnement borné des panneaux](experimental-prefit.md)
dans l'opération `garment`, sur demande explicite et sans modifier les patrons.
Elle ajoute un raffinement optionnel de la triangulation et conserve les contrôles
finaux mesurés même après refus de qualité. Le cas réel échoue encore pendant Cloth :
le prépositionnement expérimental ne qualifie pas le vêtement et reste désactivé par défaut.

La version 0.5.9 précise le [diagnostic des déplacements Cloth](cloth-motion.md) :
excursion depuis le début de phase et incrément entre images évaluées, avec
sommet source, pièce, UV, bords nommés et poids de maintien. L'image qui dépasse
le budget est conservée dans l'historique. Les anciens diagnostics restent
lisibles sans inventer leurs incréments. Aucun seuil ni profil physique n'est
modifié ; ces mesures ne prouvent pas seules une instabilité ou un fitting accepté.

La version 0.5.8 ajoute une [fiche de fitting mesurée](measured-fitting.md) :
sections homologues corps/enveloppe, capacité sur un chemin fermé des lignes de
couture, aisance et incertitude. Les données manquantes restent NOT_QUALIFIED.
Une proposition alloue un déficit mesuré en cm sans modifier les patrons.
Des attaches natives provisoires peuvent maintenir une fermeture existante
pendant l'essai local ; elles ne deviennent pas des coutures permanentes et ne
qualifient pas full/freeze. Le dessin/appliqué des retouches, le montage progressif
et le fitting du vêtement réel restent à qualifier.

La version 0.5.7 conserve les diagnostics des probes physiques avant nettoyage :
profil exécuté, durée, coupons, supports, qualité et écarts. `inspect_sewing_failure`
distingue `backend_probe_simulation=FAIL` et `garment_simulation=NOT_EXECUTED`.
Un nouvel échec local invalide la qualification courante pour le lancement full,
en conservant les preuves historiques. Voir [le diagnostic des probes](probe-diagnostics.md).

La version 0.5.6 conserve un diagnostic lorsqu'un candidat `garment` est rejeté
avant Cloth : coutures et segments d'orientation, coordonnées source/3D,
cosinus et seuil, ou contacts initiaux par pièce, sommet et collider.
`inspect_garment_failure` le lit même pendant la récupération et après restauration.
Le candidat reste rejeté ; aucun reçu de construction ni PASS Cloth n'est accordé.
Voir [le diagnostic de rejet](garment-rejections.md).

La version 0.5.5 ajoute `inspect_sewing_placement` avant Cloth : écarts et
positions des coutures, bords source, poids de maintien, intersections des
segments de rapprochement et orientations vis-à-vis des colliders déclarés.
Chaque tentative native conserve aussi son rapport initial. Ces mesures guident
la préparation du montage ; elles ne valident ni le drapé ni le fitting.
Voir [la revue de prépositionnement](sewing-placement.md).

La version 0.5.4 ajoute un cadrage contrôlé du candidat avec `frame_view`, sans
édition de géométrie, de visibilité ou de caméra. Après un échec Cloth évalué,
elle conserve un diagnostic non accepté avec positions, mappings, déformations,
écarts par couture, pénétrations et projections SVG. Ces preuves restent lisibles
après nettoyage de l'essai et restauration du checkpoint. Voir le
[parcours de cadrage et diagnostic](viewport-diagnostics.md).

La version 0.5.3 conserve des reçus distincts et immuables pour chaque composant
et package. Elle permet de récupérer une preuve d'import historique depuis un
checkpoint lorsque le reçu unique d'un projet 0.4.0 a été écrasé par un autre
composant. La vérification précède la migration et conserve l'ancien mesh comme
diagnostic non validé. Voir [le protocole de reprise](blender-continuity.md).

[Retour à la documentation](index.md).
