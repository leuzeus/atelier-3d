# Placement anatomique générique — correctif V2

Ce correctif remplace des approximations de placement par des entrées anatomiques
explicites et un calcul qui conserve les dimensions de repos des patrons. Il ne
redimensionne ni le corps accepté ni les patrons. Il prépare des candidats ; la
simulation, les contacts natifs et la revue du vêtement restent nécessaires.

## Défauts traités

| Défaut | Calcul ajouté | Limite vérifiée |
| --- | --- | --- |
| Col construit sur une section horizontale | `PATH_BAND_V1` suit le trajet corporel 3D mesuré et sa variation de hauteur ; l’axe matière et le sens longitudinal sont déclarés | Une bande trop courte est refusée ; la représentation par cage doit encore passer le contrôle métrique complet |
| Attache de manche placée sur l’articulation interne | `LIMB_ATTACHMENT_V1` utilise un trajet de peau pour l’attache et des repères distincts pour l’axe du membre | Le côté anatomique doit correspondre ; les constructions sans couture unaire compatible restent non supportées par cette primitive |
| Dos ou épaules à l’intérieur du corps | `REGIONAL_SURFACE_ENVELOPE_V1` interroge les triangles natifs des régions source déclarées et déplace les contrôles vers la surface avec réserve | Une direction ambiguë, une projection absente ou un budget insuffisant produit un résultat partiel ; tous les triangles textiles restent à contrôler nativement |
| Moyenne des seules frontières allongeant le col | `COUPLED_REST_METRIC_V2` corrige d’abord par translations, puis optimise ensemble les coutures et la métrique des triangles UV source | Conservation du meilleur candidat, extrema de déformation par pièce, limites de déplacement et stagnation ; aucun `READY` de placement émis par ce noyau |
| Manches omises du groupe corrigé | `piece_scope: PERMANENT_COMPONENT` suit les relations permanentes, y compris vers les manches et manchettes | Aucun lien détachable ou de fermeture n’est transformé en couture permanente |
| Attache anatomique déplacée après sa construction | Contraintes de points source UV, distinctes des ancrages numériques, pendant le couplage ; contrôle des réserves après celui-ci | Les contrôles de support peuvent être surcontraints ; une incompatibilité reste incomplète |
| Tête ouverte de membre refermée comme une section tubulaire | `SOURCE_SEWN_DOMAIN_V1` dérive le domaine tubulaire de la couture longitudinale et prolonge sa section terminale sur la partie ouverte | Une seule couture unaire compatible ; le tube et les contacts peuvent rester refusés |
| Embu perdu lors de la préparation | Recette source exacte transportée dans le rapport V2 et vérifiée avant génération des entrées natives | Aucun remplacement implicite par zéro ni modification de tolérance |

## Couverture du corps

Le catalogue de régions comprend la tête, le cou, le torse, le bassin, les bras,
avant-bras, mains, cuisses, jambes, pieds, doigts et orteils des deux côtés. Une
région supplémentaire utilise un nom explicite `custom:...` et des références
mesurées. Ce catalogue est un inventaire de données, pas une qualification de
fitting pour chacune de ces régions.

Le rôle public `panel` permet de préparer une pièce sans la déclarer faussement
comme manche, col ou panneau de torse. Sa politique choisit une primitive :

- bande suivant une courbe mesurée : cou, ceinture, tour de membre ou autre région ;
- enveloppe tubulaire avec attache et axe explicites : membre ou doigt, dans le
  domaine de couture et d’axe matière V accepté par `LIMB_ATTACHMENT_V1` ;
- correction de surface régionale : applicable à toute cage déjà construite,
  avec régions source et direction extérieure explicitement choisies.

Une main complète, un pied complet ou une construction complexe ne sont pas
automatiquement décrits par un tube. Chaque panneau doit avoir un guide adapté.
`anatomical_region_coverage` énumère les références disponibles, celles qui
manquent et les primitives non supportées. Une région déclarée ne suffit pas à
produire un placement accepté. Une région sans correspondance ne reçoit aucune
coordonnée inventée.

## Entrées publiques et reproductibilité

`studio_compile_production_dossier` conserve son interface. Les paramètres de
préparation d’un composant peuvent ajouter :

```json
{
  "anatomical_references_ref": {
    "path": "preparation/anatomical-references.json",
    "sha256": "<SHA-256 des octets du fichier>"
  }
}
```

