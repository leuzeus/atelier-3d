# Contraintes actives et raccords anatomiques

Le commit `43013b770e2eba031feda8fdb2862bfdcc7307fa` ajoute une projection
optionnelle de la direction du solveur sur les contraintes principales actives.
Il passe 2 173 tests sans SKIP en 440,438 secondes et quatorze contrats sur un
export Git immuable. Cette qualification est logicielle : le manteau reste
non admis et aucune opération Blender n'a été exécutée pour ce lot.

## Premier blocage corrigé, convergence encore insuffisante

La recherche historique diminuait bien son objectif, mais ses quatorze essais
aggravaient un triangle du dos déjà à sa borne inférieure. Diviser cette même
direction ne pouvait pas résoudre la contrainte. Le mode explicite
`ACTIVE_PRINCIPAL_CONE_V1` conserve les attaches, projette la direction, puis
applique les enveloppes non linéaires et la limite de déplacement existantes.
Le mode historique reste inchangé quand cette option est absente.

Le replay réel conserve les entrées du diagnostic sans enveloppe régionale,
huit itérations matière, quatre translations rigides et 120 secondes. Il
retourne une proposition en 92,875 secondes, avec le statut
`PROPOSAL_INCOMPLETE` et l'arrêt `ITERATION_BUDGET_EXHAUSTED`.

| Observation | Avant | Après |
| --- | ---: | ---: |
| Énergie de déformation matière | 29,51249 | 29,37783 |
| Écart maximal de couture | 17,09813986 cm | 17,09813971 cm |
| Étirement maximal de la manche droite | 16,65264 | 16,62966 |
| Résidu des quinze contrôles anatomiques fixés | 0 cm | 0 cm |

Seul le premier pas matière est accepté, à 1/512. Les sept recherches suivantes
échouent. La réduction d'énergie de 0,456 % n'est pas une correction visible
du placement. Les UV et les triangles source sont identiques ; aucune nouvelle
aisance ou modification du corps ne résulte de l'essai.

Le second blocage est localisé : après ce premier pas, le triangle 17 878 du
dos droit s'écarte d'environ 6 × 10⁻¹⁰ de sa borne et sort de l'ensemble actif.
Il n'a pourtant pas assez de marge pour accepter le plus petit pas suivant.
La sélection des contraintes doit donc prendre en compte le déplacement
proposé, sans confondre cette sélection avec une tolérance physique élargie.

Le correctif suivant, `f85080c`, conserve les identités des bornes réellement
violées et recalcule leurs gradients courants. Les 49 tests ciblés et la revue
indépendante passent. Son replay depuis un export immuable termine en
90,953 secondes : six pas matière sur huit sont acceptés. L'énergie matière
atteint 29,11170, contre 29,37783 sur le candidat 43013b7. L'écart maximal de
couture reste à 17,09813936 cm. Le déplacement maximal par rapport à ce dernier
candidat n'est que de 0,001998 cm, soit environ 0,02 mm. Les quinze contrôles
fixés gardent un résidu nul. La progression du solveur est vérifiée ; le
placement demeure insuffisant, sans admission.

Ce second reçu est sous `program-observed-constraints-replay-v1/`. Il indique
explicitement la portée des tests ciblés au moment du replay ; la qualification
complète doit référencer le commit intégré exact.

Les reçus et cages exacts sont sous
`work/garment-automation-v1/program-active-metric-product-replay-v1/execution/`.
Le replay reprend les cages avant projection régionale pour isoler le solveur ;
il ne remplace pas la compilation publique refusée à la révision 100.

## Correspondance col–torse

Les six raccords permanents source fournissent des cibles communes pour les
bords du col, du torse et du devant intérieur. Le diagnostic trouve 198
événements de frontière et six cohortes de jonction cohérentes, sans moyenne
des coins. Les treize attaches anatomiques existantes du col sont conservées.
Il n'ajoute aucune attache et ne déplace aucune surface textile.

Les bords initiaux sont éloignés de leurs correspondances de 4,79 cm au dos,
6,73 cm aux devants et 9,10 cm au devant intérieur. Les courbes cibles seules
ne suffisent toutefois pas : la mesure de leurs 192 segments contre le corps
trouve 27 segments à moins de la réserve de 0,3 cm. Le minimum est 0,23078 cm.
Aucune intersection de surface n'est détectée sur ces segments, ce qui ne
constitue pas une preuve globale d'extériorité ou de fitting.

Fixer toutes ces frontières en l'état rendrait la réserve impossible à
satisfaire. Leur ajustement doit être conjoint, conserver les correspondances
source et les attaches existantes, et être remesuré avant un champ intérieur.
Une courbe cible n'est ni une surface textile construite ni une nouvelle
attache anatomique admise.

Le traçage retrouve une graine native pour les quatre points dont le rayon
rencontre plusieurs nappes. Le point fixe du dos gauche, par exemple, est relié
par sa couture au segment corporel `[7458, 9517]`, puis à la face 7808 dans la
région déclarée. La reconstitution de sa cible diffère de moins de 2 × 10⁻¹⁵ cm.
Le normaliseur vérifiait ces incidences mais les omettait de sa sortie.

Le commit `d0f0d7d` conserve désormais les incidences vérifiées et leurs
identités, sans choisir une nappe. Vingt tests et la revue indépendante passent.
Le replay du trajet réel du cou garde exactement la même empreinte de
coordonnées qu'en 43013b7. Les fichiers comparés sont dans
`program-native-incidence-transport-v1/`. La continuation de surface depuis ces
graines reste à implémenter sous un domaine explicite ; une proximité ou un
nombre d'arêtes traversées ne constitue pas une correspondance anatomique.

Les planches de frontières actuelles en bleu et cibles en rouge sont sous
`program-portable-anatomical-0802-v2/preview/collar-boundary-targets-v1/`.
Les observations sont dans `collar-boundary-targets-v1/report.json` et
`collar-boundary-target-clearance-v1/report.json` du même dossier de travail.

## État de livraison et reprise

La scène et le mannequin accepté restent conservés. Le runtime connecté reste
`dev.2026100801`. Le stage antérieur 0802 n'inclut pas ces corrections ; aucune
installation, relance, publication finale ou exécution native ne découle de
cette qualification logicielle.

Les captures montrent aussi les candidats refusés avec le corps opaque. La
correction de la couverture régionale, de l'interpolation des manches et du
placement anatomique reste ouverte. Les quinze textiles et la boucle,
l'enfilage, Cloth, le fitting, les mouvements, la revue artistique et la
préversion finale ne sont pas qualifiés. Aucune nouvelle variante de coupe
n'attend de validation humaine dans ce lot.
