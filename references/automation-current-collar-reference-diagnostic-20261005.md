# Référence actuelle du col : refus conservé

L’essai unique utilise le placement rigide du col du commit `65f8965`, les patrons approuvés et le corps masculin accepté. Il s’arrête avec un `StudioError` après 30,078 s, sans référence complète ni reçu du producteur. Le calcul reste `UNKNOWN_OR_UNATTESTED` ; qualité, métriques et comptages ne sont pas attestés.

Le lecteur hôte a été corrigé et revu avant le lancement : 23 tests et 21 sondes passent, dont les cas de retour chariot et de seconde attestation incomplète. Ces contrôles concernent la collecte, pas la géométrie.

| Observation réelle | Résultat |
|---|---|
| Processus enfant | PID 82784, code de sortie 2 |
| Durée observée | 30,0779436 s, sans arrêt du watchdog |
| Sortie stdout | 169 octets physiques, un LF ; classe `StudioError` seule |
| Sortie stderr | Vide |
| Référence complète / reçu producteur | Absents |
| Préservation | Cartes avant/après identiques ; 824 entrées recontrôlées |
| Admission | Aucune |

La revue indépendante confirme ces observations. Le diagnostic du producteur a omis le message et la phase de l’exception ; plusieurs contrôles peuvent lever cette classe. Aucune cause géométrique précise n’est déduite de ce refus.

La prochaine opération prépare un compte rendu borné avec le message, la phase et la pièce lorsque ces informations sont réellement disponibles. Elle conserve le budget de 60 s et n’ajoute aucune tolérance de géométrie. Les données sources et les deux échecs de revue du lecteur restent conservés.

[Preuves du refus et de sa lecture indépendante](automation-current-collar-reference-diagnostic-evidence-20261005.json). La mesure du nouveau champ du col, les contacts et le fitting restent à réaliser.