Le document référencé contient `version: 1`, `profile_sha256` (digest canonique
du profil), `paths`, `pieces` et, pour les surfaces, `triangles_ref`. Chaque entrée
de `paths` référence un rapport sauvegardé avec `report_ref: {path, sha256}`,
`path_id` et `region`. Le chargeur vérifie les fichiers, les budgets, les chemins
internes au projet et les coordonnées contre la géométrie du corps.

Après cette vérification géométrique, chaque trajet normalisé conserve
`source_face_incidence` : faces incidentes aux arêtes ordonnées, régions
correspondantes et identités du corps, de la pose et des étiquettes. Les listes
sont copiées ; sans géométrie vérifiée, ce reçu est absent. Cette provenance
permet de préparer une graine de correspondance. Elle ne sélectionne aucune
nappe, ne définit pas de domaine de continuation et ne valide pas une nouvelle
attache. La provenance native et la revue humaine restent authentifiées par
l'appelant. Les coordonnées historiques du trajet ne changent pas.

Les politiques de pièces sont explicites :

| Primitive | Paramètres obligatoires |
| --- | --- |
| `PATH_BAND_V1` | `path_ref`, `material_axis`, `source_anchor_edge`, `source_anchor_fraction`, `path_anchor_fraction`, `longitudinal_direction_body`, `max_path_expansion_ratio` |
| `LIMB_ATTACHMENT_V1` | `attachment_path_ref`, `path_fraction`, `source_anchor_edge`, `source_anchor_fraction`, `axis_landmarks`, `transverse_direction_body`, `attachment_offset_body` |
| `LIMB_SEGMENT_AXIS_V1` | `anatomical_region`, `axis_landmarks`, `transverse_direction_body`, `source_end_edges`, `source_anchor_end` |
| `surface_envelope` | `method: REGIONAL_SURFACE_ENVELOPE_V1`, `source_region_ids`, `direction_body`, `reserve_cm`, `max_displacement_cm` |

Pour `PATH_BAND_V1`, `path_direction` fixe explicitement le sens de parcours :
entier `1` ou `-1`. Son absence conserve le sens historique `1`. La phase
`path_anchor_fraction` et le sens répondent à deux besoins distincts : placer
un repère sur la courbe et faire correspondre l'ordre matériel à son orientation.
Une phase ne corrige pas un parcours inversé. Les repères et le sens doivent
venir des bords, coutures et trajets mesurés du projet ; leur choix reste une
proposition de montage tant que le candidat n'a pas été examiné.

Le champ transversal d'une bande est également explicite :

- `transverse_field: SEGMENT_ORTHOGONAL_V1` conserve le calcul historique : la
  direction déclarée est projetée perpendiculairement à chaque segment du trajet.
  Aux coins d'une polyligne, elle peut changer brusquement. Ce mode ne garantit
  donc pas la continuité d'une bande de hauteur non nulle.
- `transverse_field: BODY_DIRECTION_CONSTANT_V1` conserve la même direction
  corporelle unitaire sur tout le trajet. La base mesurée et les longueurs des
  fibres sont conservées, y compris dans un référentiel tourné. Le champ est
  continu aux coins ; il peut toutefois introduire du cisaillement et ne dispense
  pas du contrôle métrique de chaque triangle. Une direction parallèle à un
  segment échantillonné est refusée.

L'absence du paramètre conserve le comportement et le rapport historiques.
Une bande continue ne suffit pas si ses triangles traversent plusieurs ruptures
du paramétrage : leur interpolation affine peut encore déformer la matière.
La longueur de quelques fibres témoins ne remplace pas cette mesure complète.

`cage_sampling: PATH_KNOT_PARTITION_V1` découpe les triangles matériels aux
changements de segment du trajet, sur l'axe matière déclaré. Ce mode exige le
champ `BODY_DIRECTION_CONSTANT_V1`. Il change le maillage de contrôle dérivé,
sans déplacer le contour source ni changer les coutures du patron. Les points
partagés sont calculés rationnellement et arrondis une seule fois ; le validateur
existant vérifie les frontières, les propriétaires et la couverture des faces.
Le budget limite le temps, les contrôles et les triangles ; les cellules
dégénérées restent refusées. Les extrema d'étirement restent à mesurer.

`cage_sampling: SOURCE_TRIANGLE_GRID_V1`, ou l'absence du paramètre, conserve le
raffinement historique des triangles source. La nouvelle partition n'est pas
une modification de patron, une réparation de collision ou une admission de
placement. Les résultats des deux modes doivent conserver leur identité propre.

Le paramètre de composant `section_parameterization` distingue deux calculs
des guides de torse :

