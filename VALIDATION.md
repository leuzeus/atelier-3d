# Validation d'Atelier 3D

## État de la version 0.5.0

Le socle logiciel, les contrats et des opérations natives Blender ont été
vérifiés. **La qualification de production d'un asset complet reste non exécutée.**
Les contrôles automatisés ne prouvent pas la fidélité artistique des références,
l'ajustement des patrons ou la qualité d'un export de jeu.

| Vérification | Résultat connu | Portée |
| --- | --- | --- |
| Suite Python sous Windows | PASS : 156 tests | Contrats, packages, refus, parcours autorisés, MCP, hooks, board et recette de couture synthétique |
| Rendu du board synthétique | PASS : pixels examinés | Lisibilité, légende, repères et échelle relative ; aucune qualification d'un vrai vêtement |
| Blender 5.2.2 LTS | PASS : essai natif indépendant | Import, panneaux existants, erreur après mutation, blocage, restauration et reprise |
| Recette native de couture | PASS : fixtures isolées, deux résolutions pour les trois sondes physiques | Gravité, couture, contact réellement sollicité, sous-ensemble local puis complet, consolidation et conservation des ouvertures ; voir le rapport 0.5.0 |
| Revue des rendus natifs | Effectuée sur les fixtures synthétiques | Contact et assemblage de fragments cylindriques ; aucune qualification d'une vraie emmanchure ni d'une robe |
| Distribution 0.5.0 | Archive source vérifiée localement | Publication et installation de cette correction non exécutées dans cette validation |
| Installation Codex sous Windows | PASS lors de l'installation locale 0.4.0 | Nouveau serveur : 29 outils et fichiers de runtime vérifiés ; rechargement d'une conversation existante à vérifier séparément |
| Connexion Comfy officielle | PASS lors du diagnostic local antérieur | Découverte du serveur existant ; ne prouve pas la compatibilité de chaque workflow GPU |
| Image de production via Codex Image | NOT_EXECUTED dans les tests du plugin | Fournisseur explicitement simulé ; pas de reçu réel inventé |
| Génération GPU, fitting, bake Cloth complet | NOT_EXECUTED | À qualifier sur références, nœuds et modèles réels |
| Rig, animation et import Unreal d'un vrai asset | NOT_EXECUTED | À qualifier selon la destination |
| Installation Codex macOS/Linux | NOT_EXECUTED | Distincte de l'exécution des tests Python sur ces systèmes |

Les rapports des corrections [0.2.0](references/validation-pipeline-0.2.0.md),
[0.3.0](references/validation-lifecycle-0.3.0.md) et
[0.4.0](references/validation-fabrication-0.4.0.md) et
[0.5.0](references/validation-sewing-0.5.0.md) décrivent les essais locaux.
Les journaux `work/` mentionnés dans ces rapports sont conservés localement et
**ne sont pas distribués**. Pour une preuve publique reproductible, consulter
[les exécutions CI et leur commit](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml).
Ne pas transférer le résultat d'un ancien commit vers un nouveau.

## Reproduire les contrôles logiciels

Depuis la racine du dépôt avec Python 3.11+ :

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/studio.py tools
pwsh -NoProfile -File scripts/validate_contracts.ps1
New-Item -ItemType Directory -Force dist | Out-Null
python -B scripts/package_plugin.py --output dist/atelier-3d-validation.zip
```

Les tests n'appellent aucun moteur de génération et ne nécessitent pas de GPU.
La CI exécute la suite sous Windows/Python 3.11 et Linux/Python 3.13, avec
construction de l'archive. Deux tests cmd/PowerShell sont explicitement sautés
sur Linux. L'installation du plugin dans Codex n'est pas testée par ces runners.

La validation indépendante JSON requiert PowerShell 7 (`Test-Json`). Les schémas
externes des manifestes peuvent être passés à `scripts/validate_contracts.ps1`
avec `-OfficialSchemaDirectory` ; ils ne sont pas téléchargés par la CI.

`tests/native_lifecycle_smoke.py` et `tests/native_sewing_smoke.py` sont des essais
Blender séparés : ils doivent s'exécuter
dans un processus Blender dédié, avec scène vide et son dossier de travail de test,
jamais dans la scène de production ouverte. Examiner ce script avant exécution.
Ils ne font pas partie de `unittest discover` ni des jobs GitHub Actions. Utiliser
`--background --factory-startup --disable-autoexec --python-exit-code 1` pour que
les erreurs Python échouent réellement au niveau du processus. Pour le script
de couture, consulter [les commandes et limites](references/validation-sewing-0.5.0.md).

## Qualification de production à effectuer

Conserver versions, licences, modèles, paramètres et preuves dans le projet.

1. Vérifier les connexions effectives et les nœuds/modèles de chaque template avant
   de lancer un job ; qualifier les limites mémoire et l'usage des images originales.
2. Scénario vêtement : références réelles approuvées, dossier technique, packages,
   vue éclatée Codex Image, proportions et board humainement validé ; placement,
   mannequin de collision, drapé borné et comparaison des pixels aux originaux.
3. Scénario articulé : composants séparés, références multivues cohérentes, jobs
   indépendants, validation d'identité/échelle, assemblage par ancrages et articulation.
4. Provoquer une erreur limitée dans une copie, vérifier le blocage et la reprise.
   Une soumission Comfy incertaine doit être réconciliée sans envoi en double.
5. Vérifier retopologie, UV, matières, rig, poids et dégagements selon le besoin.
   Pour un jeu, inspecter l'import dans le moteur, les animations et le budget.
6. Présenter les livrables et preuves du candidat exact avant la décision finale.

Ces scénarios restent `NOT_EXECUTED` tant que leurs preuves réelles ne sont pas
produites. Un champ `PASS`, une empreinte ou un compte rendu rédigé par l'assistant
ne remplace pas une mesure, une image examinée ou une acceptation humaine.
