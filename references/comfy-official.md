# Comfy MCP officiel local

Les bases réutilisables et leurs exemples de paramètres sont répertoriés dans
[le catalogue des templates ComfyUI](../workflows/comfy/README.md).

Studio réutilise des graphes au format API enregistrés dans
`workflows/comfy/registry.json`. Il applique leurs paramètres déclarés ; chaque
job conserve son graphe exact et son empreinte. Un changement de structure ou
l'ajout d'un workflow externe passe par une variante revue et enregistrée, avec
provenance et cibles de paramètres vérifiées. Le catalogue distingue les bases
enregistrées de leur compatibilité native et de leur qualification visuelle.

Décision d'architecture : utiliser https://github.com/Comfy-Org/comfy-mcp et ses outils existants. Aucun client HTTP ComfyUI n'est livré. Le MCP studio ajoute les contrôles métier avant d'appeler le fournisseur officiel. Aucune copie de son code n'est incluse dans la distribution.

L'installation est une étape séparée. Prévoir comfy-mcp et comfy-cli compatibles, idéalement dans un environnement dédié. La connexion de développement a été vérifiée avec comfy-mcp 0.10.0 et comfy-cli 1.22.0 ; consulter les prérequis du fournisseur avant une nouvelle installation. Le runtime du plugin utilise uniquement la bibliothèque standard Python >= 3.11. Configurer mcp_command et cli_command avec leurs exécutables absolus si le PATH de Codex ne les trouve pas. Ne pas réinstaller le ComfyUI existant.

Le plugin cible le ComfyUI HTTP local configuré (défaut http://127.0.0.1:8188). L'adaptateur fixe COMFY_LOCAL_URL pour que découverte, validation et exécution visent le même serveur. Il ne propose pas de mode cloud ni de redirection distante. Les appels run_workflow utilisent wait=false et confirm_spend=false. Une installation manquante est UNAVAILABLE ; elle n'est jamais téléchargée au démarrage.

Correspondances :

| Opération Studio | Outil officiel |
| --- | --- |
| comfy_health | server_info |
| comfy_capabilities | tools/list, nodes(action=list), search_models |
| comfy_validate_workflow | validate_workflow(workflow_path) |
| comfy_upload_image / mask | upload_file(paths, overwrite=false) |
| comfy_submit_workflow / run_template | run_workflow(workflow_path, wait=false, confirm_spend=false) |
| comfy_job_status | job(action=status, prompt_id) |
| comfy_job_outputs | fetch_outputs(prompt_id, out_dir) |

Les masks sont des fichiers PNG distincts ; le plugin ne fusionne pas automatiquement leur canal alpha avec une image d'origine. Le workflow doit exprimer comment les utiliser.

L'annulation est une limite explicite : le code actuel de comfy-cli peut utiliser /interrupt global après lecture de la file. comfy_cancel_job renvoie donc une demande de revue native, sans interrompre un autre travail. Le superviseur Codex peut utiliser le MCP natif après avoir vérifié et expliqué la portée réelle de l'annulation.

Un timeout après soumission conserve submission_unknown et interdit un deuxième envoi. Le workflow et son préfixe de sortie unique restent enregistrés. Une récupération sans prompt_id demande une vérification native et une réconciliation explicite ; aucune correspondance n'est devinée.

Sources consultées le 30 septembre 2026 : https://docs.comfy.org/agent-tools/mcp ; README et signatures de src/comfy_mcp/server.py ; contrats upload et jobs de Comfy-Org/comfy-cli. Le fournisseur est en évolution : refaire le test réel à l'installation.


Le budget max_parallel_jobs vérifie la file connue du MCP natif juste avant l'envoi. Le projet n'admet qu'un job actif ou incertain à la fois. Ce contrôle est une admission instantanée, pas un verrou global entre applications : une soumission concurrente extérieure reste possible.

La validation native a des limites documentées : champs obligatoires manquants, sous-champs dynamiques et estimation VRAM. Elle ne prouve ni la fidélité des vues ni la qualité du mesh. Les templates fournis sont des bases explicites à qualifier avec les nœuds et modèles réellement installés. La découverte des modèles renvoie les dossiers ; le MCP natif permet d'en examiner ensuite le contenu.
