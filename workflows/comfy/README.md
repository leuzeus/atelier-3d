# Templates ComfyUI de référence

Catalogue enregistré le 3 octobre 2026. Les graphes JSON de ce dossier sont les
bases réutilisables du projet ; `registry.json` définit leurs identifiants et les
paramètres que Studio accepte. Ils sont au format API ComfyUI.

| Identifiant | Graphe | Usage | Entrées | Sortie | État |
| --- | --- | --- | --- | --- | --- |
| `reference-sd15` | [reference-sd15.api.json](reference-sd15.api.json) | Préparer une variante d'image de référence à partir d'un original, par image-to-image SD1.5 | Image source PNG et prompt | Image PNG | Base enregistrée ; compatibilité native et qualité visuelle à qualifier sur l'installation cible |
| `hunyuan-multiview` | [hunyuan-multiview.api.json](hunyuan-multiview.api.json) | Reconstruire une partie volumique `MULTIVIEW_PART` à partir de deux vues | PNG clean de face et de gauche | Mesh GLB | Base enregistrée ; compatibilité native et qualité géométrique à qualifier sur l'installation cible |

Ces graphes proviennent du dépôt Atelier 3D existant. Ce catalogue n'établit pas
une provenance amont externe ni une exécution réussie. Les paramètres et classes
de nœuds décrits ci-dessous ont été relus dans les graphes et le registre locaux.

## Références SD1.5

Le graphe charge l'image source, l'encode avec le VAE du checkpoint, utilise un
`KSampler`, décode puis sauvegarde l'image. L'original est donc effectivement
consommé ; le prompt seul ne suffit pas.

| Paramètre Studio | Valeur / rôle |
| --- | --- |
| `source` | Obligatoire : `input_name` reçu après upload de l'original PNG avec `purpose=source` |
| `prompt` | Obligatoire : vue et caractéristiques à conserver |
| `checkpoint` | Nom du checkpoint SD1.5 installé ; valeur proposée : `v1-5-pruned-emaonly.safetensors` |
| `negative` | Par défaut : `text, labels, perspective, cropped, watermark` |
| `seed` | Par défaut : `42` |
| `denoise` | Par défaut : `0.35`, intervalle autorisé : `0.01` à `0.7` |

Exemple de paramètres à compléter avant validation :

```json
{
  "source": "REMPLACER_PAR_INPUT_NAME_DE_L_ORIGINAL.png",
  "prompt": "front view, full object visible, neutral background, preserve the source silhouette and proportions",
  "checkpoint": "v1-5-pruned-emaonly.safetensors",
  "seed": 42,
  "denoise": 0.35
}
```

Le graphe fixe actuellement 20 steps, CFG 7, sampler `euler` et scheduler
`normal` ; ces champs ne sont pas exposés comme paramètres dans le registre.
Une adaptation de ces champs produit une variante de template à revoir et à
enregistrer. Ce graphe ne garantit ni une vue orthographique exacte, ni la
cohérence entre plusieurs vues, ni la conservation parfaite de l'identité.
Examiner les pixels contre la source et déclarer les zones inventées.

## Reconstruction Hunyuan multivue

Le graphe encode les vues de face et de gauche, les transmet au conditionnement
Hunyuan multivue, échantillonne un latent 3D puis extrait et sauvegarde un mesh.

| Paramètre Studio | Valeur / rôle |
| --- | --- |
| `front` | Obligatoire : `input_name` de la vue clean de face |
| `left` | Obligatoire : `input_name` de la vue clean de gauche |
| `checkpoint` | Nom du checkpoint multivue installé ; valeur proposée : `hunyuan3d-dit-v2-mv.safetensors` |
| `seed` | Par défaut : `42` |
| `steps` | Par défaut : `30`, intervalle autorisé : `1` à `80` |
| `octree_resolution` | Par défaut : `256`, intervalle autorisé : `64` à `256` |

Exemple de paramètres à compléter avant validation :

```json
{
  "front": "REMPLACER_PAR_INPUT_NAME_FACE.png",
  "left": "REMPLACER_PAR_INPUT_NAME_GAUCHE.png",
  "checkpoint": "hunyuan3d-dit-v2-mv.safetensors",
  "seed": 42,
  "steps": 30,
  "octree_resolution": 256
}
```

Vérifier notamment la disponibilité et les signatures de
`Hunyuan3Dv2ConditioningMultiView`, `EmptyLatentHunyuan3Dv2`,
`VAEDecodeHunyuan3D`, `VoxelToMesh` et `SaveGLB`, ainsi que les sorties du loader
de checkpoint. Le nom d'un modèle dans le template ne prouve pas sa présence
sur la machine. Ce template consomme seulement `front` et `left` ; un package
exigeant d'autres vues nécessite un graphe et un registre adaptés.

Cette reconstruction concerne les parties volumiques. Les panneaux d'un
vêtement `PATTERN_SEWN` restent dérivés de leurs patrons approuvés.

## Réutilisation et validation

1. Choisir la base selon le composant et les vues nécessaires. Si un workflow
   déjà qualifié est disponible pour ce besoin, conserver son origine et
   préparer une variante distincte avant de modifier une base de référence.
2. Vérifier les modèles et nœuds réellement disponibles avec les outils Comfy
   du Studio, puis uploader les images exactes. Remplacer les placeholders
   par les `input_name` retournés.
3. Appeler `comfy_validate_workflow` avec `project_root`, l'identifiant et les
   paramètres. Studio conserve le graphe exact et son empreinte.
4. Pour une exécution autorisée, utiliser `comfy_submit_workflow` avec une
   `request_key` stable ; conserver le workflow, les sources, les paramètres,
   les reçus et les sorties. Studio affecte le préfixe de sortie du job.
5. Examiner les images ou la géométrie. Une validation de compatibilité ou un
   job terminé ne constitue pas une acceptation de qualité.

Les modifications du graphe restent au format API ; enregistrer aussi les
nouveaux paramètres et leurs cibles dans [registry.json](registry.json).
Les anciens jobs conservent leur graphe exact dans les preuves du projet.

La procédure complète est dans [l'intégration Comfy officielle](../../references/comfy-official.md)
et [le skill run-comfy-pipeline](../../skills/run-comfy-pipeline/SKILL.md).

Statut de cette inscription : graphes et cibles de paramètres vérifiés
structurellement ; exécution ComfyUI et validation visuelle `NOT_EXECUTED`.
