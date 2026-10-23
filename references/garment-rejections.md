# Lire un rejet de construction sans accepter le candidat

`garment` peut échouer avant d'avoir écrit un boundary map et un reçu. Dans ce
cas, `inspect_sewing_placement` ne peut pas qualifier le nouveau candidat.
Un rejet géométrique dans la construction du mesh ou son préflight conserve
maintenant un diagnostic séparé sous
`.a3d/blender/garment-rejections/attempt-*/diagnostic.json`.

Le message d'erreur et `pending_blender_operation.diagnostic` donnent chemin
et SHA. Demander le code exact de `studio_blender_operation` avec
`operation="inspect_garment_failure"` et ces arguments :

```json
{"component_id":"garment.coat","attempt_dir":".a3d/blender/garment-rejections/attempt-IDENTIFIANT"}
```

Cette lecture reste possible pendant le pending, après restauration et après
modification de la recette courante. Elle vérifie chemin, SHA, composant/package
et statut du diagnostic historique. Elle ne dépend pas de l'existence du mesh
rejeté, ne change aucun fichier/état/scène et ne libère pas l'échec. Le rapport
reste `status=REJECTED`, `accepted=false`, `simulation=NOT_EXECUTED`.

## Orientation et contact

`directions.violations` localise la couture et les bords source, le segment,
ses paires précédente/suivante, indices, UV source et positions 3D en cm.
Les positions de préflight sont celles réellement lues dans Blender. Le test
local compare le cosinus au seuil **-0,5**, inchangé. Les résumés précisent le
nombre de segments opposés et le cosinus des cordes entre extrémités.

Des tangentes locales de courbes peuvent s'opposer alors que les cordes globales
vont dans le même sens. Examiner la recette, le sens et la phase d'enroulement
ainsi que les contours : ces statistiques ne prouvent ni erreur de rotation,
ni faux positif, ni défaut Cloth. Le runtime conserve son rejet local.

`initial_contacts` localise chaque sommet qui dépasse le seuil de pénétration :
pièce, bords nommés, UV repos, position, poids de maintien, collider, face et
normale de surface, point projeté, profondeur et seuil en cm. La géométrie
évaluée du collider est liée au contexte. C'est la mesure signée au sommet déjà
utilisée par le garde-fou ; elle ne prouve pas l'absence de croisements de triangles.

Les rejets de qualité conservent les arêtes/faces hors limites lorsque le
maillage dérivé a pu être calculé. Si un rejet intervient avant sa disponibilité,
le rapport conserve source, recette, checkpoint et erreur sans inventer de
localisation. Aucun reçu de construction réussie n'est écrit pour ce candidat.

Appeler ensuite `restore_checkpoint` avant une nouvelle mutation. Conserver le
package et le board approuvés, corriger la recette séparée puis rebuild. Une
nouvelle conception des patrons conserve sa revue humaine. Les rapports sont
créés dans des répertoires uniques et ne sont pas réécrits lors des reprises.
Les diagnostics Cloth évalués restent séparés : `inspect_sewing_failure`.

## Reproduction et portée des tests 0.5.6

```text
python -B -m unittest discover -s tests -v
pwsh -NoProfile -File scripts/validate_contracts.ps1
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_garment_rejection_smoke.py
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_smoke.py
```

189 tests Python passent. Le test natif Blender 5.2.2 LTS provoque trois rejets
dans un projet isolé : rotation opposée d'un panneau, enroulement trop comprimé,
et sommets d'un panneau dans un volume fermé. Il vérifie localisation, SHA,
lecture avant/après restauration, source/package/board/ancien mesh/reçu préservés,
absence de Cloth et blocage des mutations pendant la récupération.
Le test pur distingue courbes locales et inversion globale des extrémités.
La régression physique synthétique conserve probes, local/full et freeze.
Les artefacts sont sous `work/native-*`, exclus de la distribution.

Le projet et le Blender consommateur ne sont pas modifiés par ces essais.
Les erreurs de rotation et de contact de sa recette restent des corrections
d'asset à vérifier séparément. Aucun fitting réel ou défaut du solveur n'est qualifié.
