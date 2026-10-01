# Maintenance du dépôt public

## Protections de base

La configuration visée pour `leuzeus/atelier-3d` est la suivante. La présence de
ce fichier ne suffit pas : vérifier les réglages GitHub après toute recréation.

| Contrôle | Configuration |
| --- | --- |
| Branche par défaut | `main` |
| Intégrité de `main` | Suppression et force-push interdits |
| Fusion | Pull request et CI Windows/Linux réussie ; conversations résolues |
| Revue | 0 approbation externe obligatoire, adapté à un mainteneur seul |
| Historique | Fusion squash, suppression de la branche fusionnée |
| Actions | Permissions par défaut en lecture ; approbation de PR par workflows désactivée |
| Actions tierces | Actions officielles GitHub autorisées ; dépendances de workflows épinglées à des SHA |
| Secrets | Secret scanning et push protection activés |
| Dépendances | Alertes Dependabot, correctifs de sécurité et mise à jour hebdomadaire des actions |
| Signalements | Rapports de vulnérabilité privés activés |

Les paramètres de règles sont contrôlables par le propriétaire du dépôt.
Les règles protègent les opérations ordinaires ; elles ne rendent pas le compte
administrateur immuable. Aucun secret de déploiement ou runner personnel n'est
nécessaire pour cette CI. Les PR externes n'ont pas de jeton en écriture ; ne pas
remplacer l'événement `pull_request` par `pull_request_target` pour exécuter leur code.

Les alertes de dépendances ne garantissent pas l'inventaire des installations
externes Comfy, Blender et modèles. Studio n'a actuellement aucune dépendance
Python tierce ; le fichier Dependabot suit les actions GitHub.

## Avant de publier une nouvelle version

1. Revoir les fichiers ajoutés et les diffs : aucune référence privée, configuration,
   scène, capture d'écran personnelle, identité locale ou clé dans Git.
2. Exécuter les tests concernés et la suite requise par la CI ; distinguer les
   essais logiciels des essais natifs et artistiques.
3. Mettre à jour les versions de `pyproject.toml`, `plugin.json` et
   `.codex-plugin/plugin.json`, puis l'historique et la documentation affectée.
4. Construire une nouvelle archive avec `scripts/package_plugin.py`. Examiner son
   inventaire et vérifier les empreintes avant publication. Les archives sous
   `work/` et les marketplaces `.local/` ne sont jamais des sources à ajouter à Git.
5. Ouvrir une PR, laisser réussir la CI, puis fusionner. Vérifier le commit distant
   et les règles actives. Une publication de release/marketplace est une action
   distincte de la mise à jour du dépôt.

Les rapports locaux historiques référencés dans la documentation ne sont pas des
artefacts publics. Préférer les logs CI du commit exact pour les tests reproductibles.

## Références du fournisseur

- [Règles de dépôt](https://docs.github.com/en/rest/repos/rules)
- [Réglages de sécurité du dépôt](https://docs.github.com/en/rest/repos/repos)
- [Permissions GitHub Actions](https://docs.github.com/en/rest/actions/permissions)
