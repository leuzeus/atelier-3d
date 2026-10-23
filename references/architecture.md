# Architecture du plugin

Les **11 skills** guident Codex ; le serveur Studio expose **32 outils MCP** et
utilise **25 schémas JSON**. L'état canonique du projet est conservé dans SQLite
sous `.a3d`, avec les preuves et décisions. Les fichiers `.partpkg` et
`.garmentpkg` sont des archives de transport contrôlées.

Studio appelle le [MCP officiel Comfy local](https://docs.comfy.org/agent-tools/mcp)
via stdio. Codex transmet les opérations préparées par Studio au MCP Blender.
Le plugin fournit les contrôles métier et le code d'opérations, sans embarquer
ces moteurs. Deux bases anatomiques CC0 vérifiées sont distribuées
dans le catalogue hors ligne ; les modèles ComfyUI restent externes. Codex et Codex Image restent des services externes ;
le terme « local » décrit Studio, les fichiers de projet et l'adaptateur Comfy.

| Dossier | Responsabilité |
| --- | --- |
| `a3d`, `servers/studio` | État, contrats, admission, packages, jobs et MCP |
| `blender`, `hooks` | Opérations contrôlées, checkpoints et contexte de session |
| `skills`, `references` | Parcours de travail et documentation |
| `schemas`, `templates`, `workflows` | Contrats, dossier type et graphes Comfy à qualifier |
| `tests` | Tests de contrats/protocoles et données synthétiques |

[Retour à la documentation](index.md).
