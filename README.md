# Atelier 3D

[![CI](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml/badge.svg)](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plugin Codex pour préparer et produire des assets 3D à partir d’images de référence,
avec un choix de méthode par composant, des données de construction explicites et
une validation humaine aux étapes déterminantes.

## Démarrer

Le profil d’installation cible **Windows**, avec **Python 3.11+**. ComfyUI,
son MCP officiel, Blender et son MCP s’installent séparément. La vue éclatée
textile nécessite Codex Image dans la conversation.

1. Suivre [l’installation et la configuration](references/getting-started.md).
   Cloner le dépôt ou télécharger un ZIP n’installe pas le plugin dans Codex.
2. Sélectionner `@Atelier 3D`, joindre les références et choisir un dossier
   d’asset distinct du code du plugin.
3. Examiner la méthode et le board de découpage avant de lancer la construction.
   Le guide contient [un exemple de brief](references/getting-started.md#exemple-de-brief).

## Parcours disponibles

| Méthode | Usage |
| --- | --- |
| `PATTERN_SEWN` | Vêtements et composants textiles issus de patrons approuvés |
| `MULTIVIEW_PART` | Pièces volumiques reconstruites séparément depuis des vues cohérentes |

Un asset peut combiner les deux méthodes. Le plugin organise les packages,
jobs ComfyUI, opérations Blender, preuves et checkpoints. Les
[fonctionnalités et limites](references/capabilities.md) détaillent ces parcours.
Avant d’exécuter du code via Blender MCP, il demande l’autorisation de l’utilisateur ;
cette consigne ne modifie pas les permissions MCP de Codex.

## Documentation

- [Index thématique de tous les guides](references/index.md)
- [Installation, mise à jour et premier projet](references/getting-started.md)
- [Production et validations humaines](references/production.md)
- [Classification des vêtements et aisance explicite](references/garment-fit-intent.md)
- [Patronage : mensurations, mise à taille et comparaisons calculées](references/patronage-agent.md)
- [Placement anatomique générique : guides, coutures et couverture des régions](references/generic-anatomical-placement.md)
- [Automatisation : runtime et interfaces](references/automation-runtime.md), [preuves et qualification](references/automation-validation.md)
- [Templates ComfyUI réutilisables](workflows/comfy/README.md)
- [Architecture et responsabilités](references/architecture.md)
- [Résultats des validations et limites de qualification](VALIDATION.md)
- [Historique des changements](CHANGELOG.md) et [notes des essais par version](references/version-notes.md)
- [Contribution](CONTRIBUTING.md), [sécurité](SECURITY.md) et [maintenance du dépôt](references/repository-maintenance.md)

## État et limites

Les manifestes du checkout indiquent **0.7.0-rc.2**, préversion textile. Le runtime, ses contrats et le
profil d’installation Windows ont des vérifications documentées dans
[VALIDATION.md](VALIDATION.md). Une production complète sur un vêtement réel
ou un asset articulé reste à qualifier. Les contrôles numériques ne remplacent
pas la comparaison visuelle ni l’acceptation humaine.

Cette préversion ajoute un catalogue hors ligne de deux mannequins réalistes CC0,
un planificateur de montage et des guides sémantiques. Le fitting complet reste
non qualifié ; voir [les capacités et limites de la préversion](references/garment-automation.md).

Les templates ComfyUI fournis restent à qualifier sur les nœuds et modèles de
l’installation cible. Aucun modèle n’est téléchargé automatiquement. Le paquet
portable contient le plugin, ses références et les deux bases CC0 vérifiées du
[catalogue](assets/mannequins/catalog.json). Les autres scènes et modèles,
configurations locales et sorties de production sont exclus.

## Licence

Le code et la documentation sont sous [licence MIT](LICENSE).
Les moteurs, modèles, références fournis par l’utilisateur et assets produits
conservent leurs propres droits et conditions. Les deux bases distribuées sont
décrites dans [la notice CC0](assets/mannequins/NOTICE-CC0.md).
