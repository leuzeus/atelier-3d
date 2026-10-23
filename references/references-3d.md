# Références pour reconstruction

Conserver source, clean, mask, overlay et métadonnées séparément. Une vue clean doit être sans texte ni flèches et montrer toute la pièce à une échelle stable. Conserver la provenance de tout recadrage ou génération.

Comparer les vues sur identité, proportions, costume, latéralité, pose et dégagement des articulations. Les zones cachées restent des hypothèses. Préférer une référence détaillée localisée à une augmentation aveugle du coût GPU de tout l'asset.

Enregistrer les images clean examinées ainsi que la planche de contact comme preuves avant la décision references. Une validation numérique de dimensions ne prouve ni identité ni orthographicité. Les pixels doivent être examinés.

## Templates de préparation et reconstruction

Le [catalogue ComfyUI](../workflows/comfy/README.md) conserve les graphes de
référence, leurs paramètres et des exemples à compléter. Pour préparer une image,
`reference-sd15` utilise l'original PNG par image-to-image : enregistrer sa
provenance, uploader avec `purpose=source` et fournir le `input_name` reçu.
Ce template ne garantit pas l'orthographicité, l'identité ou la cohérence multivue.

Après revue des vues clean, `hunyuan-multiview` peut servir de base à la
reconstruction d'une partie volumique depuis face et gauche. Si le composant
exige d'autres vues, adapter explicitement le graphe et son registre. Les patrons
textiles approuvés restent la source des panneaux `PATTERN_SEWN`.

Privilégier une base déjà adaptée et qualifiée au besoin. Conserver une variante
distincte lors d'un changement de structure, avec son origine et ses paramètres.
Les bases fournies restent à qualifier sur les nœuds et modèles réellement
installés, puis sur les pixels ou la géométrie produits.
