# Validation selon destination

La validation conserve séparément : contrôles déterministes, contrôles dans Blender, comparaison visuelle, acceptation humaine. Un outil terminé avec succès ne remplace pas les trois autres.

Contrôles communs : geometry, scale, orientation, separation, visual. Animation ajoute rig, weighting, clearance ; game ajoute budget, uv, materials, target_import, ainsi que rig, weighting, clearance si l'asset a des composants cousus ou articulés ; 3d_print ajoute manifold, thickness ; render ajoute materials. `asset.required_checks` permet d'ajouter les contrôles spécifiques décidés au brief. Chaque contrôle requis doit être PASS pour COMPLETE, avec son fichier exact dans check_evidence. NOT_EXECUTED, SKIP, FAIL et INCONCLUSIVE ne valent pas PASS.

L'inspection automatique de Blender fournit des métriques de départ ; le rapport final doit être rédigé à partir de tests effectifs. Ouvrir les images de comparaison, tester les articulations et enregistrer les preuves. L'acceptation humaine finale porte sur final-validation ET le manifeste visual-review référencé par visual_review_evidence, avec les fichiers exacts livrés. Pour Unreal, target_import documente un import réellement testé dans le moteur ; un export FBX réussi ne suffit pas. Voir les [contrats de jalons](lifecycle-guards.md).

Un .blend absent, une génération non exécutée ou un backend non connecté doit apparaître comme tel dans le bilan, sans transformer un problème d'orchestration en échec du modèle 3D.
