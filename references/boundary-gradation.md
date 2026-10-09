# Gradation synchronisée des bords source

`a3d.boundary_gradation.grade_shared_boundaries` prépare un ensemble complet
de bords issus des patrons. Il sélectionne les intervalles près des angles,
transporte leurs paramètres communs sur les partenaires déclarés, puis répète
la gradation après chaque union jusqu'au point fixe. Il conserve les anciens
échantillons et coordonnées exactement. Il ne crée aucune relation de couture.

Le caller fournit le dossier source, la recette dérivée, les paramètres de
maillage régulier, les bords et coutures du baseline, le transport numérique
natif `transport_2d` et l'enveloppe commune déjà ouverte. La même enveloppe
continue dans le maillage intérieur. Le service ne recrée pas d'horloge, ne
rembourse pas les essais et n'exécute ni Blender ni Cloth.

Les compteurs requis sont `capture_nodes`, `capture_bytes`, `output_nodes`,
`output_bytes`, `work_steps`, `sampling_calls`, `sampling_point_slots`,
`fraction_requests` et `attempted_insertions`. L'union des nouveaux contrôles
matériels est débitée au composant dans `attempted_insertions`. Ce budget est
partagé avec les insertions intérieures suivantes. Les slots de sampling sont
des coûts cumulés ; la limite de sommets présents au composant reste distincte.

Les paramètres, supports source et propriétaires proviennent des entrées.
Une ambiguïté de propriétaire, une collision d'identités après transport, une
source modifiée, une stagnation ou un budget épuisé produit un refus explicite.
Le service ne rapproche pas les points et ne modifie pas les tolérances.
Réorganiser les tables préparées conserve le résultat ; réorganiser le source
avec une ancienne orientation de baseline incohérente est refusé. Le caller
doit produire un baseline cohérent pour le source exact.

Le résultat contient les bords publics, les coutures remappées et un rapport
`SYNCHRONIZED_SOURCE_BOUNDARY_GRADATION_V1`. Les cartes numériques de travail
du sampler sont omises. Le caller doit revérifier les coins source et relier
les crans aux nouveaux bords. Les crans matériels ne deviennent pas des pins.
Le rapport contient les identités des entrées, les anciens indices remappés,
les intervalles dérivés et leurs coûts. Son snapshot d'enveloppe est pris avant
les réservations de sortie et ne décrit pas le coût terminal de l'opération.

`qualification=NONE`, `native=NOT_EXECUTED` et les absences d'admission et de
preuve de présence physique sont conservées. Le point fixe concerne la
gradation des intervalles ; l'angle minimal final, la métrique, les contacts,
le fitting et les gates humaines restent à contrôler sur le candidat natif.

L'activation conjointe avec le noyau natif et les callers de production relève
du profil explicite de préparation. Cette interface seule ne l'active pas.
