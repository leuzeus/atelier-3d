---
name: assemble-in-blender
description: Assembler dans une copie Blender des reconstructions 3D indépendantes ou des panneaux cousus, en conservant leurs articulations.
---

# assemble-in-blender

Lire [le protocole Blender](../../references/blender.md). Utiliser le MCP Blender officiel déjà connecté. Demander le code exact à `studio_blender_operation` puis le transmettre tel quel à l'outil Python Blender ; le dispatcher vérifie à nouveau les prérequis. `prepare` crée une copie sans écraser l'original. Vérifier la scène connectée. Après approbation humaine du board de découpage, `garment` construit les panneaux issus du package approuvé. Pour l'assemblage, faire approuver les relations critiques puis appeler `assemble`. Le mannequin de collision et la simulation restent un travail de scène explicite et traçable. Ne jamais substituer des tubes/surfaces procédurales à PATTERN_SEWN. Ne jamais souder des composants must_remain_separate. Inspecter les pixels avant toute conclusion.

Enregistrer et faire approuver assembly-plan, avec tous les composants, leurs sorties acceptées et les hashes du fichier de travail/checkpoint. Utiliser mode=existing pour les panneaux cousus déjà construits, mode=import pour les fichiers de parties. L’opération produit assembly-result nécessaire à REFINING. Après erreur, utiliser restore_checkpoint avant une nouvelle mutation. Voir les [contrôles des étapes](../../references/lifecycle-guards.md).

Pour PATTERN_SEWN, suivre [la recette native de toile](../../references/sewn-toile.md) après approbation du board : contours source conservés, maillage dérivé, mannequin auxiliaire vérifié, essais gravité/couture/contact puis sous-ensemble local, simulation complète bornée et consolidation des seules coutures permanentes. Préparer les données techniques pour l’utilisateur ; ne pas lui imposer un nouveau formulaire ni faire réapprouver un board inchangé pour ajuster la physique. Après deux échecs complets, diagnostiquer le petit cas et refaire l’essai local. Examiner les rendus avant toute conclusion artistique.
