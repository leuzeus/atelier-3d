# Maillage de patrons borné par une enveloppe commune

`blender.bounded_pattern_meshing` expose uniquement :

```python
coordinates, faces, mapping = triangulate(
    boundary, recipe, regular_mesh, envelope=envelope
)
report = boundary['preparation_refinement']
```

Le module est une extraction du noyau natif V4 gelé `815922eb0fe5173653fe5e0aa2ecdbbd93ac64b6f7f37c41605acc5af6232f70`. Importer ce module ne change aucun caller. L’activation, le schéma, la construction du composant, le protocole Blender et les gates appartiennent au coordinateur. Cette unité a des preuves portables seulement ; aucun maillage du vêtement actuel ni processus Blender n’a été exécuté pour la qualifier.

## Protocole minimal du caller

- `boundary['piece_id']` est une identité de pièce explicite, sans nom de vêtement codé dans le module. Les contours, clés, provenance et autres données restent des entrées sourcées.
- `envelope.check(phase)` est le checkpoint partagé, y compris le callback passé à `a3d.mesh_refinement.improve_interior(..., check=envelope.check)`. Les callbacks sont des observations/arrêts, sans mutation des entrées matérielles.
- `envelope.reserve(kind, amount, owner=piece_id)` débite un travail monotone. Les kinds requis sont `attempted_insertions`, `native_cdt_calls`, `native_remesh_attempts` et `native_point_slots`.
- `envelope.material_controls` est un mapping readonly `piece_id → nombre initial`. Ces contrôles sont déjà débités par le caller ; le module ne les réserve pas une seconde fois. Le snapshot doit confirmer ce mapping et les compteurs payés globaux/par propriétaire.
- `envelope.snapshot()` retourne au minimum `limits`, `work`, `owner_work` et `material_controls`, comme l’implémentation interne `a3d.meshing_envelope`. Les snapshots ne produisent aucune admission.

Le module ne construit pas d’enveloppe, de clock, de délai ni de budget de reprise. Un propriétaire ayant déjà commencé des coûts natifs dans la même enveloppe est refusé : il ne peut pas recréer ses births ou ses compteurs locaux. Une reprise de run/checkpoint reste une opération explicite du caller.

## Limites et débits

Les limites locales historiques sont au plus **8 remesh**, **9 CDT**, **4 000 insertions** et **30 000 points**. Elles restent des garde-fous locaux et des statistiques par pièce. Le caller déclare aussi les bornes totales explicites des coûts CDT/remesh/point slots ; un total global de neuf CDT pour toutes les pièces n’est pas supposé.

Le plafond supplémentaire `attempted_insertions` appartient à l’enveloppe **du composant**, sans multiplication par le nombre de pièces. Les ajouts matériels initiaux et les tentatives intérieures consomment ce même compteur. La sélection prépare des propositions temporaires ; `reserve('attempted_insertions', n, owner=...)` puis `reserve('native_remesh_attempts', 1, owner=...)` interviennent avant leur entrée dans le pool physique du CDT. Un refus après une réservation conserve son débit.

Chaque CDT réserve aussi `native_point_slots = len(input_pool)` puis une tentative CDT. Les slots sont un **coût cumulatif distinct** du nombre courant de sommets. Le plafond de sommets vivants **du composant** reste contrôlé par `build_mesh` du caller ; le module ne remplace pas cette vérification par sa borne locale de 30 000 points.

Une première réserve consommée suivie d’un refus de la seconde reste consommée. Aucun remboursement n’est introduit. Il n’existe aucun CDT supplémentaire à un arrêt pour stagnation, budget local atteint ou rollback d’un candidat non monotone.

## Identités, transport et restauration

Chaque sortie CDT doit correspondre à **un seul ID d’entrée**, sans alias, ID absent ou doublon. Les births sont fixées depuis le pool d’entrée pour les anciens IDs et depuis le point d’insertion réellement transporté pour les nouveaux IDs. Leur référence n’est pas recentrée à chaque passage.

Le lisseur intégré reçoit ces births dans l’ordre des IDs retournés. La validation mesure le déplacement cumulé des coordonnées et de leur transport `mathutils.Vector` Float32 ; la plus grande des deux distances doit rester dans `.5 * min_spacing_cm`, jamais au-delà de 0,5 cm dans cette route. Les sources sont restaurées exactement avant admission numérique du candidat. Les associations, finitude, intérieur, collisions d’IDs et triangles inversés/collapsés sont refusés selon les garde-fous V4. Les seuils historiques du noyau sont conservés, sans relèvement.

Le meilleur état conserve la triangulation entière (`verts`, `edges`, `faces`, `origins`), coordonnées, mapping, smoothing, pool, births, added et passes. Un rollback restaure tous ces tableaux. Les statistiques d’added/passes du candidat retourné peuvent donc revenir au meilleur état ; les compteurs de travail CDT/remesh/insertions/slots de l’enveloppe restent monotones.

Le rapport conserve les hashes de pools/births, les transports et historiques numériques, les références d’entrée et un snapshot d’enveloppe. Un arrêt ou refus expose sur l’exception `bounded_meshing_partial` le meilleur état **déjà snapshotté**, sans copie/mesure après expiration. Son `last_completed_work_snapshot` est explicitement un checkpoint historique, **pas le ledger terminal** ; le caller reste responsable de l’observation finale du run.

Les contours, recette, profil régulier et charge matérielle sont revérifiés avant le retour. Un checkpoint final doit réussir avant publication du nouveau rapport dans `boundary`. Le calcul du quadrillage intérieur existant est encadré par des checkpoints avant/après ; il n’a pas de callback interne dans cette unité. Le lisseur, les boucles de transport, les candidats d’insertion, les traces et les retours utilisent des checkpoints coopératifs internes.

## Portée des statuts et preuves

Le discriminant du rapport est `BOUNDED_PATTERN_MESHING_V1`, avec `qualification: NONE`, `admission: NONE` et `physical_mesh_qualified: false`. Le statut historique `TARGET_REACHED` qualifie uniquement les métriques numériques calculées du mesh retourné, pas un placement, support physique authored, montage, Cloth, drapé, fitting ou revue artistique. Aucun `READY` ni gate produit n’est ajouté.

Les tests portables emploient des fixtures Vector32/CDT fournies. Ils contrôlent identités singleton, transport IEEE, ancres exactes, winding, rollback complet, non-remboursement, caps composant, mutation et échéances. Les helpers purs sont comparés en AST au gel V4 ; trois petits scénarios reproduisent les coordonnées/faces/mapping et tous les champs historiques de ses rapports. Ces témoins ne remplacent pas la future qualification native du code intégré sur les pièces et le composant réels.
