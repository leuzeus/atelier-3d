# Reprendre une session Blender après mise à jour

Le Studio et les hooks doivent provenir de la nouvelle installation. Fermer puis
rouvrir Codex après son remplacement, en conservant Blender ouvert si sa scène
contient des changements non enregistrés. Obtenir un nouveau code exact via
`studio_blender_operation` ; ne pas réutiliser le code fourni par l'ancien Studio.

Le code 0.5.2 charge `blender/bootstrap.py` par chemin absolu. Ce chargeur remplace
les packages Python `a3d`, `blender` et leurs sous-modules en cache, puis vérifie
leur origine avant d'appeler le dispatcher de l'installation demandée. Il ne
recharge pas de fichier `.blend` et ne change pas les données de la scène pour
activer le runtime. Le dispatcher répète l'admission canonique. Le contrôle du
code exact par les hooks reste requis ; ce mécanisme n'est pas un bac à sable Python.

## Protocole natif

Chaque ligne est un appel à `studio_blender_operation(project_root, operation,
arguments)`, suivi de l'exécution de son champ `code` inchangé dans le MCP Blender.

| Opération | Arguments | Résultat à contrôler |
| --- | --- | --- |
| `inspect` | `{}` | `runtime.version` égal à la version attendue, `runtime.root`, scène de travail, `is_dirty`, composants et `auxiliary_colliders` |
| `resume` | `{}` | Nouveau checkpoint et SHA-256 ; même `working`, fichier sur disque inchangé et modifications en mémoire conservées |
| `garment` pour des panneaux 0.4.0 non acceptés | `{"package_dir":"chemin/extrait","recipe_path":"recette.json","rebuild":true,"migrate_legacy":true}` | `archived_legacy_panels`, nouvel objet dérivé et son mapping, sans toucher aux contours approuvés |
| `simulate_sewn` | Recette, composant, phase et `scope="local"` | Essai local admis et physiquement mesuré avant un essai complet |

`resume` fonctionne sur la copie de travail déjà connectée, même dirty. Il ne
change ni le chemin actif ni `session.json`, ne marque pas le projet comme accepté
et ne réinitialise aucune opération en attente. Une erreur précédente exige
toujours `restore_checkpoint`. Un projet COMPLETE ou une autre scène sont refusés.
`prepare` reste réservé à la première création d'une session.

## Limites de la migration 0.4.0

La migration nécessite exactement un mesh pour le composant, avec le SHA du
package approuvé, sans rôle versionné ni ancien mapping. Les indices des faces,
les arêtes et le nombre de sommets doivent correspondre à la construction 0.4.0
du package. Le reçu d'import doit identifier le mesh, ses comptes et un checkpoint
dont le fichier et le SHA sont encore vérifiables.

Les positions et modificateurs peuvent avoir été modifiés : ils sont conservés
dans l'ancien objet archivé et dans le checkpoint. La nouvelle géométrie est
reconstruite depuis les sources et la recette actuelles. L'ancien objet reçoit le
rôle `archived-legacy-panels`, sans faux mapping ni rôle `simulation`. Le nouveau
maillage est seul candidat aux contrôles de couture. Les décisions humaines de
découpage restent applicables tant que références, dossier et packages ne changent pas.

### Variante legacy densifiée par des scripts

Si la topologie a changé, la voie précédente refuse le mesh brut incompatible.
Utiliser la même opération `garment` avec `rebuild=true`, `migrate_legacy=true` et
deux arguments supplémentaires, après `inspect` puis `resume` :

```json
{
  "package_dir": "chemin/extrait",
  "recipe_path": "recette.json",
  "rebuild": true,
  "migrate_legacy": true,
  "legacy_snapshot_sha256": "empreinte de 64 caracteres retournee par inspect",
  "legacy_script_receipts": [".a3d/blender/script-identifiant.json"]
}
```

Sélectionner les reçus historiques pertinents ; ne pas en fabriquer. Le plugin
vérifie l'identité du composant et du package, le reçu d'import initial et son
checkpoint, chaque reçu de simulation déclaré, le SHA du script conservé et son
checkpoint. L'empreinte de l'objet courant doit encore correspondre à `inspect`.
Elle couvre les sommets, arêtes, faces, transformation, poids et formes de repos.
La même empreinte est vérifiée après archivage ; le checkpoint complet conserve
également modificateurs et matériaux. Le reçu de reconstruction conserve le reçu
d'import ancien et les empreintes avant/après.

Cet archivage conserve un objet de diagnostic **non validé**, même s'il possède
des défauts. Il ne certifie pas que les scripts historiques expliquent toutes ses
modifications. Il ne réutilise ni ses indices ni son mapping dans le nouveau
maillage, qui est entièrement dérivé du package et de la recette actuels. Aucune
simulation n'est automatiquement lancée. Un reçu absent ou altéré, une identité
étrangère ou une empreinte périmée sont refusés. Un composant RECONSTRUCTED reste
immuable ; ne pas fabriquer des propriétés pour passer les contrôles.

## Essai natif reproductible

Dans une copie du dépôt, extraire le commit public 0.4.0
`205d18c13a99bcbe0dff4d812c0da3a85516faa1` dans `work/legacy-0.4.0`, puis exécuter
dans un processus dédié (jamais dans le Blender de production) :

```powershell
$env:BLENDER_USER_RESOURCES = "$PWD/work/blender-test-user"
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tests/native_continuity_smoke.py -- --legacy-root "$PWD/work/legacy-0.4.0"
```

Le test charge réellement les modules 0.4.0, construit une fixture, la modifie puis
exécute les codes exacts du nouveau Studio dans le même interpréteur. Il lit le
checkpoint pour vérifier les changements sauvegardés, vérifie l'archivage, le
nouveau mapping et les décisions conservées, puis teste le refus d'une scène
étrangère. Il n'exécute pas de simulation physique ni de qualification artistique.
Répéter avec `--modified-legacy` pour exercer le chemin densifié : la fixture est
modifiée par un vrai appel `run_script` de la version 0.4.0, avec reçu natif,
subdivision et forme de repos. Ce script synthétique ne simule pas la physique.
Le répertoire utilisateur isolé utilise la variable documentée par
[Blender](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html#environment-variables).
