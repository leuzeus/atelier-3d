# Raffinement CDT au voisinage des bords protégés

La préparation régulière conserve tous les arrêts physiques requis par les deux bords homologues d’une couture. Deux coins source distincts peuvent donc produire un intervalle court sur le partenaire. Le raffinement ajoute des sommets dérivés à l’intérieur du patron ; il ne supprime, ne rapproche et ne déplace aucun arrêt de contour.

## Cause mesurée et correction

L’investigation de la source 53 a observé un intervalle matériel de `0,010898330561834733 cm` sur le devant gauche. Ses extrémités portent deux vrais coins de partenaires distincts. Sur la face incidente 2607, le candidat équilatéral calculé depuis cet intervalle se trouve dans le patron et dans la face. Sa distance au bord est `0,009438231125385613 cm`, supérieure à la séparation déjà requise de `0,0021796661123669466 cm`.

La règle précédente remplaçait ce candidat par un circoncentre dès que celui-ci appartenait au patron complet. Le circoncentre de cette face était pourtant extérieur à la face incidente. Le petit triangle formé avec le bord court mesurait alors `13,947824987171709°`, contre environ `60°` pour la proposition locale. Ces deux mesures décrivent des propositions géométriques isolées ; elles ne prédisent pas le résultat du CDT et de son conditionnement.

Preuve de diagnostic conservée : [rapport de la source 53](G:/projets/atelier-3d/work/garment-automation-v1/program-native-full-source-quality-investigation-v1/report.json), SHA-256 `f9b2016f3d0e36fd39c23523011058bb53519ee3f80c53e6df76f28f3067933d`.

`blender/sewing.py` calcule désormais au plus trois propositions par face refusée :

1. Lorsque le plus court côté est un segment du contour contraint, l’apex équilatéral tourné vers l’intérieur de la face est essayé en premier.
2. Le circoncentre n’est proposé que s’il appartient à sa face incidente. Pour un côté non contraint, il garde la priorité lorsqu’il est admissible.
3. Le centroïde de la face constitue la dernière proposition.

Toutes les propositions sont calculées depuis la géométrie matérielle courante. Dans le parcours régulier, les coordonnées exactes des arrêts source ont déjà été restaurées. Le calcul du circoncentre utilise un repère translaté à une extrémité du côté court afin de réduire les soustractions de carrés de grandes coordonnées absolues.

La proposition est convertie en vecteur Blender, puis ses coordonnées représentables sont de nouveau contrôlées dans la face et dans le patron. Une proposition en double précision située dans la face peut sortir de celle-ci après conversion en float32 ; ce cas est refusé avant transmission au CDT. Au plus une proposition admissible est ajoutée pour une face pendant une passe.

## Contrôles et budgets conservés

La séparation reste `max(min_edge_cm, 0,2 × longueur_du_côté_court)`. Elle s’applique aux points déjà présents, aux insertions de la passe et au contour. Une proposition trop proche est refusée ; aucun espacement n’a été diminué et aucun point existant n’est déplacé pour lui faire une place.

Le nombre de passes, le nombre de sommets ajoutés et le budget total de sommets restent ceux de la recette existante. Les propositions supplémentaires représentent un coût constant borné par face ; elles n’ajoutent ni passe ni essai CDT. Le lissage intérieur borné, la restauration exacte des arrêts source, la comparaison du candidat conditionné au meilleur candidat et le retour complet au meilleur candidat restent en place.

L’admission finale est toujours recalculée sur les coordonnées matérielles exactement retournées. Pour le profil régulier courant, la limite reste `15°` avec des arêtes d’au moins `0,001 cm`. La limite plus permissive d’une recette de construction ne remplace pas ce contrôle régulier. Une impossibilité locale, une absence de point admissible, un budget épuisé ou une dégradation du meilleur candidat donnent toujours `NEEDS_CORRECTION` avec la raison correspondante.

## Vérification et portée

Les 23 tests ciblés exécutés couvrent les dix nouveaux cas de proposition et les treize tests existants du conditionnement et du lissage intérieur. Ils vérifient notamment le témoin matériel décalé, les deux orientations, la translation, le circoncentre dans ou hors de la face, la densité des points, la conversion float32 qui sort de la face, les budgets, un vrai angle source aigu, le refus `REFINEMENT_STALLED`, la répétabilité et la conservation exacte des coins source.

Ces tests utilisent une doublure de transport float32 et des sorties CDT contrôlées. Ils ne qualifient pas le triangulateur natif ni le vêtement. Le prochain contrôle minimal est un essai Blender isolé sur un contour à intervalle court protégé, suivi de la mesure des préparations régulières des dix pièces du manteau original et de la variante de manches acceptée. Le coordinateur exécute les essais natifs sur le code gelé. Aucune mesure corporelle, preuve de fitting, simulation Cloth, revue artistique ou autorisation Blender n’est accordée par ce raffinement.
