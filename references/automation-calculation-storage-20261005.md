# Calculs et stockage — bilan du 5 octobre 2026

Les tests logiciels, l'exécution d'un calcul et la conservation de sa sortie
sont des preuves distinctes. Les capacités ci-dessous restent de qualification
`NONE` ; elles n'admettent pas encore le manteau complet. Le
[reçu lié aux artefacts exacts](automation-calculation-storage-evidence-20261005.json)
conserve leurs SHA et leur portée.

| Unité | Preuve disponible | Ce qu'elle établit |
|---|---|---|
| Stockage compact exact | 129 tests, 15 sondes et 12 résultats V1 complets exacts ; commit `7b703b5` | Conservation du champ fourni et comptabilité cumulative, sur fixtures ; aucun col réel qualifié. |
| Métriques affines privées | Commit local `57109e07b0e448badaf5a6cf4eae011ab50bcd7a`, 92 tests et neuf sondes de revue | Jacobien/Gram/PSD exacts sur état interne frais ; aucun contrôle implicite du domaine, déplacement ou contact. |
| Profil natif synchronisé V2, essai réel | `MESH_BUILD_COMPLETED_ONLY`, puis `INCOMPLETE_OUTPUT_BUDGET` | Le calcul atteint sa frontière terminale ; le payload complet et les rapports de qualité par pièce ne sont pas sauvegardés. |
| Col compact V2, essai portable réel | `PORTABLE_TRIAL_TERMINALLY_ATTESTED`, sortie complète sauvegardée | Compilation unique et stockage compact sur les données réelles du col ; aucune qualification de placement, métriques ou fitting. |
| Profil natif V3, essai réel | Même refus `INCOMPLETE_OUTPUT_BUDGET` après conversion one-pass | La correction de comptage seule ne suffit pas à conserver le payload ; la qualité par pièce reste absente. |

## Métriques : une unité interne bornée

Le [module métriques](material-surface-metrics.md) reçoit directement l'état
fraîchement compilé du caller et son vrai budget field existant. Il ne recapture
pas les données, ne recompile pas les domaines, n'ouvre pas une horloge et ne
remet aucun compteur à zéro. Son noyau réutilise les helpers historiques exacts
du Jacobien et des tests PSD, aux bornes binaires 0,9/1,1 sans epsilon.

Les 92 tests ciblés comprennent 18 nouveaux, 43 tests champ et 31 tests compact.
La revue indépendante ajoute neuf sondes et douze cas numériques ; aucun
finding bloquant n'est conservé dans cette portée. Les bytes du module sont
liés aux observations et contrôlés avant/après la finalisation. Le reçu reste
le checkpoint du packer avant les guards de retour ; ces guards utilisent la
même deadline et ne prétendent pas fournir un timestamp postérieur au retour.

La fraîcheur et les domaines de l'état restent à garantir par le caller.
Displacement, pas, appuis et contacts sont `NOT_ASSESSED` ; contraintes 3D,
simulation et fitting ne sont pas qualifiés. Le commit metrics est local et
n'est pas encore poussé au moment de ce bilan. Les tests ciblés ne sont pas une
suite intégrée du nouveau commit ou une installation.

## Stockage : conserver exactement sans confondre avec l'admission

Le [format compact](material-surface-compact.md) publié en commit `7b703b5`
conserve les parents rationnels, les références complètes et la provenance
opaque. Les coûts de deux sorties et les refus restent cumulés. Les 12 DTO V1
complets sont reproduits exactement sur fixtures ; la consommation publique
V1 d'un compact n'est pas implicite. Le build source67 au commit `0f18f0b`
précède compact et metrics et ne valide donc pas ces ajouts.

Le préflight col compact V2 et son helper host sont revus séparément. Les
findings précédents restent gelés : le PASS module ne peut remplacer la revue
du pilote, et les hashes d'inputs du reçu host doivent être liés aux données
réellement sauvegardées. Les revues corrigées ne qualifient que ces bindings
et les petites fixtures. L'essai réel suivant dispose de ses propres preuves.

## Col compact V2 : compilation et stockage réels terminés

Le résultat complet est sauvegardé avec le SHA
`65f6e1e2eab0a3b08060a02958a576663ce7e2b105a65c0bbc5f4f17c690f1b7`
et 7 171 072 octets, dont le LF final. Le host atteste
`COMPILED_TEST_ONLY / NONE` après une seule compilation sur le même budget.
Les 661 fichiers protégés avant/après sont identiques. Aucun Blender n'est
exécuté pour cette campagne portable.

Les données conservent 15/13 sommets/faces source, 125/192 pour le porteur,
la référence fraîche complète 743/1098, 751 samples, sept marks et sept
relations. Les tables géométriques comportent 586, 5 178 et 5 526 lignes.
Le ledger cumule 1 922 721 paires et 117 830 opérations de fractions, sans
hausse des plafonds ni remboursement.

Le checkpoint après lecture/hash du fichier, avant encodage de l'attestation,
est à 51,625 s sous l'échéance de 60 s ; le lancement host prend 51,764725 s
sous watchdog 75 s. Le ledger compte 267 903 nodes et 7 173 226 octets,
incluant résultat/LF et attestation JSON+LF. La lecture exacte du log révèle
une seule ligne JSON terminée par CRLF : l'attestation est débitée à 2 154
octets, le pipe/log en contient 2 155. Le résultat plus stdout physique totalise
donc **7 173 227 octets**, soit un octet de plus que le ledger. Le SHA de stdout
est `47bcd4c3b6320c52aae65143f630d829c393f501f2152a12b40ad91cad18975e`.

