# Documentation d’Atelier 3D

Le [README](../README.md) présente le plugin. Cet index donne accès aux guides
par sujet, sans imposer de lire les comptes rendus historiques pour démarrer.

Les guides décrivent les parcours et contrats ; [VALIDATION.md](../VALIDATION.md)
décrit la portée des vérifications. Les notes de versions et reçus historiques
conservent le contexte de leurs essais et ne qualifient pas un nouvel asset.
L’état canonique d’un projet de production reste sa base SQLite `.a3d`, comme
le précise le [contrat de production](production.md).

## Démarrer et comprendre

- [Installation, configuration, mise à jour et premier projet](getting-started.md)
- [Fonctionnalités, méthodes et limites](capabilities.md)
- [Architecture et responsabilités des dossiers](architecture.md)
- [Déroulement et état du projet](production.md)
- [Contrôles des étapes et récupération](lifecycle-guards.md)

## Références, méthode et fabrication

- [Préparer les références visuelles](references-3d.md)
- [Proposer la méthode et revoir le découpage](construction-review.md)
- [Board textile et patrons de fabrication](fabrication-board.md)
- [Contrats des packages](packages.md)
- [Templates ComfyUI : usages, paramètres et réutilisation](../workflows/comfy/README.md)
- [Intégration du MCP officiel ComfyUI](comfy-official.md)

## Préversion textile 0.7.0-rc.2

- [Automatisation : capacités, preuves et limites de développement](garment-automation.md)
- [Mensurations : contrôles existants et travaux restant à réaliser](mannequin-measurements.md)
- [Catalogue hors ligne des deux bases réalistes](../assets/mannequins/catalog.json)
- [Provenance et licence CC0](../assets/mannequins/NOTICE-CC0.md)

## Blender et préparation textile

- [Protocole Blender et autorisation du code](blender.md)
- [Continuité native, checkpoints et reprise](blender-continuity.md)
- [Choisir explicitement le corps source](body-source.md)
- [Dimensionner et mesurer le mannequin pour le vêtement](garment-body-target.md)
- [Préparation native des patrons](pattern-preparation.md)
- [Assemblage depuis les patrons approuvés](pattern-assembly.md)
- [Du board à la toile cousue](sewn-toile.md)
- [Montage par étapes et transfert des résultats locaux](sewn-stages.md)
- [Préparation et montage des interfaces locales](local-interfaces.md)
- [Prépositionnement expérimental borné](experimental-prefit.md)
- [Renforcements après l’étude OpenSew](opensew-improvements.md)

## Fitting et diagnostics

- [Classification du vêtement et aisance explicite](garment-fit-intent.md)
- [Variantes de patrons calculées et contraintes conservées](pattern-ease-variants.md)
- [Suivi de la correction d’aisance du 4 octobre 2026](automation-ease-followup-20261004.md)
- [Reçu des contrôles logiciels et observations d’aisance](automation-ease-evidence-20261004.json)
- [Sections de peau des bras et enveloppes de passage des mains](body-region-sections.md)
- [Préparation des régions et capacités nominales des manches](limb-source-measurements.md)
- [Reprise dans une scène vide et fitting séparé](clean-construction-fitting.md)
- [Préparation native du fitting](fitting-preparation.md)
- [Fiche de fitting mesurée](measured-fitting.md)
- [Prépositionnement et écarts des coutures](sewing-placement.md)
- [Couplage des guides par leurs coutures source](source-seam-coupling.md)
- [Reçu des contrôles de couplage et de conservation des coins](automation-source-coupling-evidence-20261004.json)
- [Déplacements pendant Cloth](cloth-motion.md)
- [Diagnostic des probes physiques](probe-diagnostics.md)
- [Candidats refusés avant Cloth](garment-rejections.md)
- [Cadrage et diagnostics conservés après échec](viewport-diagnostics.md)
- [Reprise après refus : choix utilisateur et correction ciblée](preparation-recovery.md)
- [Complétude locale et globale des pièces](piece-completeness.md)
- [Signalement de complétude du 3 octobre 2026](../BUG-2026-10-03-completude-pieces-blender.md)

## Validation et historique

- [Résultats et limites de qualification](../VALIDATION.md)
- [Contrat de validation d’un asset](validation.md)
- [Historique des changements](../CHANGELOG.md)
- [Notes des essais par version, extraites du README](version-notes.md)
- [Validation du pipeline 0.2.0](validation-pipeline-0.2.0.md)
- [Validation du cycle 0.3.0](validation-lifecycle-0.3.0.md)
- [Validation du board 0.4.0](validation-fabrication-0.4.0.md)
- [Validation de la couture 0.5.0](validation-sewing-0.5.0.md)
- [Validation de la continuité 0.5.2](validation-continuity-0.5.2.md)
- [Validation des reçus 0.5.3](validation-receipts-0.5.3.md)
- [Validation du cadrage 0.5.4](validation-viewport-0.5.4.md)
- [Validation du placement 0.5.5](validation-placement-0.5.5.md)

## Développer et maintenir

- [Contribution et vérifications de développement](../CONTRIBUTING.md)
- [Sécurité et signalement privé](../SECURITY.md)
- [Maintenance du dépôt, publication et installation](repository-maintenance.md)
- [Fixtures de tests et portée synthétique](../tests/fixtures/README.md)

[Retour à la présentation du plugin](../README.md).
