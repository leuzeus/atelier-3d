# Complétude des pièces dans Blender

Après un refus ou une absence de pièces, suivre [la reprise ciblée](preparation-recovery.md) :
identifier la cause, proposer une correction ou la production des éléments
manquants ; si la technique approuvée dépasse le support du logiciel, expliquer
la limite et attendre le choix de l'utilisateur avant de changer de méthode.

Le nombre d'objets ou d'îlots ne prouve pas la présence des pièces prévues.
Le contrôle réconcilie chaque identité `(component_id, piece_id)` avec le
package lié à la planche approuvée. Chaque identifiant source est attendu une
fois ; les exemplaires distincts doivent avoir leurs propres identifiants.
Les accessoires rigides restent hors du compteur textile.

## Résultats et revue

`inspect`, la préparation native et les opérations de construction retournent
`piece_completeness` et `summary`. Présenter ce résumé dans le chat, avec la
liste des pièces manquantes, chaque fois que les aperçus sont montrés.
`piece_completeness.review` désigne une page HTML avec le bilan près des images
techniques existantes. La préparation fournit aussi un `completeness.json`
dans le dossier de son essai. Les images originales restent inchangées.

Le cas robe bleu nuit doit être annoncé comme « Manteau : 10/10 ; vêtement :
10/15 pièces textiles présentes ; 5 pièces manquantes », puis nommer
`garment.hood-yoke/hood-left`, `hood-right`, `yoke-upper`, `yoke-lower` et
`garment.belt/belt`. Ce texte est un exemple historique, pas un inventaire
automatique de la scène actuellement ouverte.

Le résultat distingue :

- `components` : couverture par composant ; un résultat local complet
  n'accorde aucun verdict global.
- `global` : identités attendues et présentes, absences, doublons, identités
  inattendues et correspondances non vérifiables.
- `visible_in_view_layer` : visibilité Blender déclarée. L'occultation et le
  cadrage dans les pixels restent `NOT_VERIFIED`, même si l'objet est visible.
- `candidate_mode=preview` : candidats de préparation explicitement suivis,
  y compris ceux qui restent `NEEDS_CORRECTION` ou `NEEDS_CLARIFICATION`.
- `candidate_mode=active` : géométrie active de simulation ou de rendu.
  Témoins, colliders et anciennes variantes archivées sont exclus.
- `qualification` : la présence ne vaut ni préparation READY, ni simulation,
  ni fitting, ni acceptation artistique.

Un candidat partiel peut être inspecté et rendu. Si sa topologie ne correspond
plus au fichier de correspondance ou si sa provenance est ambiguë, le statut
est `NON_VERIFIABLE`. Les coordonnées peuvent évoluer sans perdre l'identité
des faces ; les surfaces consolidées et gelées conservent cette correspondance.

## Admissions et invalidation

Les essais Cloth et les transitions de montage exigent la complétude du
composant qu'ils traitent. Le `full` d'une recette reste une simulation complète
de ce composant, pas de tout le vêtement. L'assemblage global, les scripts de
comportement/validation/export et la validation finale exigent une couverture
globale complète de la géométrie active. Les autres contrôles de production
et décisions humaines restent nécessaires.

Les résultats conservés lient la planche, les packages, les correspondances,
le fichier Blender sauvegardé et un relevé de la géométrie réellement inspectée.
Les jalons canoniques refusent un ancien reçu si ces fichiers changent ou si
l'observation indique une scène modifiée non sauvegardée. Les opérations
natives revérifient la scène vivante avant leur admission. `studio_project_status`
expose seulement le dernier état vérifiable sur disque et le marque
`live_scene=NOT_REINSPECTED` : cet outil ne peut pas observer Blender.

Une inspection sans planche approuvée reste possible, mais sa complétude est
non vérifiable. Après modification de la scène ou des packages, refaire
`inspect` sur le candidat sauvegardé. Une scène importée sans correspondances
source ne peut pas être déclarée complète sur la seule base de ses noms.

Avant l'inspection native, demander l'autorisation d'exécuter le code exact
retourné par `studio_blender_operation`, selon [le protocole Blender](blender.md).
