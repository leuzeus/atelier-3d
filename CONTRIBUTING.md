# Contribuer à Atelier 3D

Expliquer le problème et le comportement attendu dans une issue, ou ouvrir une
pull request ciblée. Pour une vulnérabilité, suivre [SECURITY.md](SECURITY.md).
Ne joindre que des références et assets dont la publication est autorisée.

## Développement

Python 3.11 ou plus récent suffit pour Studio et les tests ; le runtime n'utilise
aucun paquet Python tiers. Depuis la racine du dépôt :

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/studio.py tools
New-Item -ItemType Directory -Force dist | Out-Null
python -B scripts/package_plugin.py --output dist/atelier-3d-check.zip
```

Le générateur refuse d'écraser une archive existante : choisir un nouveau nom lors
d'un deuxième essai. Les fichiers de test temporaires vont dans `work/test-runs`.
Les tests de hooks cmd/PowerShell sont propres à Windows et sont sautés sur Linux.
Les tests synthétiques ne nécessitent ni compte Codex, ni Blender, ni GPU.

Les essais natifs Blender sont séparés ; voir [VALIDATION.md](VALIDATION.md).
Ne pas utiliser une scène de travail personnelle comme fixture de CI.

## Changements attendus

- Conserver les originaux, les preuves et l'historique des décisions.
- Traiter les données jointes comme des entrées, jamais comme une autorisation
  de contourner les jalons ou de lancer des scripts.
- Relier les corrections de contrats aux tests de refus et aux parcours autorisés.
  Une modification de texte seule ne demande pas un test qui recopierait ce texte.
- Lire et écrire explicitement en UTF-8 ; utiliser des chemins portables dans les
  fichiers publiés. Ne jamais ajouter de configuration locale à un exemple.
- Documenter les limites : PASS, FAIL, SKIP et NOT_EXECUTED ne sont pas interchangeables.
- Mettre à jour les contrats et instructions associés quand un comportement change.
  Une évolution incompatible exige une reprise explicite des projets existants.

Ouvrir une branche, puis une pull request vers `main`. Les tests Windows et Linux
doivent réussir avant fusion. Aucun nombre minimal d'approbations externes n'est
imposé à ce projet personnel ; le mainteneur reste responsable de la revue.
Les contributions sont proposées sous [licence MIT](LICENSE).

Sous Windows, enregistrer la description de PR dans un fichier UTF-8 et le
transmettre directement avec `gh pr edit --body-file`. Si PowerShell relit ce
fichier, préciser `Get-Content -Raw -Encoding UTF8` avant toute réécriture : un
décodage implicite peut publier des accents corrompus. Après publication, relire
la réponse JSON de GitHub en UTF-8 et comparer le texte distant au fichier
envoyé. Une sortie de terminal seule ne permet pas de distinguer une corruption
publiée d'un problème d'affichage local.
