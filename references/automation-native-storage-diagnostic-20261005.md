# Diagnostic de stockage natif V5 — 2026-10-05

L'essai numérique isolé V5 est **incomplet**. Il a conservé un diagnostic
`ALLOCATION`, sans fichier de résultat natif final. Le statut du calcul reste
`UNKNOWN_OR_UNATTESTED` : le nombre de pièces terminées et leurs rapports de
qualité ne sont pas attestés. Les calculs complets observés aux V2/V3 ne sont
pas transférés à cette exécution.

Le processus observé a terminé avec `exit 2` après 68,180 secondes, sous le
watchdog de 120 secondes. La seule capture native conservée est celle des
entrées : 59 877 octets. Le reçu hôte décrit un checkpoint de consommation ;
la fin de sa propre persistance demeure explicitement `NOT_ATTESTED`.

| Réservation codec au refus | Valeur | Plafond |
|---|---:|---:|
| Nœuds | 235 808 | 500 000 |
| Octets | 6 611 634 | 8 388 608 |
| Travail | 12 269 277 | 100 000 000 |
| Allocation | 237 891 893 | 268 435 456 |

Ces valeurs sont des réservations cumulatives. Elles ne constituent ni la
taille d'un payload sauvegardé ni une mesure de mémoire résidente. La taille
de la prochaine réserve rejetée n'a pas été rapportée ; une cause unique ne
peut pas être déduite de ce seul diagnostic.

Le premier lancement avait été refusé avant tout processus : le lanceur
attendait le snapshot du codec sous PF5, alors que la requête réutilisait le
snapshot PF4 exact. Une liaison de chemin explicitement revue a précédé
l'unique essai réel. Les deux observations et les anciens gels sont conservés.

La piste retenue est une sérialisation JSON avec échappement ASCII des
caractères, comptée exactement pour le packet encodé. Le texte Unicode doit
rester identique après parse ; les compteurs du DTO natif développé et son
hash conservent leur convention UTF-8. Les plafonds restent inchangés. Les
petites fixtures de cette analyse ne démontrent pas que le payload réel
tiendra ; le Unicode dense peut augmenter la taille encodée.

[Preuves et empreintes](automation-native-storage-diagnostic-evidence-20261005.json).
La lecture de contrôle est réalisée par l'auteur du gel d'observation ROOT ;
elle n'est pas une seconde revue indépendante du producteur. Aucun placement,
contact, Cloth, fitting ou vêtement complet n'est qualifié par ce diagnostic.
