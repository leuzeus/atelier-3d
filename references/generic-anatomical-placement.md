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

Les politiques de pièces sont explicites :

| Primitive | Paramètres obligatoires |
| --- | --- |
| `PATH_BAND_V1` | `path_ref`, `material_axis`, `source_anchor_edge`, `source_anchor_fraction`, `path_anchor_fraction`, `longitudinal_direction_body`, `max_path_expansion_ratio` |
| `LIMB_ATTACHMENT_V1` | `attachment_path_ref`, `path_fraction`, `source_anchor_edge`, `source_anchor_fraction`, `axis_landmarks`, `transverse_direction_body`, `attachment_offset_body` |
| `surface_envelope` | `method: REGIONAL_SURFACE_ENVELOPE_V1`, `source_region_ids`, `direction_body`, `reserve_cm`, `max_displacement_cm` |

Pour `PATH_BAND_V1`, `path_direction` fixe explicitement le sens de parcours :
entier `1` ou `-1`. Son absence conserve le sens historique `1`. La phase
`path_anchor_fraction` et le sens répondent à deux besoins distincts : placer
un repère sur la courbe et faire correspondre l'ordre matériel à son orientation.
Une phase ne corrige pas un parcours inversé. Les repères et le sens doivent
venir des bords, coutures et trajets mesurés du projet ; leur choix reste une
proposition de montage tant que le candidat n'a pas été examiné.

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

## Vérifications et portée

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
