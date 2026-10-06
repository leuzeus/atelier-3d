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

Les nouvelles opérations natives archivent dès leur reçu les projections
mutables connues : session, inventaire des candidats et scènes de travail
`working-HEX` ou `working-recovered-HEX`. Les copies exactes deviennent des
références immuables déclarées ; l'observation live reste distincte.

Un reçu ancien peut encore référencer sa session live. Pour la restauration
seulement, les références historiques sont authentifiées dans des archives
distinctes, liées à la tentative et au SHA exact du reçu canonique. Si une
restauration partielle a déjà changé le chemin de travail, la session peut
être reconstruite en mémoire en remplaçant uniquement `working` par l'unique
chemin de travail historique déclaré. Le JSON courant doit être strict et
géré ; le résultat doit reproduire le SHA complet de la session historique.
Un champ différent, un choix ambigu ou un artefact absent reste refusé. Les
scènes Blender ne sont jamais reconstruites à partir de métadonnées.

La lecture du descripteur ne crée pas d'archive et ne modifie pas SQLite. La
restauration autorisée fige les octets authentifiés avant ouverture du
checkpoint ou changement de session. Les archives divergentes sont conservées
et refusées. Les octets du reçu sont hashés puis décodés depuis le même buffer.
Les anciens reçus et événements restent inchangés ; les contrôles ordinaires
de rejeu ne consomment pas ce fallback `RESTORATION_ONLY`.

La régression réelle et la portée des tests sont consignées dans
[la preuve de reprise](automation-session-recovery-evidence-20261005.json).

Chaque restauration exige sa propre autorisation explicite d'exécution
Blender. Les tests de `tests/test_returned_run_recovery.py` utilisent des faux
fichiers Blender et contrôlent les contrats portables ; ils ne prouvent pas
une réouverture native d'un vêtement.

Sur Windows, les accès aux archives utilisent les chemins étendus après
validation du confinement et des liens/jonctions. Cette conversion reste une
adaptation d'accès fichier : les chemins relatifs des reçus et les chaînes des
sessions ne changent pas. Elle couvre les lecteurs du journal et des preuves
natives, ainsi que les sources longues ; les empreintes communes incluent les
modules d'archivage et de preuve native. Le projet racine doit rester accessible
par le runtime existant. Les tests simulent aussi un hôte sans prise en charge
des chemins ordinaires longs ; ils ne remplacent pas le prochain essai Blender.
Voir [la correction Windows](automation-windows-archive-evidence-20261005.json).
