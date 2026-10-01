# Audit et renforcement des autres étapes — Atelier 3D 0.3.0

Date : 1 octobre 2026. Source : checkout de développement du plugin. L'audit prolonge le contrôle de pipeline/board 0.2.0. Les corrections sont dans le projet source et son runtime, avec les instructions correspondantes dans les skills.

Les journaux et artefacts `work/` cités ci-dessous sont locaux et ne sont pas distribués. Voir [la validation actuelle](../VALIDATION.md) et la CI publique pour les contrôles reproductibles.

## Écarts constatés et corrigés

| Étape | Écart antérieur | Contrôle livré |
| --- | --- | --- |
| Références Comfy | Template SD1.5 alimenté seulement par texte | Source originale enregistrée/uploadée obligatoire, encodée par le graphe et conservée dans le job |
| Reconstruction | Labels PASS et hash de sortie, preuves des contrôles non liées | Fichiers check_evidence et revue visuelle liés à la sortie ; relecture des preuves acceptées avant assemblage ; remplacement silencieux refusé |
| Assemblage | Approbation générale et couverture partielle possibles | Gate lié à assembly-plan, couverture exacte des composants, sorties acceptées, scène et checkpoint identifiés ; mode existing pour les panneaux déjà cousus |
| Finition | Transition sans reçu d'assemblage exploitable | Reçu lié au plan, checkpoint et copie immuable ; rapport de finition et revue silhouette exigés avant comportements |
| Comportements / simulation | Contrat de simulation inutilisé, validation des déformations peu imposée | Intervalle, budget et collisions vérifiés ; rig/weighting/clearance sur le candidat courant avant validation lorsque requis |
| Livraison | Mention de preuve visuelle sans lecture de son contenu ; profil jeu incomplet pour un vêtement | Revue visuelle structurée et approuvée avec tous les livrables ; fichiers de preuves rehashés ; import moteur obligatoire et contrôles de déformation adaptés |
| Erreur Blender / reprise | Mutation partielle possible sans verrou de poursuite | Opération en cours persistée, checkpoint, blocage après exception/interruption, restauration dans une nouvelle copie et invalidation du reçu d'assemblage restauré |
| Suivi Comfy | Statut failed mal normalisé, poll tardif susceptible de déclasser une pièce acceptée | failed explicite ; une reconstruction déjà acceptée conserve son état |
| Diagnostic | Préflight centré sur le board | État d'opération interrompue exposé et prérequis de l'étape courante revérifiés |

## PASS

- Suite complète : **113 tests**, aucune erreur, aucun échec, aucun saut (`work/lifecycle-tests.log`). Inclut les six hooks sous cmd.exe et PowerShell, le protocole MCP, les packages, les contrats, les refus et les parcours autorisés.
- Après les derniers ajustements du diagnostic et des fixtures : **64 tests ciblés** (`work/lifecycle-targeted-final.log`), puis **51 tests** des preuves et de la progression (`work/lifecycle-evidence-final.log`) passent. Aucun test antérieur supprimé.
- Parcours synthétique de la machine d'état jusqu'à COMPLETE avec les preuves spécialisées ; refus pour contrôles incomplets, candidat différent, références/preuves/images modifiées, mauvais plan, absence de reçu ou de revue humaine requise.
- Blender **5.2.2 LTS**, en processus indépendant avec scène vide : import OBJ de 3 sommets ; panneaux cousus de 16 sommets conservés sans duplication par mode existing ; intervalle Cloth appliqué sans bake.
- Pour les deux parcours Blender : erreur provoquée après reçu d'assemblage, reçu invalidé à la restauration, réassemblage réussi ; erreur de script après mutation, poursuite refusée, récupération réussie et opération suivante réussie. Les originaux restent identiques et les copies d'assemblage restent immuables.
- Preuve Blender finale : `work/native-lifecycle-f242fb4ae43c49b59bc32112db4eeaaf/result.json`, journal `work/native-lifecycle-final.log`. Les assertions native Blender contrôlent les objets et les hashes, sans déclarer de succès artistique.

## Non exécuté et limites

- Aucune génération GPU, aucun bake Cloth réel, aucun rig de vêtement réel ni import dans Unreal durant cette correction. La validation native du nouveau graphe sur les modèles Comfy installés reste à effectuer avant son premier job.
- L'asset existant et sa scène ouverte n'ont pas servi aux essais. Les exemples de tests sont expressément synthétiques.
- Le code vérifie la traçabilité et l'intégrité des fichiers ; il ne sait pas certifier leur fidélité artistique, la véracité d'un rapport ou l'authenticité d'une citation humaine. Les images doivent être ouvertes et comparées aux références originales.
- Les scripts Blender sont du Python de confiance, pas un bac à sable ni un système de quota CPU/GPU. Les hooks dépendent de leur activation et confiance dans Codex.
- Les rapports anciens sans les nouveaux champs ne sont pas automatiquement approuvés. Les instructions de reprise sont dans [le contrat des étapes](lifecycle-guards.md).

L'archive avant correction est conservée sous `work/before-lifecycle-0.2.0.zip`. La vérification de la copie installée et le résultat du serveur fraîchement lancé sont consignés séparément sous `work/installed-0.3.0-verification.json` lors de l'installation ; ils ne prouvent pas le rechargement d'un serveur déjà attaché à une ancienne conversation.
