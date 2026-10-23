# Maillage synchronisé : intégration et preuve source67

Le profil explicite `SYNCHRONIZED_GRADED_V1` active la gradation des bords source
et le noyau à références de naissance permanentes dans les callers existants.
Son absence conserve le comportement historique. Les contrôles de bord et les
insertions intérieures partagent le plafond du composant ; les coûts restent
débités après rollback. Les bords des pièces suivantes gardent leur réserve.
Un refus du noyau conserve sa cause et ses coûts et ne peut produire `READY`.

Le [reçu](automation-synchronized-meshing-evidence-20261005.json) lie
**1,392 tests intégrés** en **197.602 s**, **14 contrats**
et le build local aux **559 fichiers** exacts du commit
`0f18f0b1e17748fc8f3723108904f2b3d3b51e5c`. La revue du raccord reproduit 223 tests et 62 sondes.
Les revues séparées du noyau, de l'enveloppe et des bords gardent leur périmètre.
La fixture du noyau est autonome et vérifie les octets source historiques.
Les ajouts documentaires de ce bilan suivent le snapshot logiciel testé.

L'essai portable réel couvre dix pièces et 24 raccords : 2 236 points de bord
deviennent 2 324 avec 88 contrôles. La revue compare exactement neuf champs
publics et les coutures, dont 26 932 flottants par leurs bits. Les cartes de
travail omises ne sont pas comparées. Les inventaires historiques avant/après
ne sont pas persistés ; les assertions du helper restent des observations en
mémoire. Son checkpoint précède les dernières écritures. Cette preuve ne vaut
pas attestation terminale Blender et n'exécute pas le nouveau caller natif.

Le clipping exact des triangles disjoints permet au nouvel essai du champ du
col de finir avec un motif mesuré : `INCOMPLETE`, plafond de 500 000 nœuds de
sortie épuisé, résultat compilé absent. Le host atteste cette issue ; il n'atteste
aucune qualification. L'analyse compte au moins 575 076 nœuds dans les seuls
intersections et patches du format actuel. Un format compact séparé est en
développement. La référence fraîche complète, les seuils et les caps actuels
restent conservés. Aucun nouvel essai automatique ne suit ce refus.

Le package local reste déclaré **0.7.0-rc.2**, avec portée de développement.
La campagne native du profil intégré, les sept autres pièces du nouveau
candidat, la présence physique de tous les points authored, les surfaces 3D,
les contacts et le placement restent à qualifier. L4 reste partiel et L5 non
admis. Les 15 textiles et la boucle, l'enfilage, Cloth, le fitting, les clips
et la revue artistique restent requis avant la préversion et l'installation.

Voir les contrats du [profil](synchronized-meshing-profile.md), des
[bords](boundary-gradation.md), de l'[enveloppe](meshing-envelope.md) et du
[noyau](bounded-pattern-meshing.md).