Le finding de transport reste ouvert : la compilation et le fichier complets
sont conservés, et l'attestation du helper V2 a été reçue ; aucun PASS global
d'exactitude des octets transportés n'est accordé. La traduction de fin de ligne
Windows est une explication cohérente avec le CRLF observé. ROOT prépare une
correction distincte de sortie binaire et du contrôle host ; les artefacts
gelés, patrons, calculs et caps restent intacts.

La compilation/stockage ne donne aucune admission de domaine UV, des cassures
du champ 3D ou du placement. Métriques, barres/contraintes, contacts, Cloth,
drapé, fitting et décision artistique restent non qualifiés ou non exécutés.
Le nouveau module metrics n'est pas intégré à cet essai. Le résultat précédent
V1 incomplet est conservé ; il ne devient pas rétroactivement un succès.

## Essai natif V2 : calcul observé, sortie complète absente

L'essai réel emploie le snapshot source67 exact et une instance Blender isolée.
Le dernier checkpoint natif est à 53,580428 s sous son budget local de
capture/calcul de 90 s ; le lancement externe prend 59,844085 s sous watchdog
120 s. Ces durées ont des origines et portées distinctes.

Le reçu conserve les compteurs de travail des dix pièces préparées, les hashes
d'inputs avant/après identiques et l'état `MESH_BUILD_COMPLETED_ONLY`. La
persistance host refuse avec `HOST_OUTPUT_NODE_OR_DEPTH_BUDGET`, puis classe la
preuve `INCOMPLETE_OUTPUT_BUDGET`. Aucun payload complet n'est sauvegardé. Cette
raison groupée ne permet pas d'affirmer une cause unique sans payload complet ;
elle n'est pas une impossibilité du patron. Les rapports de qualité par pièce
étant absents, leurs angles et gates finaux ne sont pas déduits des compteurs.

L'essai réel V3, après conversion one-pass, atteint lui aussi
`MESH_BUILD_COMPLETED_ONLY`, puis le même refus host groupé. Son checkpoint
natif est à 53,346502 s et son lancement à 59,094219 s. Il conserve source67,
les dix IDs observés et les compteurs essentiels de 28 CDT, 18 remesh et
220 insertions ; les hashes d'inputs avant/après sont identiques. Les arrays
et rapports de qualité complets restent absents. Cette égalité de compteurs
ne prouve pas à elle seule des maillages complets identiques.

La correction de comptage/serializer n'a donc pas suffi. Une représentation
compacte native est à examiner dans une unité distincte, sans conclure à une
cause unique du refus ou à une impossibilité des patrons. Les deux essais
réels restent conservés. Aucun retry automatique, hausse de plafond,
modification de patrons ou de corps ne découle de ces résultats.

## Gates produit encore ouvertes

Les preuves historiques et portables gardent leur candidat et leur portée.
Les surfaces réelles, les contraintes, le placement, les contacts, Cloth,
le drapé, l'enfilage et le fitting restent à mesurer/admettre
sur le candidat exact. L'acceptation finale des 15 textiles et de la boucle,
les mouvements, la revue artistique et le package livré restent distincts.
Une nouvelle préversion et installation ne sont pas réalisées par ce bilan.

Les prochaines étapes sont la correction séparée du transport stdout et
l'examen d'un stockage compact natif, puis les contrôles réels du champ et
du vêtement. Aucun statut logiciel ou compteur de calcul ne leur donne un
PASS implicite.

## Mise à jour : frontière stdout corrigée et vérifiée sur le col réel

Le nouvel essai V3 conserve la compilation complète et ses entrées sans augmenter
les plafonds. Il passe ses contrôles de persistance et de transport : les
**2 165 octets physiques de stdout** correspondent au débit déclaré, avec un LF
binaire exact. Les **267 903 nœuds et 7 173 249 octets** agrégés incluent le fichier
de résultat et cette attestation. Les 1 021 fichiers protégés restent identiques
avant/après. Le col V2 et son écart CRLF restent conservés, sans reclassement.

Le checkpoint terminal V3 est à **51,578 s**, avant émission physique ; le processus
observé termine en **51,719456 s** sous son watchdog distinct. Les 743 sommets et
1 098 triangles de référence, 125 sommets / 192 faces du porteur, 751 samples,
sept marks et sept relations sont conservés. Une erreur ROOT de hash d'argument
a été refusée avant le processus de calcul et la création de la sortie ; elle est
conservée séparément. La commande corrigée lance un seul calcul.

Le [reçu V3](automation-current-collar-transport-evidence-20261005.json) lie les
48 tests du pilote, ses quatre sondes indépendantes, les six sondes du lecteur
de transport et les artefacts réels. Il lie aussi la CI logicielle réussie sur
Windows 3.11 et Ubuntu 3.13 au commit `06c1cf2` ; son nombre de tests n'est pas
extrait des logs fournisseur. Cette CI ne qualifie pas le vêtement.

Le transport est corrigé pour cet essai. Les métriques d'étirement du col réel,
les contraintes, les contacts, le placement et le fitting restent ouverts.
