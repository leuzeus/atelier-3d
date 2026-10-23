# Rejet exact des intersections UV séparées

La fonction privée `material_sample_carrier._clip` refuse de calculer une intersection lorsque les intervalles de coordonnées des deux polygones sont **strictement disjoints sur au moins un axe**. Les comparaisons utilisent les coordonnées rationnelles exactes déjà préparées par les callers. Aucun epsilon, arrondi, conversion IEEE, nouvelle coordonnée ou drapeau de confiance n'est utilisé.

La condition `max(A.axis) < min(B.axis)` ou son inverse prouve que l'intersection est vide. **Une égalité garde le clipping historique**, afin de conserver les contacts par arête ou sommet. Les autres intersections suivent le même calcul, dans le même ordre, avec la même limite de précision. Un contrôle de délai précède les bornes ; un autre précède chaque retour, y compris le retour du chemin historique.

Les callers continuent de débiter chaque `pair_checks` avant `_clip`. Les caps, contrats publics, identités matérielles, coordonnées source, relations et validations `_number/_mesh` restent inchangés. Le raccourci n'est pas une qualification de domaine ou de vêtement ; il donne seulement une preuve locale d'intersection vide.

Une différence bornée de refus est intentionnelle : le clipping historique pouvait dépasser le plafond de précision sur une intersection intermédiaire avant de découvrir que les polygones étaient disjoints. Le nouveau chemin peut alors renvoyer `[]` sans créer cette intersection inutile. Les coordonnées d'entrée restent contrôlées et les intersections réellement calculées conservent leur plafond de **4 096 bits**. L'équivalence de tous les refus historiques n'est donc pas revendiquée.

Les tests couvrent séparation dans les deux directions, boîtes tangentes, contacts par arête/sommet, recouvrement rationnel, deux windings, séparation perdue par un cast IEEE, grandes translations, immutabilité, précision d'entrée/intersection, budgets de paires et délais. Une comparaison portable conserve le noyau historique, vérifie les sorties géométriques admises et mesure les appels arithmétiques évités sur des fixtures synthétiques.

Le SHA du module UV change. Les champs compilés incluent ce SHA dans `compiler_code` ; un reçu historique doit être refusé par l'observateur actuel et un nouveau champ compilé avec la nouvelle identité. Le module champ n'est pas modifié. Les temps de fixtures ne démontrent ni gain de performance produit, ni achèvement du col sous 60 s, ni Cloth, fitting ou acceptation artistique.
