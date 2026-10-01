---
name: build-part-package
description: Créer un package .partpkg pour reconstruire séparément une partie volumique d'un asset 3D.
---

# build-part-package

Lire [le contrat de package](../../references/packages.md). Préparer part.json avec vues clean PNG, dimensions, caméra orthographique, hauteur en cm, anchors et relations. Inclure toutes les vues requises par le workflow ; hunyuan-multiview consomme front et left. Des images simplement étiquetées front/left ne prouvent pas une projection orthographique : le vérifier visuellement. Conserver les overlays et masks séparément. Construire, inspecter et lier l'archive sans remplacer l'original.