- `POLYLINE_ARCLENGTH_V1`, ou son absence, conserve le parcours historique et
  ses rapports. La distance le long de chaque polyligne reconstruite sert de
  coordonnée transversale.
- `SOURCE_MATERIAL_U_V1` transporte les coordonnées U auxquelles le producteur
  a réellement échantillonné chaque section. Il exige des panneaux devant/dos
  appariés, les sections de surface et un `upper_blend` strictement positif.
  Les autres découpages restent explicitement non supportés par ce producteur.

Cette seconde option empêche de remplacer les paramètres matériels par des
longueurs recalculées après la mise en forme des épaules. Elle peut modifier
la forme du guide et relève d'une politique V2 distincte. Elle ne change ni
le patron ni le corps et ne constitue pas une gradation ou un fitting.

Le noyau `material_section_sampling` consomme des sections V croissantes,
avec des coordonnées U strictement monotones et des cibles 3D explicites. Il
est indépendant du rôle anatomique ; son raccord au producteur est actuellement
limité au torse apparié, seul producteur qui transporte ces paramètres. Une
coordonnée manquante n'est pas déduite et une requête hors domaine est refusée.

La partition coupe les faces source originales aux changements U et V, conserve
les propriétaires et les frontières et consomme un budget partagé entre pièces.
Elle ne fusionne pas les points proches et conserve le refus des triangles
numériquement dégénérés. Le résultat utilise le contrat existant de cage UV/XYZ.
La cage affine approxime le champ bilinéaire entre sections : l'erreur rapportée
porte sur les points intérieurs échantillonnés, sans borne continue certifiée.
Les extrema de matière, contacts et raccords restent des contrôles séparés.

Les guides V2 lient le code, le profil, la pose, la géométrie, les rapports, les
sources, les recettes et les paramètres. La vérification reconstruit le rapport
entier sans arrondi ; une durée d’exécution ne fait pas partie de cette identité.
Les paramètres historiques restent disponibles explicitement pour reproduire
leurs observations. Une ancienne politique n’acquiert pas silencieusement les
nouvelles correspondances anatomiques.

La préparation transmet toutes les attaches finales, y compris celles d'une
pièce sans couplage. Au passage au maillage natif, les points source requis
sur les bords sont insérés et propagés aux partenaires cousus. Ils restent
obligatoires pendant la gradation et sont vérifiés après triangulation. Les
attaches UV intérieures ne sont pas supportées par ce transport et sont
refusées explicitement. Un écart d'interpolation d'une courbe ne
peut pas être assimilé à un arrondi. Les contrôles de support sont protégés
pendant la récupération métrique et la correction des contacts ; aucun pin
Cloth n'est créé. Les résidus sont contrôlés à l'entrée et à la sortie même
si la correction optionnelle n'est pas exécutée. La marge de stockage binary32
est calculée séparément et refusée au-delà de 0,01 cm.

Le couplage V2 conserve les coutures unaires. Un tube déjà initialisé peut se
fermer sur lui-même ; une bande plate sans initialisation courbe n’obtient pas
une direction de courbure arbitraire. L’embu non nul exige une distribution
déclarée `UNIFORM_NORMALIZED_SOURCE_ARC`. Les poids du solveur et les budgets
peuvent rendre la proposition incomplète ; les tolérances finales restent fixes.

L'option `source_seam_coupling.relaxation.constraint_projection` accepte
`ACTIVE_PRINCIPAL_CONE_V1`. Son omission conserve le solveur historique et
n'ajoute aucune clé à ses paramètres ou diagnostics. Ce mode adapte la direction
de descente aux bornes principales déjà actives, au lieu de diviser indéfiniment
un pas qui aggrave toujours le même triangle. Il s'applique aux faces matérielles
et à leurs propriétaires, indépendamment du vêtement ou de la région du corps.

Les degrés de liberté fixés sont retirés avant la projection pondérée. Les
256 balayages maximaux et le résidu normalisé de `1e-12` appartiennent au contrat
versionné ; ce ne sont pas des tolérances physiques configurables. Le budget
global reste contrôlé pendant les calculs. Les valeurs non finies, les domaines
invalides et les dérivées singulières non supportées sont refusés explicitement.
Une face entièrement fixée reste mesurée mais n'exige aucune dérivée.

