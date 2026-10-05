# Restauration d'une frontière native

`restore_checkpoint` conserve sa forme historique sans arguments pour une
opération Blender interrompue encore présente dans `pending_blender_operation`.

Une opération peut aussi terminer et produire `NEEDS_CORRECTION`, ou dépasser
son budget et laisser un run `INCOMPLETE`. La réconciliation retire alors le
pending, mais le rejeu exige toujours la restauration du checkpoint d'entrée.
La forme `restore_checkpoint(run_id, attempt_id)` traite ce cas, sans recréer
un pending et sans accepter de chemin de fichier fourni par l'utilisateur.

La préparation et le dispatcher vérifient la dernière tentative Blender de
l'unité, son statut enregistré, le fingerprint canonique du run, le binding
de la tentative, le reçu natif exact et son événement, les identités historiques
du code, les sources, les artefacts et le checkpoint lié au démarrage natif.
Un autre pending ou une opération de run non réconciliée bloque la restauration.
Le dispatcher exige également la scène de travail connectée à ce projet.

La restauration sauvegarde une nouvelle copie de travail et produit un
événement natif `blender_recovered` avec les identités du run, de l'unité, de la
tentative et du checkpoint. Un nouvel appel identique ne rouvre pas la scène
si cette copie exacte est encore la scène courante. Une copie modifiée ou
une frontière remplacée ne bénéficie pas de cette idempotence.

Une correction du runtime peut invalider le code de l'ancien run sans rendre
son checkpoint historique inaccessible. La restauration authentifie les
empreintes historiques enregistrées, sans les remplacer par les empreintes
actuelles. Elle n'admet aucune nouvelle exécution : `studio_next_run_step`
continue à exiger les sources et le code actuels. Après changement de code,
il faut une nouvelle identité de spécification de run revue, plutôt que
réécrire le journal ancien. Aucun PASS de géométrie, Cloth, fitting ou revue
artistique n'est accordé par une restauration.

Chaque restauration exige sa propre autorisation explicite d'exécution
Blender. Les tests de `tests/test_returned_run_recovery.py` utilisent des faux
fichiers Blender et contrôlent les contrats portables ; ils ne prouvent pas
une réouverture native d'un vêtement.
