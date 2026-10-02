# Revoir le prépositionnement avant Cloth

Après `garment`, appeler `studio_blender_operation` avec l'opération
`inspect_sewing_placement` et transmettre son code exact au MCP Blender :

```json
{"component_id":"garment.coat","recipe_path":"recipe.json"}
```

L'inspection vise le maillage de simulation non accepté dans la copie de travail
attendue. Elle exige les patrons, le board et la route approuvés, une recette liée
au mesh, les poids et le repos intacts, et les colliders déclarés inchangés.
Le précontrôle de qualité et de pénétration reste actif. Restaurer le checkpoint
après un échec si Cloth est encore actif. Aucun fichier ni état n'est écrit par
cette inspection ; elle ne crée pas de pending et ne libère pas un pending existant.

Si `garment` a été rejeté avant son mapping/reçu, utiliser
[`inspect_garment_failure`](garment-rejections.md) pour le nouveau candidat.
Ne pas l'inspecter à travers le mesh de la toile précédente. Restaurer avant
la prochaine mutation ; conserver le diagnostic historique pour comparer les recettes.

## Lire les mesures

- `seams` : chaque paire présente positions en cm, écart, IDs de panneaux et
  bords nommés, UV source, longueur d'arc du contour et poids de maintien. La
  longueur d'arc situe l'échantillon dérivé ; ce n'est pas un cran de fabrication.
  Les bords nommés proviennent de la source vérifiée, y compris pour les anciens mappings.
- `straight_segment_hits` : premier point où le segment entre partenaires
  traverse chaque collider déclaré, avec face et normale. Ce trajet droit décrit
  le rapprochement initial ; il ne représente pas le trajet réel du solveur.
  Un croisement est un avertissement de montage, pas une preuve d'impossibilité.
- `panels.supports` : positions et poids des sommets maintenus, même hors couture.
  Vérifier notamment col, épaule et poignets avant d'en réduire les poids.
- `collider_regions` : projections des centres de faces sur le collider,
  étendues spatiales, distances, offsets signés et produit scalaire des normales.
  Les régions n'ont pas de noms anatomiques déduits. Des normales opposées sont
  un indice à examiner, pas une preuve de mauvais fitting ; la mesure dépend de
  l'orientation du collider. Ce contrôle n'est pas un test exhaustif de triangles
  ni d'auto-intersection du tissu.

`above_final_seam_tolerance` compare l'écart initial au seuil **final** de la
recette. Un montage ouvert peut normalement dépasser ce seuil avant couture.
Le rapport retourne `accepted=false`, `simulation=NOT_EXECUTED` et
`visual_validation=NOT_EXECUTED`, même sans avertissement.

Chaque `simulate_sewn` archive aussi ce contexte initial dans
`attempt-*/placement.json`, avant les probes et frames Cloth. Son chemin/SHA est
lié au résultat ou au diagnostic évalué d'échec ; il reste disponible après
restauration. Ce rapport automatique complète la revue faite avant simulation.

## Préparer un bras posé avec le placement natif existant

1. Mesurer l'axe du bras et son volume dans sa pose actuelle. Identifier les
   bords avant/arrière, épaule, emmanchure et poignet avec le graphe de couture
   approuvé. Ne pas confondre une manche alignée sur l'axe avec une manche enfilée.
2. Pour un premier enroulement, utiliser `mode=cylinder`. L'axe local est Y :
   `angle=(u-origin_u)/radius_cm`,
   `local=(r*sin(angle), v-origin_v, r*cos(angle))`. `mirror_u=true` inverse
   l'angle. Les rotations sont Euler XYZ en degrés puis la translation en cm.
   Calculer une rotation qui amène Y sur l'axe mesuré du bras, et documenter les
   origines et le sens de chaque panneau avec les partenaires de couture.
3. Exemple synthétique : deux demi-panneaux de largeur 20 cm, rayon `20/pi`
   soit 6,3662 cm ; origines U de 0 et -20 pour des demi-tours successifs.
   Pour un bras incliné de 35° autour de Y, appliquer `R_y(35°) * R_x(90°)` et
   convertir le résultat en Euler XYZ. Transformer aussi les translations avec
   `R_y(35°)`. Les paramètres réels dépendent des contours et de la pose mesurés.
4. Refaire `garment(..., rebuild=true)` après modification de placement, puis
   inspecter écarts, supports, trajets, orientations et pénétrations. Examiner un
   rendu de la toile initiale autour du mannequin avant Cloth. Conserver l'ancien
   mesh archivé et le package approuvé ; aucune soudure par proximité.
5. Un rayon constant conserve un enroulement approximatif pour une manche effilée :
   les circonférences peuvent varier et laisser une ouverture. Des épaules ou
   emmanchures complexes demandent leur propre placement. Ne pas transférer ce
   réglage synthétique au vêtement réel sans mesures. Si les contrôles échouent,
   corriger localement la recette et justifier tout placement dérivé supplémentaire
   avec qualité repos/placement et collision ; ne pas modifier les seuils pour passer.

Choisir ensuite le sous-ensemble local autour de l'emmanchure et suivre
[le parcours de toile](sewn-toile.md). `trial_pieces` sélectionne des pièces
entières : une pièce prolongée en jupe n'est pas un petit coupon spatial.
Une réussite du diagnostic n'autorise pas la simulation complète ; le PASS local
actuel et les contrôles de drapé, silhouette et mobilité restent requis.
