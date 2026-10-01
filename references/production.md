# Contrat de production

Le plugin possède son propre runtime et ses contrats. Le serveur MCP studio fournit les opérations métier. Pour les opérations ComfyUI, il invoque une installation externe de Comfy-Org/comfy-mcp en stdio ; celle-ci utilise comfy-cli. Blender MCP est une dépendance externe que Codex appelle directement.

Le projet actif est extrait sous .a3d. SQLite state.sqlite3 est canonique ; project.json est un snapshot lisible. Ne pas modifier ce snapshot pour forcer un état. Les originaux, preuves, packages et sorties restent sous le project_root demandé.

Ordre normal : INIT → SPECIFIED → REFERENCES_GENERATING (facultatif) → REFERENCES_READY → REFERENCES_APPROVED → ANALYZED → ROUTED → PACKAGED → RECONSTRUCTING → RECONSTRUCTED → ASSEMBLING → REFINING → BEHAVIOR_AUTHORING → VALIDATING → COMPLETE. Chaque transition nécessite un fichier de preuve enregistré. BLOCKED et FAILED conservent l'étape de reprise, avec raison documentée.

Les gates portent les noms references, route.<component_id>, construction, assembly, silhouette et final. studio_record_human_decision enregistre la déclaration réelle et la référence du message utilisateur ; ce stockage ne prouve pas à lui seul l'authenticité de la déclaration. Ne pas inventer de réponse. La décision final doit inclure final-validation. Une preuve modifiée invalide la décision qui la référençait.

Le schéma d'asset fixe les composants au début. Une nouvelle conception ou révision d'un composant déjà validé demande un nouveau projet/révision conservant l'ancien. Le runtime privilégie l'historique explicite à la réécriture silencieuse des résultats.

Le CLI expose les mêmes outils : python scripts/studio.py tools ; python scripts/studio.py call NOM --arguments arguments.json. Tous les chemins de payload sont relatifs au project_root, utilisent / et restent à l'intérieur de celui-ci.

Depuis 0.2.0, toutes les routes nécessitent une proposition enregistrée et revue. Entre PACKAGED et RECONSTRUCTING, produire puis faire approuver le board de découpage via le gate `construction` lié à `construction-board`. Voir [la revue de construction](construction-review.md). Les anciennes preuves générales ne remplacent pas cette revue.

Depuis 0.3.0, chaque jalon de production exige ses preuves spécialisées : lire [les contrôles du cycle complet](lifecycle-guards.md). Le passage entre étapes ne peut plus être justifié par le seul brief.
