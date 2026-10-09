# Composition calculée depuis une revue de patrons existante

Le service `a3d.reviewed_pattern_admission` prépare et vérifie une composition
d’entrées. Il lit les fichiers et SQLite sans écrire de dossier, enregistrer de
preuve, modifier une étape ou créer une décision humaine. Le coordinateur reste
responsable de l’import dans un nouveau projet et des transitions ordinaires.

## Préparation

`prepare_reviewed_pattern_composition(source, request)` reçoit un `Project`
source et exactement deux champs :

```json
{
  "gate_name": "pattern-variant.sleeves.garment.coat",
  "decision_evidence_key": "pattern-variant.sleeves.garment.coat.decision"
}
```

Les identifiants de cet exemple désignent des clés ; le service ne crée aucun de
ces enregistrements. La source doit conserver son board original courant, ses
packages liés, ses références et ses décisions de construction et de route. La
revue de variante doit être un véritable événement `human_decision` du projet
source, identique au record actuel de la gate. Une gate copiée depuis un autre
projet ne suffit pas pour cette nouvelle revue de patrons.
La gate demandée appartient au namespace `pattern-variant.` : aucune gate de
fitting, de génération ou d’acceptation finale n’entre dans les copies ajoutées.

Le document de décision V1 contient `approved: true`, `component_id`, une liste
`piece_ids` explicite, unique et non vide, `approved_scope`, `statement` et
`source_ref`. Ces deux derniers champs doivent être exactement ceux de la gate.
Les types admis sont :

| Statut du document | Portée minimale explicite |
|---|---|
| `TWO_SLEEVE_PATTERN_VARIANT_APPROVED` | `two_sleeve_pattern_shapes`, deux pièces |
| `SCOPED_PATTERN_VARIANT_APPROVED` | `pattern_shapes`, pièces listées |

Les sept références imbriquées suivantes sont obligatoires. Chaque référence
contient exactement `path` et `sha256`, vise un fichier réel et utilise un chemin
relatif portable dans le projet source.

| Champ | Liaison supplémentaire requise |
|---|---|
| `proposal_ref` | Une seule entrée exacte de la même gate humaine |
| `review_ref` | Une seule entrée exacte de la même gate humaine |
| `candidate_dossier_ref` | Une seule entrée exacte de la même gate humaine |
| `variant_package_ref` | Une seule entrée exacte de la même gate humaine |
| `numeric_design_decision_ref` | Identité du fichier vérifiée ; aucune admission de fitting déduite |
| `body_ref` | Identité du fichier vérifiée ; aucune qualification anatomique ou physique créée |
| `original_dossier_ref` | Dossier original exact lié au board original |

La référence du document de décision doit également être liée une seule fois à
la même gate. Des rôles visant le même chemin, des bindings dupliqués ou un
document JSON ambigu sont refusés ; une différence de casse ne distingue pas
deux rôles sur le même chemin Windows.

Le package candidat doit conserver exactement les champs globaux, coutures,
matières, IDs et pièces hors portée. Le dossier composé conserve les lignes et
l’ordre du dossier original pour toutes les pièces non revues ; seules les
lignes explicitement revues viennent du dossier candidat. Les différences des
lignes exclues sont rapportées, y compris un changement d’une seule ULP dans un
cran. Aucune tolérance ne permet de les importer.

Les contrats de construction et de fabrication existants sont ensuite exécutés
sur le dossier composé avec les packages candidats : inventaire, routes,
dimensions, droit-fil, marges, contour de coupe, plis, repères et proportions.
Cette validation de données conserve ses limites et ne qualifie aucun vêtement.

Le retour comprend :

- `files` : tous les fichiers source nécessaires et leurs SHA-256 ;
- `sources` : les sources retournées par la validation du dossier ;
- `extra_gates` et `extra_evidence` : uniquement la gate de revue demandée et
  ses records exacts, à préserver sans fabriquer d’événement humain ;
- `package_overrides` : le package exact du composant revu ;
- `composed_dossier` : la composition déterministe ;
- `manifest_template` : la preuve typée `CALCULATED_SOURCE_COMPOSITION`, avec
  les origines, comparaisons, fichiers, SHA des deux producteurs et champs de
  sortie encore vides.

## Génération du board original et imports historiques

La validation de génération s’applique seulement au dossier et aux packages
originaux. `generation_origin` identifie le vrai projet, sa requête, son reçu et,
si nécessaire, la lignée des imports canoniques.

Certains imports `EXACT_APPROVED_DESIGN_IMPORTED` conservent le reçu de génération
sans copier le slot SQLite de sa requête. V1 peut lire cette requête dans le
parent original si le manifeste d’import et son événement canonique sont
identiques, les gates héritées et le board sont toujours exacts, les packages et
le dossier sont identiques et le reçu copié est celui du parent. La validation
existante `validate_dossier` s’exécute dans ce parent réel en lecture seule. Une
requête absente, un reçu périmé, une approbation révoquée, un parent modifié, une
lignée cyclique ou une profondeur supérieure à huit sont refusés. Le service
n’ajoute aucun slot de génération au projet importé.

Une révision sans rapport avec ces dépendances reste admissible. Réenregistrer
une preuve liée modifie son record canonique et peut rendre la décision ou la
génération périmée, même si le fichier conserve les mêmes octets.

## Vérification avant reconstruction

`require_reviewed_pattern_composition(project, state, base_manifest, packages)`
requiert une preuve enregistrée sous la clé distincte
`reviewed-pattern-composition`. Le caller a rempli :

```text
output.dossier_ref = {path, sha256}
output.packages = records complets de tous les packages courants
```

Le service prépare à nouveau la composition depuis le parent canonique, compare
le manifeste intégral, vérifie les copies source, le code, le dossier de sortie
et tous les packages. Seul `source_revision_observed` est descriptif : toutes les
dépendances pertinentes restent vérifiées. Les décisions source sont relues aux
frontières de préparation et de consommation.

La vue dérivée donne le chemin du dossier composé, ses dépendances exactes et ses
packages. Elle conserve le board original et sa décision humaine ; ses anciennes
images restent explicitement de portée
`BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE`. Une composition déjà calculée ne peut
servir de nouveau parent en V1.

Le statut `COMPOSED_INPUTS_ONLY` et la vue calculée conservent `qualification:
NONE`, `construction: NOT_GRANTED`, `fitting: NOT_GRANTED` et `permission:
NOT_GRANTED`. L’import conserve seulement les autorisations de conception déjà
enregistrées, dans leur portée exacte. Il ne transfère aucune preuve de Blender,
Cloth, fitting, mouvement, acceptation artistique ou livraison. Les fixtures des
tests sont synthétiques et ne constituent aucune acceptation du manteau réel.

## Vérification ciblée

```text
python -B -m unittest tests.test_reviewed_pattern_admission -v
```

Les cas incluent l’import public complet, le replay, les falsifications de
portée et de manifeste, les modifications hors portée, les inputs copiés, les
gates sans événement, les révocations, les révisions non liées et la lignée de
génération originale. Aucun calcul Blender n’est lancé par cette suite.
