# Validation de continuité 0.5.2

Essais locaux du 1er octobre 2026, sous Windows et Blender 5.2.2 LTS
(`d13f752e3b9c`). La suite Python comprend **170 tests réussis**. Le validateur
PowerShell vérifie huit fichiers JSON distribués ; la configuration privée locale
fait l'objet d'un neuvième contrôle et reste exclue de la distribution.

## Régression native ciblée

Le script `tests/native_continuity_smoke.py` charge un instantané authentique du
commit public 0.4.0 `205d18c13a99bcbe0dff4d812c0da3a85516faa1`, puis les codes
exacts produits par le Studio 0.5.2 dans le même interpréteur Blender. Aucun MCP
de production n'est appelé. Le [protocole](blender-continuity.md) fournit la
commande, l'isolation du répertoire utilisateur et l'option `--modified-legacy`.

| Cas | Résultat et preuve |
| --- | --- |
| Modules anciens conservés dans `sys.modules` | PASS : tous les packages et sous-modules Atelier chargés proviennent de la racine demandée ; l'admission est répétée |
| Scène de travail dirty | PASS : checkpoint relu comme bibliothèque, géométrie et transformation non enregistrées présentes ; scène active, session et fichier sur disque inchangés |
| Scène étrangère | PASS : reprise refusée sans nouveau checkpoint |
| Panneaux 0.4.0 | PASS : ancien objet conservé et masqué, empreinte avant/après identique, nouveau mapping dérivé distinct |
| Variante subdivisée par un ancien script | PASS : vrai appel guardé 0.4.0 avec reçu, rest et Cloth conservés lors de l'archivage ; ancienne topologie explicitement non validée |
| Historique ou empreinte invalides | PASS : refus unitaires des sources modifiées, reçus étrangers, identité incompatible et empreinte périmée |
| Découpage approuvé | PASS : décisions, package et `garment.json` conservent leur identité |
| Placement cylindrique inversé | PASS : `mirror_u=true` reproduit la formule attendue sur trois points ; rest, faces, panneaux, coutures et pins inchangés ; empreinte de recette différente |
| Nouveau sens d'enroulement | PASS : contrôle préalable refusant l'ancien maillage et demandant sa reconstruction |

La régression `tests/native_lifecycle_smoke.py` passe également : import et
assemblage séparé, interruption après mutation, refus tant que l'erreur demeure,
restauration dans une nouvelle copie et reprise.

## Journaux locaux

Les fichiers suivants sont conservés dans le répertoire ignoré `work/` ; ils ne
sont pas inclus dans la release publique. Les tests et fixtures permettant leur
reproduction sont distribués.

- `work/continuity-final-tests.log` : 170 tests, 0 échec.
- `work/native-continuity-60d538b639a242eb8c7d26de4fcb8d61/result.json` : cas brut.
- `work/native-continuity-e0840f4db7004058b3be8b3685874ac3/result.json` : cas densifié.
- `work/native-lifecycle-cee4cec21c2d4dec895b0512274d5678/result.json` : régression du cycle de vie.

La CI publique exécute les tests Python et le conditionnement, pas Blender. Son
résultat doit être lu sur le commit exact de la PR ou de la release dans
[GitHub Actions](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml).

## Limites

Les simulations physiques ne sont pas relancées dans le test de continuité.
Le script historique synthétique sert à reproduire une modification de topologie,
pas à démontrer un drapé. Le test cylindrique ne valide pas l'ajustement d'un col,
un mannequin ou les tangentes d'une recette de production. L'archivage d'un mesh
densifié ne le rend pas conforme et ne prouve pas une chaîne exhaustive de toutes
ses modifications historiques.

La scène du consommateur et son Blender ouvert restent intacts. La migration
réelle, la validation visuelle, la simulation complète et l'export Unreal restent
à exécuter sur le candidat de production. L'installation dans Codex doit être
actualisée puis rechargée avant d'utiliser le nouveau Studio ; publier la release
ne remplace pas un serveur déjà démarré.
