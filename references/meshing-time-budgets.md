# Durée explicite du maillage synchronisé

`meshing_profile.budgets.max_seconds` déclare le budget de calcul du maillage
d'un composant complet. La plage supportée est de 0,001 à 600 secondes. Les
entrées existantes à 90 secondes et le défaut de `MeshingEnvelope` restent
inchangés. La durée choisie figure dans la préparation, son empreinte et le
run ; elle doit être présentée dans l'autorisation native exacte.

Cette durée est une limite de ressources. Les seuils d'angle et de longueur,
les correspondances source, le nombre de sommets, les passes, les insertions,
les contrôles de déplacement et les compteurs de travail restent indépendants.
Un budget plus long n'accorde aucun PASS de géométrie, Cloth ou fitting.

Tous les panneaux partagent la même origine de temps. La deadline n'est pas
réinitialisée entre panneaux, remeshes ou rollbacks. Le contrôle coopératif
refuse à la deadline exacte et conserve le travail tenté. Un appel natif qui
ne rend pas la main ne devient pas préemptif du seul fait de ce budget.
Un calcul interrompu n'a pas d'observation terminale complète et reste non admis.

Pour préparer une durée différente, créer des entrées séparées avec le service
générique `prepare_profile` ou `prepare_recovery_profile`. Conserver les sources,
le corps, la recette et les autres paramètres. Vérifier le diff, l'enveloppe
de travail et le budget du run. Le runtime chargé doit supporter la plage
proposée avant de créer une nouvelle identité de run. Une ancienne tentative
ne doit pas être réécrite pour augmenter son budget après son refus.

Le délai de transport MCP reste distinct : sur l'installation examinée, il
est de 300 secondes pour `execute_blender_code`. Un maillage budgété à
300 secondes peut laisser l'opération totale dépasser ce délai, puisqu'elle
comprend aussi admission, préparation, contrôles, sauvegarde et rendu.
Après une réponse incertaine, conserver la tentative et réconcilier le reçu
natif réel avec `studio_next_run_step` ; ne pas envoyer un deuxième calcul.

Le cas de qualification du vêtement conserve un fichier séparé proposant
300 secondes. Il est non exécuté et ne démontre pas que cette durée suffira.
Les [preuves de progression et de contrat](automation-meshing-budget-expansion-evidence-20261007.json)
conservent cette distinction.
