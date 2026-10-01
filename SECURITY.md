# Sécurité

## Signaler une vulnérabilité

Utiliser [Report a vulnerability](https://github.com/leuzeus/atelier-3d/security/advisories/new)
pour un signalement privé. Ne pas publier de secret, d'image privée, de scène
client ou de chemin personnel dans une issue. Fournir la version, le scénario
minimal, l'impact et des données synthétiques lorsque possible. Aucun délai de
réponse contractuel n'est garanti pour ce projet personnel.

Seule la dernière version publiée est maintenue. Les anciennes versions peuvent
nécessiter une mise à jour ; leurs approbations ne sont pas transférées vers de
nouveaux contrats ou de nouvelles preuves.

## Frontières de confiance

- Studio s'exécute avec les droits du compte local. Ses vérifications de chemins,
  d'archives et d'état ne constituent pas une isolation du système d'exploitation.
- Les scripts Blender sont du Python de confiance. Examiner leur contenu avant
  exécution ; leurs empreintes et checkpoints ne prouvent pas leur innocuité.
- Les hooks dépendent de leur activation et de la confiance accordée dans Codex.
  Ils bloquent les contournements connus, pas tout programme externe possible.
- L'adaptateur Comfy utilise une adresse HTTP de boucle locale. Il n'expose pas
  d'API HTTP publique. ComfyUI, ses nœuds, ses modèles et les MCP externes doivent
  être installés et évalués séparément.
- Les données du projet restent dans son dossier ; les images transmises à Codex
  et à Codex Image suivent les conditions de ces services. « Plugin local » ne
  signifie pas que ces services d'IA s'exécutent hors ligne.
- Une preuve hachée détecte sa modification. Elle n'authentifie pas à elle seule
  une déclaration humaine, une génération externe ou la qualité artistique.

## Dépôt et publication

La configuration machine, les jetons, les environnements, les poids de modèles,
les scènes, les références utilisateur et les sorties de production ne font pas
partie du dépôt. `.gitignore` et le générateur d'archive servent de protections
complémentaires ; relire les fichiers avant tout commit et toute publication.

La configuration GitHub prévue est décrite dans [la maintenance](references/repository-maintenance.md).
Les paramètres effectifs sont ceux visibles dans GitHub ; les fichiers du dépôt
ne les activent pas à eux seuls. Les contrôles automatisés ne remplacent pas une
revue de code.
