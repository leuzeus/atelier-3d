# Packages

Les .partpkg et .garmentpkg sont des ZIP immuables avec manifest.json et hashes SHA-256 de tous les fichiers. Les membres sont JSON, PNG et SVG ; pas de scripts ni de secrets. Le validateur refuse traversées de chemins, doublons, collisions de casse, liens, archives trop volumineuses, checksum manquant et fichiers changés.

Les unités sont cm, Z up, avant -Y, repère droit. Les caméras et anchors sont explicites. Les fichiers de référence clean doivent être des PNG dont les dimensions correspondent au contrat. Les overlays et masks ne deviennent pas des entrées de reconstruction implicites.

Pour les patrons, les polygones SVG et la liste vertices de garment.json correspondent exactement. Les faces source restent décrites, mais le maillage de simulation est dérivé à une densité indépendante. Le plugin ne fabrique pas un patron fiable à partir d'une illustration. Les bords nommés suivent le contour sans sauter de segment. Ils peuvent avoir des nombres de points différents : la recette établit les paires par longueur d'arc. Une couture sur deux bords distincts d'un même panneau est admise. Déclarer `kind` (`permanent`, `closure`, `detachable`) dans les nouveaux packages. Voir [la recette de toile](sewn-toile.md).

Les fixtures assassin-garment et articulated-skeleton vérifient les contrats et les invariants. Elles sont synthétiques et ne démontrent ni qualité de reconstruction ni simulation d'un vêtement réel.
