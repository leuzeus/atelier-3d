# Packages

Les .partpkg et .garmentpkg sont des ZIP immuables avec manifest.json et hashes SHA-256 de tous les fichiers. Les membres sont JSON, PNG et SVG ; pas de scripts ni de secrets. Le validateur refuse traversées de chemins, doublons, collisions de casse, liens, archives trop volumineuses, checksum manquant et fichiers changés.

Les unités sont cm, Z up, avant -Y, repère droit. Les caméras et anchors sont explicites. Les fichiers de référence clean doivent être des PNG dont les dimensions correspondent au contrat. Les overlays et masks ne deviennent pas des entrées de reconstruction implicites.

Pour les patrons, les polygones SVG et la liste vertices de garment.json correspondent exactement. Les faces doivent être décrites pour obtenir un maillage de simulation utile ; le plugin ne fabrique pas un patron de couture fiable à partir d'une illustration. Les bords de couture relient des panneaux distincts et ont un échantillonnage de même longueur.

Les fixtures assassin-garment et articulated-skeleton vérifient les contrats et les invariants. Elles sont synthétiques et ne démontrent ni qualité de reconstruction ni simulation d'un vêtement réel.
