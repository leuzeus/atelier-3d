# Validation du cadrage et des diagnostics 0.5.4

Essais du 1er octobre 2026 sous Windows, Blender 5.2.2 LTS
(`d13f752e3b9c`). **185 tests Python réussis**, huit contrats distribués et
configuration locale privée vérifiés avec PowerShell Test-Json.

`tests/native_viewport_smoke.py` utilise un projet synthétique et une instance
Blender isolée. Il construit une toile depuis les données approuvées de test,
demande le code exact au Studio et l'exécute par le bootstrap courant. Cadrage
ORTHO puis PERSP, sélection/objet actif/orientation/projection conservés,
géométrie/transforms et fichiers du projet inchangés. Il refuse mesh étranger,
nom absent, package erroné, mesh masqué, sélection interdite, archive, caméra,
verrou, mode édition et scène étrangère. Le rendu de viewport OpenGL provient
de cette fixture ; il ne s'agit pas d'une image du vêtement consommateur.

`tests/native_sewing_failure_smoke.py` prépare une fixture de buste/manche avec
partenaires délibérément trop éloignés, puis lance réellement les probes et
32 frames de Cloth local. Le contrôle `mesh_quality` refuse le résultat évalué.
Les positions, arêtes hors limites, coutures, indices globaux et contexte sont
conservés avant suppression de l'objet local. L'inspection confirme FAIL, aucun
reçu local PASS n'est créé, le mesh original et les gates sont conservés et
la production full demeure refusée. Après `restore_checkpoint`, le même
diagnostic et son tracé restent vérifiables ; l'original reste intact.

`tests/native_sewing_smoke.py` repasse aussi le parcours précédent : probes
gravité/couture/contact à deux densités, essais local et full, refus des dérives,
circuit de retry, consolidation des coutures permanentes et maintien des liens
amovibles. Aucune donnée consommateur n'est utilisée par ces tests.

Le diagnostic de pénétration utilise la proximité signée du collider, comme
le contrôle existant. Le SVG est une projection de coordonnées mesurées, sans
matières, image générée ou nouvelle approbation. Les tentatives antérieures sans
positions conservées restent incomplètes ; leurs résultats ne sont pas inventés.

Le retest réel du cadrage et de la collecte après réinstallation reste distinct.
Cette version ne qualifie ni la silhouette, ni le drapé complet du manteau, ni
l'import Unreal. La sélection d'une région spatiale avec nouveaux supports
temporaires n'est pas implémentée sans diagnostic et mapping propres à l'asset.
