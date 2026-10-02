# Inspection et préparation locale d'interfaces — 0.6.2

Après un transfert cousu, le torse peut être correct tandis que des tangentes
d'emmanchure s'opposent encore à celles des manches. Une corde globalement
concordante n'annule pas ce défaut local et ne prouve pas une erreur du contrôle.

## Inspection d'un candidat refusé

`inspect_sewing_placement` lit désormais ce candidat sans exiger son admission
géométrique. Elle conserve les vérifications package/source/mapping, transform,
visibilité, topologie, FlatRest et pins, et refuse leur altération. Les colliders
déclarés doivent toujours correspondre à leur identité/pose/épaisseur.

Le rapport retourne `directions`, tous les partenaires et arcs source, les
contacts, la qualité et un `preflight.status` PASS ou REJECTED avec les erreurs.
Ces états décrivent les mesures initiales, avec `MEASUREMENTS_ONLY`,
`accepted=false`, `simulation=NOT_EXECUTED`. Ils ne permettent aucune simulation
ou mutation supplémentaire. L'inspection ne modifie ni la scène, ni le fichier
enregistré, ni l'état canonique ; elle ne libère pas un pending.

## Corriger les quelques tangentes locales

Dans une copie de recette, déclarer :

```json
"interface_preparation": {
  "source_ref": "rapport-et-hypothese-locale",
  "interfaces": [
    {"seam_id": "armhole-front", "moving_side": "b"}
  ],
  "radius_cm": 5,
  "max_displacement_cm": 2,
  "target_cosine": -0.4,
  "max_passes": 4
}
```

Appeler `prepare_sewn_stage(stage=assembly)` sur la copie cousue actuelle.
Le côté opposé et les panneaux extérieurs restent fixes. Les cibles angulaires
visent une valeur strictement supérieure au seuil inchangé −0,5. Le voisinage
est limité par distance sur les arêtes du mesh existant. Une préparation
harmonique puis des projections conjointes de longueurs et d'angles évitent de
figer deux cibles incompatibles sur un sommet de couture partagé. Les poids 1
restent fixes. Budget, ambiguïtés antiparallèles et précontrôles finaux sont des
refus, pas des dérogations. La méthode peut ne pas trouver de candidat.

Le reçu expose les indices source réellement concernés, les mesures avant/après,
les passes et le déplacement. `PREPARED_NOT_SIMULATED` ne vaut pas PASS Cloth.
Ne pas réinitialiser la géométrie, modifier les contours, changer une closure
en permanent ou utiliser un script externe pour appliquer le résultat.

## Monter un groupe encore trop éloigné

Quand les tangentes passent mais que les écarts initiaux induisent un déplacement
Cloth refusé, une préparation distincte peut rapprocher un groupe explicitement
sélectionné, sans déplacer le torse ou un composant externe :

```json
"panel_mount": {
  "source_ref": "mesures-des-ecarts-et-refus-physique",
  "moving_pieces": ["sleeve-left", "sleeve-right"],
  "seam_ids": ["sleeve-side", "armhole-front", "armhole-back"],
  "max_displacement_cm": 20,
  "iterations": 600,
  "settle_iterations": 600,
  "strain_margin": 0.02
}
```

Adapter les IDs aux seuls panneaux et coutures source concernés. La sélection
est explicite, sans ajout de liens. Les panneaux extérieurs et pins de poids 1
restent immobiles. Le solveur attire les partenaires permanents et projette les
longueurs dans une plage plus stricte que le contrat existant. Il retire ensuite
l'attraction de couture pour relâcher la déformation. Cette marge ne relève pas
les seuils ; les contrôles natifs complets sont obligatoires à la fin. Les écarts
résiduels sont conservés pour Cloth, sans soudure ou PASS artificiel.

Les options ne sont disponibles que via `prepare_sewn_stage` sur un stage natif
lié à ses reçus. Elles ne se mélangent pas au préfit global, au fitting ou aux
bâtis. Le budget ne dépasse pas la limite existante. Le receipt expose les
pièces, coutures, indices, déplacements, écarts et contexte. Un candidat refusé
conserve son diagnostic et exige `restore_checkpoint` avant une nouvelle mutation.

Une correction locale peut précéder le montage du groupe. Si une recette contient
les deux options, la transition suivante applique le montage du groupe puis
la correction locale ; le précontrôle reste obligatoire pour chaque opération.
Après chaque changement de recette/placement, qualifier le local sur les
interfaces réellement à terminer, puis full `purpose=assembly`. Aucun changement
de board humain à coupe inchangée. La géométrie peut être conservée par checkpoint,
mais jamais qualifiée par le seul solveur de préparation.

## Après un montage complet PASS

Suivre [la reprise et le fitting séparé](sewn-stages.md). Copier la recette en
retirant `interface_preparation` et `panel_mount`, puis introduire le corps
identifié et les mesures de fitting. `prepare_sewn_stage(stage=fitting)` conserve
le résultat complet actuel. Un nouveau local/full de fitting est requis avant
freeze. Le PASS de montage court ne valide pas le corps cible, la silhouette,
la stabilité longue, les mouvements ou l'export Unreal.
