# Reprise propre et fitting distinct — 0.6.4

Une robe cousue librement peut réussir le montage tout en étant incompatible
avec la pose actuelle du mannequin. Recommencer ne prouve ni ne corrige à lui
seul ce problème. Comparer les coordonnées, les coutures et les contacts avant
de conclure à une accumulation d'erreurs.

## Inspection malgré les contacts

`inspect_garment_fit` et `propose_pattern_adjustment` mesurent les capacités sur
un candidat géométriquement refusé. Les contrôles source/package/map, FlatRest,
topologie, pins, unités, transformations et identités du corps/enveloppe restent
stricts. Le rapport sépare `fit_status` et `placement_diagnosis.preflight`,
avec `accepted=false`, `simulation=NOT_EXECUTED`. `donning` indique les données
manquantes pour l'enfilage ; un proxy ne devient pas un corps cible qualifié.
Scène, fichier et SQLite ne changent pas. Les gates de mutation/full/freeze
continuent d'exiger leurs précontrôles physiques complets.

## Nouvelle scène versionnée depuis le même package

Sur la copie de travail sauvegardée, sans pending et avec board actuel approuvé :

```json
{"operation":"start_clean_construction","arguments":{"working_sha256":"SHA256_EXACT_DU_FICHIER_COURANT"}}
```

Cette opération explicite préserve une copie binaire du fichier courant comme
`witness-*.blend` et archive son ancien `session.json`. Elle ouvre une scène
réellement vide dans un nouveau `working-clean-*.blend` du même projet. Le fichier
source sauvegardé et ses reçus restent inchangés. Une scène dirty, une identité
périmée, une reconstruction acceptée ou un pending sont des refus. Ne pas lancer
ce changement de scène pour un simple diagnostic ou à l'insu de l'utilisateur.

La scène vide est chargée par `read_homefile(use_empty=True,
use_factory_startup=True, load_ui=False, use_splash=False)`, autorisé par le MCP
officiel. Préférences, add-ons et timers persistants sont conservés.
Ne pas désactiver le garde ou modifier le code fourni pour contourner un refus.

Un journal `clean-recovery-ID.json` existe avant le changement de scène.
Sur erreur, le rollback rouvre la source et restaure la session ; son statut
devient ROLLED_BACK. Source, témoin, candidat éventuel, archive et journal restent
disponibles. Si le rollback échoue, ROLLBACK_REQUIRED conserve son erreur.
Appeler alors `recover_clean_construction(recovery_path)` sur ce journal exact :
identités source/témoin/archive et session non remplacée sont vérifiées.
Préserver une scène dirty avant récupération. Un journal COMPLETED/ROLLED_BACK
ou remplacé par une nouvelle session n'est pas rejouable.
Cette opération n'utilise pas le pending standard : `restore_checkpoint`
ne s'applique pas à ce changement de scène. Ne pas créer de pending fictif.

Le package, le board, ses approbations exactes et les relations restent les mêmes.
Seul le point de départ de construction change. Aucun mesh, mannequin, cube,
Cloth ou résultat physique historique n'entre dans cette scène. Un nouvel ID de
construction lie maps/objets/essais : un ancien PASS ne qualifie pas la reprise.

Appeler `garment` avec le package exact et une recette de montage sans collider,
sans fitting et sans mannequin visible. Qualifier un nouveau local, transférer
son résultat avec `apply_sewn_result`, préparer les interfaces et le montage
nécessaires, puis qualifier un nouveau local/full `purpose=assembly`. Les anciens
essais restent des témoins. Ne pas copier leurs coordonnées ou qualifications
dans la nouvelle construction. `rebuild=true` à lui seul n'efface pas une scène.

Comparer ensuite le résultat complet à son témoin, avec les mêmes seuils et
profils. À coupe inchangée, cette préparation technique ne nécessite pas une
nouvelle approbation du découpage. Les closures réversibles et pièces amovibles
gardent leur type ; aucune fusion par proximité.

## Introduire le contexte après le montage libre

Après un full libre actuel PASS, importer seulement les objets explicitement
déclarés dans la recette/fiche de fitting depuis le témoin exact :

```json
{"operation":"introduce_fitting_context","arguments":{
  "component_id":"garment.coat","recipe_path":"fit.json","fit_path":"body-measurements.json",
  "source_blend":".a3d/blender/witness-ID.blend","source_sha256":"SHA256_EXACT_DU_TEMOIN"
}}
```

L'import vérifie le full courant, le fichier, les noms, géométries/poses, échelles
et épaisseurs de collision. Il refuse les dépendances ou objets de construction
non déclarés et les duplications. Les objets déjà présents sont conservés et
leurs identités vérifiées ; seuls les objets manquants sont importés.
Il conserve le vêtement intact et retourne
ses mesures, sans modifier la pose, enfiler ou simuler le vêtement.

Pour un corps choisi dans un fichier contenant un ancien vêtement et un rig,
suivre [la sélection du corps source](body-source.md). Préparer une référence
figée exacte plutôt qu'importer l'ensemble du fichier ou perdre sa pose.
Un collider séparé nécessite sa propre source qualifiée.

## Placement explicite de fitting

Un mannequin de 1,80 m n'est pas une preuve de pose compatible. Déclarer le corps
cible exact et des repères homologues validés sur vêtement et corps, avec indices
source, labels et provenance. Les épaules, coudes et poignets doivent être
contrôlés ; trois points alignés ne définissent pas la torsion d'un membre.
Ajouter un repère transversal pour un cadre non collinéaire.

Une recette de fitting peut déclarer `fitting_placement` :

```json
"fitting_placement": {
  "max_displacement_cm": 5,
  "groups": [{
    "pieces": ["sleeve-upper-left", "sleeve-under-left"],
    "source_indices": [101, 203, 307],
    "target_indices": [15, 24, 38],
    "labels": ["repere-proximal", "repere-distal", "repere-transversal"],
    "landmark_status": "validated",
    "source_ref": "releve-homologue-verifie",
    "tolerance_cm": 0.1
  }]
}
```

Les IDs/indices de cet exemple sont à remplacer par des mesures réelles.
`prepare_sewn_stage(stage=fitting)` applique des transformations rigides par
groupe disjoint depuis les coordonnées cousues actuelles. Il n'étire pas les
panneaux, ne change pas leurs contours et ne projette pas les sommets sur la
surface. Le corps reste immobile. Proxy, repères absents/colinéaires, cadres
incompatibles sans scale, groupes qui se chevauchent, pins fixes déplacés,
budget dépassé et précontrôle physique final refusé restent des erreurs.
Le placement est `PLACED_NOT_SIMULATED` ; il ne garantit pas qu'un vêtement fermé
puisse physiquement être enfilé, ni ne remplace une séquence d'enfilage.

La récupération de contact est réservée aux petites pénétrations initiales
(au plus 0,5 cm), avec son budget et les contrôles finaux existants. Une pénétration
profonde exige une pose/enfilage explicite : elle est refusée avant la projection
indépendante qui pourrait effondrer les segments. Ne pas augmenter les budgets
ou multiplier les profils pour contourner ce refus. Le diagnostic conserve
`stage_transition.initial_contacts`, profondeur et motif même quand les contacts
de racine sont vides. Un refus exige une restauration native du checkpoint.

Après un placement admissible, qualifier un nouveau local/full de fitting.
Le fitting réel, la stabilité longue, les UV/matériaux, rig, LODs, Unreal et
acceptation humaine restent des étapes séparées. Aucun PASS de fixture n'est
importé comme qualification du projet consommateur.
