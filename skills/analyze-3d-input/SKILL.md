---
name: analyze-3d-input
description: Analyser des images de référence 3D en composants stables, occlusions, articulations et relations de séparation.
---

# analyze-3d-input

Ouvrir les images disponibles avant de conclure. Décrire ce qui est visible et ce qui est inféré. Attribuer des IDs stables tels que body.jaw ou garment.coat. Remplir component.schema.json et les relations de asset.schema.json. Séparer les dents, mâchoires, manches et membres lorsque leur mobilité l'exige. Identifier les vues manquantes et les ambiguïtés ayant un effet sur la fabrication. Un texte ou une flèche appartient à l'overlay, jamais par défaut à l'image clean. Voir [les règles de références](../../references/references-3d.md).

Préparer le dossier conforme à `schemas/construction.schema.json` : gabarit et mensurations, vues face/profil/dos, décomposition avec IDs, pièces et matières, dimensions, hypothèses, assemblages, critères de silhouette, mobilité et livraison cible. Pour un vêtement : lignes continues au-dessus et au-dessous de la ceinture, ouverture des pans, largeur des bras/poignets, couches, doublure, col, pièce amovible, positions de capuche et aisance doivent être explicités. Les observations ne deviennent pas des mesures certaines : indiquer observed/inferred/user-confirmed. Lever les inconnues bloquantes avant la revue du board.

Le board de préparation est construit à partir des images de référence originales fournies par l’utilisateur, avant modélisation. Ne jamais utiliser le mesh produit comme sa propre référence de conception. Le dossier doit fournir `source_references` (preuves des originaux et origine dans la conversation), `source_evidence_keys` pour chaque vue et pièce, et `reference_notes` pour les indices observés ou extrapolés. Les références sources doivent être celles examinées dans le gate references. Elles sont intégrées au board et au dossier. Le type mesh-render est refusé pour les vues de ce board. Un board documentaire créé après la 3D est un diagnostic séparé et ne remplace jamais cette validation.