La politique `RETAIN_NONLINEAR_VIOLATIONS_V1` conserve les couples face/borne
réellement refusés pendant les recherches de pas du même solve. Leurs gradients
sont recalculés aux coordonnées courantes, même lorsque la face est sortie de
la bande d'arrondi. Aucun témoin n'est déduit du seul manque de descente. Cette
sélection évite d'oublier une contrainte qui reste limitante ; elle peut être
conservatrice si la face acquiert ensuite de la marge. Les témoins sont
dédoublonnés et comptés séparément des contraintes actives par arrondi.
Cette politique fait partie de l'identité des cages ; elle n'ajoute ni budget
de recherche ni tolérance physique.

Une direction projetée doit encore descendre l'objectif, respecter les limites
de déplacement, puis passer la recherche et les enveloppes non linéaires
existantes. Un échec conserve la meilleure proposition avec sa raison d'arrêt.
Les reçus distinguent projection refusée, absence de descente, dépassement
d'une borne et pas accepté. Un pas accepté ne qualifie ni les contacts, ni
le placement complet, ni Cloth ou le fitting. L'identité des cages lie également
le code du noyau de projection et ses constantes, même si les cibles coïncident.

## Domaine cousu des membres

Le paramètre de composant `limb_parameterization` accepte
`SOURCE_SEWN_DOMAIN_V1`. Son omission ou la valeur explicite
`SOURCE_ROW_CIRCUMFERENCE_V1` conserve le calcul historique.

Le nouveau mode exige les deux bords réels d'une couture permanente unaire,
appariés au même V, monotones, de longueur et de partition compatibles. Le
domaine tubulaire est leur intervalle V commun. À l'intérieur, le calcul
conserve la loi des sections source. À l'extérieur, il prolonge le cylindre de
la section terminale sans refermer la largeur locale de la partie ouverte sur
un tour complet. Les coordonnées U du patron sont conservées, même pour une
extension asymétrique. La continuité en position est assurée au raccord ; la
continuité de dérivée ne l'est pas.

Le mode inclut une partition des faces source aux changements V, avec calcul
rationnel et un seul arrondi des nouvelles coordonnées. Les aires, frontières,
propriétaires et contrôles source sont vérifiés par les validateurs existants.
La résolution `cage_subdivisions` reste 8 dans le dispatcher, et peut être de
2 à 16 dans le noyau. Elle subdivise ici les cellules partitionnées : son coût
diffère du même nombre appliqué aux anciens triangles. Les membres partagent
un budget borné, avec au plus 32 768 triangles par cage.

Les domaines multiples, appariements obliques, largeurs terminales nulles et
extensions sortant de l'intervalle U terminal sont refusés. Une extension
conique, une main complète ou une topologie sans couture longitudinale
compatible ne sont pas inférées. Le calcul dépend des relations source et des
axes déclarés, sans nom de vêtement ou de pièce codé dans le noyau.

Une attache anatomique existante peut nécessiter une nouvelle translation
rigide de la cage. Cette translation est mesurée et enregistrée ; les anciens
contacts ne sont pas réutilisés. La correction de la partie ouverte ne valide
ni la métrique du tube, ni les contacts, ni le vêtement complet.

## Vérifications et portée

Le [noyau de continuation locale](surface-path-continuation.md) prépare un
diagnostic générique depuis les incidences natives d'un bord corporel. Il
conserve les ambiguïtés et les domaines manquants. Il n'est pas encore raccordé
au dispatcher et ne modifie pas le placement des panneaux.

Les tests couvrent les référentiels tournés, les côtés anatomiques, les jambes
avec repères de hanche et cheville, les régions personnalisées, le chargement
public des fichiers, les modifications de source, les coutures unaires,
l’extension des groupes, les contraintes incompatibles et la reproductibilité.
Un témoin de fibre de 7 cm, allongé à plus de 8 cm par la moyenne historique,
reste à 7 cm à 0,001 cm près avec le couplage V2.

Le diagnostic portable générique
`tests/portable_anatomical_band_diagnostic.py` accepte des références de fichiers,
une pièce et sa politique. Son replay du col réel accepté emploie le trajet de
base du cou de 51,2154 cm et le patron de 55,2154 cm. Les quatre fibres comparables
de la cage conservent leur longueur à moins de 0,000001 cm. Il ne qualifie ni
l’orientation du col dans l’assemblage ni les autres pièces du manteau.

La qualification sur la scène complète reste à exécuter : placement des quinze
pièces, boucle, contacts, enfilage, Cloth, fitting, mouvement et revue artistique.
Le build source et le runtime installé sont des identités distinctes. Aucune
exécution Blender ni installation ne résulte de ces tests portables.
