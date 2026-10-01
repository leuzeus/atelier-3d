# Validation locale de la recette de couture — 0.5.0

Date : 2026-10-01. Tests exécutés sous Windows, Blender **5.2.2 LTS**, build
`d13f752e3b9c`, dans des processus indépendants avec scène d'usine. Aucun test
n'a utilisé la scène Blender de production ouverte.

## Constats et correction

Le code antérieur utilisait directement les faces source pour Cloth, affectait
`material.mass_kg` à la masse **de chaque sommet** et ne fixait pas le plafond de
couture. Il ne vérifiait pas entièrement les colliders auxiliaires, la forme de
repos ou les paramètres réels après un script. Ces constats sont distincts de
la cause de tous les essais sans mouvement signalés par un projet consommateur :
cette dernière n'a pas été établie pour ce projet.

La correction introduit une recette native : dérivation bornée des panneaux,
contexte physique mesuré, essais courts puis simulation complète, et copie de
surface soudant les seules paires permanentes. Elle conserve les contours
approuvés, les décisions du board inchangé et les variantes techniques archivées.
Voir [le parcours et les arguments](sewn-toile.md).

## Résultats

| Contrôle | Résultat et portée |
| --- | --- |
| Suite Python | **PASS, 156 tests** : contrats, packages, protocoles, hooks, board, coutures et progression |
| JSON indépendant | **PASS** : recette et fixtures avec PowerShell `Test-Json` ; 8 fichiers distribués, plus la configuration locale lorsqu'elle existe |
| Source dense | 4 001 points collinéaires rééchantillonnés en 21 points ; source inchangée, erreur de contour et échantillons appariés vérifiés |
| Repos et placement | Refus d'arêtes effondrées, triangles dégénérés, coordonnées non finies et étirement ×41,6 |
| Masse | Masse totale constante quand la résolution change ; conversion explicite par sommet et force finie |
| Gravité | Coupon 10 × 10 cm, 3 g, 12 frames : centre de 6 cm à environ −0,584 cm avec pas 2 cm, et 0,750 cm avec pas 1 cm |
| Couture | Deux coupons, écart initial 1 cm : environ 0,116 cm et 0,271 cm après 24 frames, pour les deux résolutions |
| Contact | Départ à 2 cm, centre final environ 0,559 cm et 0,420 cm au-dessus du support ; la chute libre correspondante passerait sous le support. Pénétration finale mesurée nulle |
| Essai local puis ensemble synthétique | Fragments de quatre demi-cylindres autour d'un support mesuré : écart de couture final environ 0,034 cm après 32 frames sur l'ensemble |
| Consolidation | 1 120 → 1 047 sommets par 73 unions explicites ; deux ouvertures longitudinales non soudées |
| Refus physiques | Absence de réponse, script sans évaluation terminée, mannequin changé, modifier recréé avec masse différente et poids d'exclusion modifiés détectés |
| Reprise | Simulation complète refusée sans essai local correspondant ; deux échecs complets injectés imposent un nouvel essai local réussi |
| Variante technique | Reconstruction du mesh dérivé avec archivage intact de la copie précédente et décision du board conservée |
| Cycle Blender existant | Import, assemblage de panneaux existants, panne après mutation, refus de continuation, restauration et reprise : **PASS** |

Les rendus natifs des sondes et les vues de face, profil et dos de l'ensemble
synthétique ont été ouverts. Ils montrent l'assemblage et l'ouverture conservée.
Le contact et la géométrie finale présentent une réponse mesurée ; la surface
reste facettée. Les valeurs ci-dessus ne démontrent ni invariance physique selon
la résolution, ni qualité de drapé d'une robe réelle.

Les trois sondes isolent les mécanismes ; l'essai local du projet utilise ensuite
ses propres paramètres. Le cas natif testé est un raccord de fragments
cylindriques, **pas une manche ajustée à une emmanchure anatomique**. La phase
complète testée est `mount` ; le drapé d'un vêtement complet reste non qualifié.

## Reproduire

Depuis la racine du dépôt, dans des processus dédiés :

```powershell
python -B -m unittest discover -s tests -v
pwsh -NoProfile -File scripts/validate_contracts.ps1
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tests/native_lifecycle_smoke.py
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tests/native_sewing_smoke.py
```

Utiliser le chemin local de l'exécutable Blender si nécessaire. Pour isoler aussi
les ressources utilisateur, définir `BLENDER_USER_RESOURCES`, `TEMP` et `TMP`
vers des répertoires de test autorisés avant de lancer les processus. Ne pas
exécuter ces scripts dans le Blender MCP connecté à une production.

Chaque test natif écrit un répertoire unique sous `work/native-*`, ses rapports,
scènes synthétiques et rendus. Ces fichiers restent locaux et exclus de l'archive
source. Les reçus automatiques portent `visual_validation=NOT_EXECUTED` : un
résultat numérique ne s'auto-attribue pas une revue visuelle ou humaine.

## Limites et préservation

Le mannequin doit être préparé et ses normales vérifiées. Le contrôle de contact
porte sur les sommets ; il ne prouve pas exhaustivement l'absence de croisements
entre triangles. Seuls les placements plats et cylindriques sont fournis. Le
fitting complexe, le bake d'animation, les matières finales, le rig, les UV et
l'import Unreal restent **NOT_EXECUTED** sur un asset réel.

Les douze fichiers consommateurs suivis par empreinte avant/après, dont le
contrat de patrons, les preuves examinées et l'état du projet, sont inchangés.
Les assets privés et l'ancienne robe n'ont pas été reconstruits par ces tests.
Le temps gagné sur un vêtement complet n'est donc pas mesuré.

La route de modélisation classique pour accessoires n'est pas ajoutée dans cette
correction ; les routes publiques restent `PATTERN_SEWN` et `MULTIVIEW_PART`.
La correction 0.5.0 est préparée localement. Sa publication GitHub, sa CI distante
et son installation Codex sont distinctes et ne sont pas attestées par ce rapport.
