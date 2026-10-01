# Board de fabrication : contrat 0.4.0

Le board à présenter au validateur humain comporte trois volets. Il est préparé depuis les images originales et les pièces du découpage proposé, avant reconstruction. Les données observées, extrapolées et confirmées restent distinguées.

## 1. Vues orthographiques et proportions

Fournir face, profil et dos. Pour chaque vue, déclarer `subject_bbox_px: [x, y, largeur, hauteur]` et `subject_height_cm`, hauteur du même sujet visible dans les trois images, distincte du gabarit du personnage si nécessaire. Les cadres doivent contenir tout le vêtement et représenter le même état (capuche relevée, par exemple). Le rendu utilise une échelle commune et conserve le rapport largeur/hauteur des images. Il ne grossit pas séparément les manches ou les poignets.

Mesurer `proportion_checks` directement sur les pixels de référence et de proposition. Chaque entrée contient un libellé, la preuve originale, la vue cible, deux segments de référence et deux segments dans la vue proposée. Chaque segment est une paire de points `[x,y]` en pixels. Le rapport longueur(segment 1) / longueur(segment 2) est comparé avec `tolerance_relative` (au plus 15 %, choisir plus strict selon le cas). Les quatre vues front/side/back/exploded doivent être couvertes. Ne pas utiliser un segment comparé à lui-même ni inventer des mesures pour passer le contrôle.

Pour un vêtement long à capuche, comparer notamment : largeur des épaules/longueur de robe, largeur des manches et poignets, volume de capuche, largeur du panneau central et ouverture entre les deux pans avant. Si les références le demandent, conserver la continuité de la bande centrale au-dessus et au-dessous de la ceinture, l’ensemble capuche-épaules amovible et la possibilité de rabattre la capuche. Ces caractéristiques ne justifient pas d'élargir le gabarit du mannequin. Les vues de profil/dos cachées ou extrapolées doivent être signalées.

Les contrôles calculent les rapports des points fournis ; ils ne détectent pas automatiquement la bonne position anatomique de ces points. Ouvrir les images et vérifier leur placement avant de soumettre le board à l'utilisateur.

## 2. Vue éclatée avec Codex Image

1. Préparer les packages et le dossier de construction à PACKAGED : liste exacte des pièces, dimensions, matières, caractéristiques et contraintes de proportions.
2. Appeler `studio_prepare_exploded_view(project_root, dossier_path)`. L'outil sauvegarde la demande liée aux packages et aux références originales et retourne le prompt et `referenced_image_paths`. Il ne génère pas lui-même l'image.
3. Examiner les images d'entrée. Utiliser **Codex Image intégré (`image_gen`)** avec le prompt préparé et ces images originales. Si cet outil est absent ou échoue, signaler l'indisponibilité et conserver le travail ; ne pas remplacer discrètement la vue par un rendu Blender, un schéma vectoriel ou ComfyUI.
4. Copier le PNG effectivement retourné dans le projet, sans écraser les originaux. Appeler `studio_register_exploded_view(project_root, image_path, tool_source_ref)` avec la référence réelle de l'appel/résultat. Ne pas inventer de résultat de génération.
5. Renseigner `exploded.path`, `exploded.generation_evidence_key`, les `source_evidence_keys`, et une annotation `{component_id, piece_id, anchor_px, label_position_px}` sur **chaque pièce réellement visible**, une seule fois. Positionner les repères et leurs libellés en examinant l'image, dans les espaces libres pour éviter tout chevauchement. Compléter les mesures de proportions de l'éclaté.

L'image générée montre les pièces, sans texte génératif à recopier. Le compositeur ajoute des repères `A01`, `A02`… sur ces pièces et une nomenclature complète liée aux mêmes IDs : **nom, matière, dimensions à plat et caractéristiques**. Les patrons portent ces mêmes références. Cette méthode garantit que les libellés lisibles viennent du dossier, tout en laissant Codex Image produire l'illustration détaillée. En cas de pièce manquante, déformée, surnuméraire ou de proportions incorrectes, corriger la demande et régénérer l'image avant la présentation.

Une modification des caractéristiques, pièces, dimensions, packages ou références après préparation invalide la demande. Le reçu lie les fichiers et la référence d'appel déclarée ; il n'authentifie pas à lui seul un appel externe et ne prouve pas la fidélité des pixels.

## 3. Patrons 2D de fabrication

Les contours de couture viennent des pièces réelles du `.garmentpkg`. L'illustration Codex Image n'est pas utilisée pour inventer ou remplacer ces contours. Pour chaque pièce textile, renseigner `characteristics`, droit-fil, marge, puis l'objet `pattern` :

| Champ | Contenu et représentation |
| --- | --- |
| `cut_outline_cm` | Polygone de coupe explicite en cm, contenant le contour de couture et sa marge déclarée ; trait continu |
| Contour du package | Ligne de couture/piqûre ; tirets, avec les IDs `S01`, `S02`… associés aux assemblages |
| `folds` | ID, nom, type et points de la ligne de pli ou de milieu ; trait mixte et libellé |
| `fold_notes` | Fonction du pli ou justification explicite de l'absence de pli ; ne pas ajouter un pli fictif sur toutes les pièces |
| `grain_direction` | Direction du tissu dans les coordonnées 2D de la pièce ; double flèche « Droit-fil » |
| `assembly_marks` | ID de repère, couture concernée, position de 0 à 1 sur le bord et symbole simple/double ; crans appariés sur le contour de coupe |
| `mark_notes` | Explication des repères ou de l'absence de couture pour une pièce non assemblée |
| `cut_quantity`, `cut_instruction` | Quantité, côté/miroir et instructions de coupe explicites |

Chaque couture doit avoir des repères correspondants sur ses deux pièces. Pour une orientation reverse, la position B doit être `1 - position A`. Les contrôles refusent les contours auto-intersectés, les marges dessinées insuffisantes, les plis hors pièce et les repères absents ou contradictoires. Les contrôles de marge et de contenu du contour utilisent des échantillons géométriques ; ils ne remplacent pas une qualification de patronage.

Tous les patrons utilisent **la même échelle de présentation**, avec une réglette en cm. Une manche courte doit rester plus petite qu'un long pan de robe. Les noms, IDs, matières, dimensions, marges et instructions restent lisibles à côté des formes. Le dossier HTML contient les coordonnées et les détails complets des plis, repères et coutures.

Ce board permet de valider le découpage pour la production 3D. Son image n'est pas une impression de coupe grandeur nature ni une certification d'ajustement d'un vêtement réel. L'échantillonnage des courbes, l'aisance, les raccords, les doublures et le drapé doivent être vérifiés sur le projet.

## Présentation et décision

Appeler `studio_build_construction_board`, ouvrir l'image et le dossier et inspecter les pixels, particulièrement les libellés et les repères. Demander la validation explicite du découpage à l'utilisateur. Un ancien board sans ces données est refusé par le nouveau contrat ; produire une nouvelle version et conserver l'ancien. Ne pas fabriquer une approbation humaine ni transférer une ancienne décision vers une nouvelle image.
