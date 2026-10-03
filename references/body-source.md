# Corps cible issu d'un fichier Blender existant — 0.6.4

Le choix du corps appartient à l'utilisateur. Ne pas le remplacer par une
enveloppe de collision historique ou déduire son anatomie de sa hauteur.
Un squelette ajouré peut avoir des sections ouvertes, absentes ou multiples :
cela retourne NOT_QUALIFIED, pas une circonférence inventée.

## Sélection et inspection

Enregistrer un JSON conforme à `schemas/body-source.schema.json` dans le projet :

```json
{
  "version": 1,
  "source_blend": "sources/corps-original.blend",
  "source_sha256": "SHA256_EXACT_DU_FICHIER",
  "source_ref": "corps choisi par l'utilisateur ; pose et unités relevées",
  "frame": 1,
  "unit_scale_m": 1,
  "meshes": ["Corps", "Main_G", "Main_D"],
  "dependencies": ["Rig", "Controle"],
  "reference_object": "A3D.BodyReference"
}
```

La source peut être un chemin absolu vers l'original choisi ; elle est lue,
jamais sauvegardée. Relever le SHA, l'image et les unités sur ce fichier exact.
Les meshes sont le corps ; les dépendances sont les ARMATURE/EMPTY nécessaires
à sa pose. Ne pas exclure un rig utile parce que son nom contient « robe » ;
exclure la géométrie de l'ancien vêtement. Un catalogue par
`bpy.data.libraries.load` cherche les noms sans ouvrir le fichier complet.
Un timeout CLI est une erreur d'inspection, pas un échec de l'asset ; ne pas
répéter aveuglément le même appel.

Demander le code exact à `studio_blender_operation` :

```json
{"operation":"inspect_body_source","arguments":{"selection_path":"body-selection.json"}}
```

La scène temporaire contient seulement les objets déclarés. L'opération vérifie
les dépendances effectivement chargées, évalue la pose à l'image choisie et
retourne dimensions, géométries, plages d'indices, matrices, modifiers et repères
du rig. Les drivers Python nécessitant un contexte arbitraire sont refusés.
Les données temporaires sont retirées aussi sur refus. Scène courante, image,
fichier et SQLite restent inchangés. Si des noms sélectionnés existent déjà dans
la scène courante, l'opération refuse l'ambiguïté : inspecter ce contexte existant.

## Référence figée et introduction progressive

```json
{"operation":"prepare_body_reference","arguments":{"selection_path":"body-selection.json"}}
```

Après revue du board actuel, cette opération écrit un nouveau
`.a3d/blender/body-reference-ID.blend` et son reçu. Il contient un objet avec les
surfaces évaluées en coordonnées mondiales, en mètres. Les parties gardent leurs
indices séparés dans le reçu : aucun weld, remesh, remplissage anatomique,
lissage supplémentaire ou mise à l'échelle du gabarit. Ancien vêtement, rig,
animations, matériaux et colliders ne sont pas exportés. Cette pose figée ne
remplace pas le rig d'origine pour l'animation finale.

Le reçu fournit `artifact.path`, `artifact.sha256`, `reference_object` et
`geometry_sha256` pour le corps `role=target` de la fiche de fitting.
Après un full libre courant PASS, utiliser `introduce_fitting_context` avec
cette source et cette fiche. Il importe seulement les objets manquants et
vérifie aussi les identités des objets déjà présents. Un collider auxiliaire
distinct peut ensuite être ajouté depuis sa propre source exacte : déclarer
le corps conservé et ce nouveau collider dans la fiche/recette, puis introduire
ce contexte. Aucun remplacement silencieux ou duplication des objets existants.

Les points d'os mesurés ne valident pas les correspondances vêtement/corps.
Le rapport conserve `anatomical_landmarks=NOT_VALIDATED`, `collider=NOT_CREATED`,
`fitting=NOT_EXECUTED`, `accepted=false`. Qualifier épaules, coudes, poignets et
repères transversaux avant `fitting_placement` ; suivre la
[reprise et le fitting distinct](clean-construction-fitting.md).

## Test interactif isolé

`tests/run_interactive_clean.py` lance sa propre instance GUI cachée, avec profil,
port localhost et projet distincts. Fournir `--blender`, `--addon` (dossier de
l'add-on MCP officiel existant) et un `--output` neuf. `--runtime` teste une copie
installée ; `--body-selection` ajoute un corps réel. Aucun appel ne se connecte
au port de production 9876 ou à un Blender déjà ouvert. Le garde officiel reste
actif : un appel témoin à `read_factory_settings` est refusé. Le test conserve
ses preuves sur disque et arrête uniquement son propre PID.
