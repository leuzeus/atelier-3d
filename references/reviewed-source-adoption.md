# Adoption canonique d'une révision de patrons

L'interface de branche `studio_adopt_reviewed_source_revision(project_root,
revision_path, expected_parent_epoch, request_key)` adopte des entrées de
conception déjà préparées et humainement revues. Elle utilise le service
`Project` et ses événements SQLite ; aucun patch manuel de base n'est admis.
Elle ne modifie pas Blender et ne crée aucune autorisation d'exécution.

La préparation préalable reste décrite dans
[les révisions approuvées](reviewed-pattern-revisions.md). Ses quatre preuves
doivent être celles de la décision humaine directe : proposition, planche,
dossier candidat et package. La politique, les paramètres, les crans et les
coutures sont rejoués ; une nouvelle optimisation ne remplace pas le candidat
examiné.

## Domaine initial

La première implémentation accepte un projet `RECONSTRUCTING` dont le parent
est une composition V1 calculée et authentifiée. Une seule composante textile
change, avec topologie conservée et exactement le périmètre revu. Le corps,
les routes, les types de raccord et le découpage global restent conservés.
Un autre parent ou un changement de conception hors de ce domaine est refusé.
Le service n'accorde pas une prise en charge implicite de toutes les révisions
ultérieures ni d'une modification du corps.

Une opération Blender en attente, un job actif ou une tentative non terminée
empêche l'adoption. L'arrêt ou la récupération suit le parcours existant ;
le service ne clôture pas artificiellement une opération interrompue.

## Preuve du parent et transaction

Le parent est conservé dans un snapshot neuf. Le vérificateur V1 est rejoué
contre son vrai ancêtre inchangé, avec les approbations, les fichiers et les
packages exacts. L'ancien état n'est jamais réinjecté dans `Project.state()`.
La génération du board reste celle du design original, de portée
`BASE_DESIGN_ONLY_SCOPED_REVIEW_SEPARATE`.

L'adoption réserve les ancêtres canoniques, puis recontrôle le parent et les
quatre preuves dans la transaction du projet. Un événement final
`reviewed_source_revision_adopted` active ensemble le manifeste V2, le package
du composant et son `source_epoch`. Les anciens fichiers, décisions et reçus
restent présents. Un artefact écrit avant un crash ne suffit pas à activer une
révision ; l'événement canonique fait autorité.

La même `request_key` avec les mêmes arguments exacts retourne le reçu déjà
enregistré après vérification. La réutilisation avec d'autres arguments est
refusée. `expected_parent_epoch` protège contre l'adoption sur un autre parent.

## Dépendances et reprise

Les preuves de production qui dépendent du dossier ou du package remplacé
sont retirées des slots courants et conservées dans le journal. Les mesures
intrinsèques du corps et les preuves indépendantes restent disponibles.
Les décisions humaines anciennes conservent leur portée ; leur historique ne
valide pas la nouvelle géométrie physique.

Les nouveaux runs textiles, de mouvement et d'export lient l'epoch active.
Une ancienne epoch bloque la reprise avant la réconciliation d'un résultat
natif. Les runs ComfyUI et de coupons indépendants restent sans epoch textile ;
une dépendance explicite périmée les invalide également. Les unités, tentatives
et reçus historiques ne sont pas effacés. Une invalidation de run fait partie
de la même transaction que l'adoption et est annulée si celle-ci échoue.

`studio_check_pipeline` vérifie ce manifeste avant le parcours V1. L'adoption
réussie signifie seulement que les entrées de conception courantes sont
admises : `qualification=NONE`, `fitting=NOT_GRANTED`,
`permission=NOT_GRANTED`. La prochaine préparation doit recompiler les guides
et recettes dépendants. Placement, Cloth, drapé, fitting et revue artistique
gardent leurs opérations, contrôles et autorisations propres.

## Reprise après une mise à jour logicielle

Une mise à jour peut modifier les empreintes des producteurs tout en recalculant
exactement les mêmes patrons et le même dossier. Cette situation ne demande pas
une nouvelle décision de coupe. Elle exige une revalidation explicite avec
`studio_revalidate_source_adoption(project_root, output_dir)`, dans un dossier
neuf sous `preparation/` et sans opération de production active.

Le service authentifie l'adoption historique, son événement canonique, ses
ancêtres, les fichiers et les décisions humaines actuelles. Il rejoue le calcul
avec le code courant. Seules les valeurs SHA des producteurs peuvent différer :
leur inventaire reste identique, et chaque autre champ, sortie, géométrie,
annotation, raccord et référence de package doit être strictement identique.
Une modification de données, une revue révoquée ou un producteur absent reste
un refus. L'epoch source, les packages et les anciennes décisions sont conservés.

Une attestation neuve conserve les deux inventaires logiciels et les fichiers
exacts. Son enregistrement canonique fait autorité ; un fichier laissé par une
interruption ne suffit pas. L'admission suivante refait le calcul intégral et
vérifie cette attestation contre le code effectivement chargé. Une nouvelle
modification de code la rend périmée et demande une nouvelle revalidation.

Cette opération ne revalide aucune preuve de placement, de simulation ou de
fitting. Les guides et les résultats physiques gardent leurs contrôles de code,
de géométrie et de candidat. Aucune autorisation Blender n'est créée.
