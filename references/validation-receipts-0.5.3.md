# Validation des reçus multicomposants 0.5.3

Essais du 1er octobre 2026 sous Windows, avec Blender 5.2.2 LTS
(`d13f752e3b9c`). **176 tests Python réussis** ; huit contrats JSON distribués
vérifiés indépendamment, plus un contrôle de configuration privée locale.

## Cas natif reproduit

`tests/native_multigarment_smoke.py` utilise l'instantané public réel de la version
0.4.0 au commit `205d18c13a99bcbe0dff4d812c0da3a85516faa1` et un projet synthétique
à trois composants. Les packages, données de fabrication, routes et décisions
de test sont explicitement synthétiques ; ils ne qualifient aucun vêtement réel.

1. Importer successivement manteau, capuche et ceinture par les vrais appels
   `garment` 0.4.0 : le reçu global n'identifie plus que la ceinture.
2. Densifier le manteau et ajouter une forme de repos par un vrai `run_script`
   guardé 0.4.0, sans lancer de simulation physique.
3. Charger les codes exacts 0.5.3 dans le même interpréteur, inspecter puis reprendre
   la scène dirty. Reproduire le refus de l'ancien prérequis de reçu unique.
4. Exécuter `verify_legacy_import`, vérifier le checkpoint dans le journal canonique,
   puis lire le manteau original dans le checkpoint
   avant l'import de la ceinture. Vérifier identité, package et topologie ; retirer
   tous les IDs temporaires et conserver contexte, fichier actif et état canonique.
5. Refuser un fichier de checkpoint altéré, un objet absent et des identités de
   composant/package étrangères, sans créer une opération en attente.
6. Archiver et reconstruire les trois composants, puis reconstruire de nouveau
   le manteau : conserver les voisins, rest, sources, décisions et reçu global.
   Vérifier quatre nouveaux reçus distincts, leurs SHA et les liens des objets.

Tous ces contrôles passent. La régression `native_continuity_smoke.py` avec
`--modified-legacy` passe également : activation de version, sauvegarde dirty,
archivage, mapping nouvellement dérivé, `mirror_u` et refus d'une scène étrangère.

## Lecture du checkpoint consommateur

Un checkpoint historique authentique du projet consommateur a été inspecté dans
un processus Blender séparé. Il contient le mesh d'import du composant demandé,
avec l'identité/package et la topologie initiale attendus, bien que le reçu global
identifie un autre composant. Les SHA des fichiers d'entrée et de l'état canonique
restent identiques après lecture. Le Blender ouvert n'est pas utilisé.

Cette observation vérifie la disponibilité de la preuve de récupération dans ce
cas. Elle ne constitue ni une migration exécutée sur le consommateur ni une
qualification de la géométrie de diagnostic densifiée. Les fichiers privés, noms
de projets, chemins machine et données du vêtement ne sont pas distribués.

## Reproduire

Préparer l'instantané 0.4.0 comme décrit dans le
[protocole de continuité](blender-continuity.md), puis, dans un processus dédié :

```powershell
$env:BLENDER_USER_RESOURCES = "$PWD/work/blender-test-user"
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tests/native_multigarment_smoke.py -- --legacy-root "$PWD/work/legacy-0.4.0"
```

Journaux locaux ignorés et exclus de la release :

- `work/receipt-recovery/unit-tests.log` : 176 tests réussis.
- `work/native-multigarment-6ba0a99391d04ac5a9dfbfb358736d5d/result.json` : scénario multicomposants.
- `work/native-continuity-413f8b87f0034a75a92ecf505c42c614/result.json` : régression de reprise.
- `work/receipt-recovery/consumer-readback.json` : preuve privée de lecture du checkpoint réel.

La [CI publique](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml)
exécute les tests Python et l'archive sur le commit exact ; elle n'exécute pas
Blender. Les essais natifs restent reproductibles séparément.

## Limites

Les reçus sont des fichiers ajoutés et liés au composant/package ; aucune propriété
d'inviolabilité cryptographique du système de fichiers n'est revendiquée. Un reçu
écrit avant une interruption peut rester comme diagnostic ; une réussite nécessite
aussi la fin de l'opération canonique, sans état pending. Le fichier global ancien
reste une preuve historique conservée, jamais le dernier reçu des nouvelles opérations.

Un checkpoint déjà densifié sans preuve de la topologie initiale, absent, altéré
ou étranger reste refusé. La récupération ne fabrique pas de reçu d'import et
n'attribue pas de mapping natif au mesh archivé. Les simulations locale/complète,
la silhouette du vêtement et son import Unreal restent à qualifier séparément.
