# Préparer une révision de patrons déjà approuvés

`studio_prepare_reviewed_pattern_revision(project_root, gate_name, roles,
output_dir)` prépare les données de la prochaine étape de patronage depuis
le parent exact et une nouvelle revue humaine. Cette interface de branche
n'est pas distribuée dans le runtime `0.7.0-rc.2.dev.2026100701`.

Les quatre valeurs de `roles` sont les clés de preuves présentes dans la
décision humaine réelle : `proposal`, `review`, `candidate_dossier` et
`variant_package`. La proposition scellée doit déclarer sa compilation,
sa politique de gradation et les paramètres retenus. Le service recompile
les sources puis rejoue ces paramètres ; il ne relance pas l'optimisation.

Le parent peut déjà contenir une variante calculée et approuvée. La nouvelle
revue porte uniquement sur le changement depuis ce parent. Les pièces hors
de ce périmètre, les raccords et les annotations protégées sont comparés
exactement, sans tolérance numérique. Une approbation antérieure de manches
ne devient donc pas une approbation des nouvelles pièces du col.

La préparation V1 exige une topologie inchangée, les crans matière conservés
et un seul composant textile affecté. Les autres cas sont refusés explicitement.
Elle ne fournit pas encore l'adoption de cette révision dans les bindings
de production d'un projet en `RECONSTRUCTING`.

Les sorties sont écrites dans un répertoire neuf sous `preparation/` :

- `effective-dossier.json` : dossier calculé pour la préparation suivante ;
- `effective-packages.json` : références des packages correspondants ;
- `revision.json` : parent, décision, périmètre, empreintes, budgets et résultats.

Le `source_epoch` identifie ces données et leur filiation. Il ne remplace
ni l'admission du pipeline ni l'identité d'un candidat physique. Le résultat
reste `DESIGN_SOURCE_REVISION_PREPARED`, `ADOPTION_REQUIRED`,
`production_binding=NOT_CHANGED`, `execution=NOT_AUTHORIZED` et
`fitting=NOT_QUALIFIED`. SQLite et la scène ne sont pas modifiés.

Le service contrôle les sources, le code et l'état canonique avant et après
écriture. Un changement pendant le calcul produit un refus ; les fichiers
diagnostiques restent conservés. Les budgets sont de 120 secondes,
128 Mio d'entrées, 64 Mio par fichier, 16 Mio de sorties et 512 références.
Le préflight inclut les tailles décompressées déclarées des packages et les
dépendances de conception de huit projets parents au maximum, avant les
lecteurs d'admission historiques. Il ne parcourt pas les preuves de runs,
scènes et checkpoints sans rapport avec cette préparation.
Une sortie existante ou un alias de casse est refusé.

Pour poursuivre la production, il faut une opération d'adoption distincte
qui réconcilie les packages, le dossier, les guides et les preuves dépendantes.
Les opérations Blender passent ensuite par `studio_check_pipeline` et
`studio_blender_operation`, avec l'autorisation exacte de l'utilisateur.
La présente préparation n'autorise aucun placement, Cloth ou fitting.
