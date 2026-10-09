# Partie ouverte des guides de membres

`SOURCE_SEWN_DOMAIN_V1` distingue la partie tubulaire réellement cousue d'un
prolongement ouvert du même patron. Le code dérive cette distinction des deux
bords d'une couture permanente unaire. Il ne dépend d'aucun nom de vêtement,
de manche ou de repère corporel particulier.

## Cause et correction

Le producteur historique transforme chaque largeur horizontale du patron en
une circonférence complète. Au sommet d'une tête ouverte, cette largeur diminue
fortement : le producteur referme alors la tête comme une extrémité de tube,
alors que les bords source n'y sont pas cousus l'un à l'autre.

La nouvelle carte conserve la loi historique dans le domaine des bords cousus.
Au-delà, elle conserve l'origine U et le rayon de la section terminale. La
frontière ouverte suit ainsi le patron sur le cylindre prolongé. Elle n'est pas
transformée en une nouvelle couture. Les faces source sont partitionnées aux
changements V pour ne pas interpoler au travers de deux lois différentes.

Le mode est explicite. La valeur historique ou l'absence de paramètre conserve
les sorties précédentes. Voir [le contrat et les refus](generic-anatomical-placement.md).
Les budgets portent sur la phase de génération des membres : ils ne constituent
pas une borne de temps globale pour les phases torse, couplage et contrôles.

## Expériences réelles avant intégration

Les deux coutures longitudinales couvrent V de 0 à 25,600655 cm. Les patrons
continuent jusqu'à 35 cm. Les sections terminales sont U=[0 ; 36] et
U=[−36 ; 0] cm. Ces valeurs viennent des sources conservées.

La partition seule réduit l'erreur d'interpolation aux anciens témoins, mais
révèle des déformations analytiques supérieures à 10 au sommet. Elle ne corrige
donc pas la carte. Le POC suivant combine la partition et la partie ouverte :

| Domaine, subdivision 8 | Gauche : étirements principaux | Droite : étirements principaux |
| --- | ---: | ---: |
| Partie ouverte | 0,999780–1,001798 | 0,999791–1,000752 |
| Tube cousu | 0,604934–2,085406 | 0,585661–1,759115 |

Aucun triangle de la partie ouverte ne sort de la plage de référence ±2 %
dans ce POC. Le tube reste largement hors de cette plage. Les observations
intérieures échantillonnées ne sont pas un certificat continu et aucune
qualification du vêtement n'est transférée de cette amélioration locale.

Conserver la même cible anatomique exige une nouvelle translation rigide de
5,72958 cm par rapport à l'ancienne carte. Les résidus des ancres sont nuls ou
inférieurs à 3 × 10⁻¹⁶ cm. La translation est explicite et enregistrée ; les
contacts doivent être remesurés. Les patrons, relations de couture, mannequin
et décisions humaines restent conservés.

## Captures et portée

Le replay du produit intégré `376c59882ddbad2353c7214049c9b0319a9def82`
construit les quatre guides de membres en 4,954 secondes ; génération et
mesures complémentaires prennent ensemble 6,563 secondes. Le budget partagé
de génération reste 120 secondes, 70 000 contrôles et 131 072 triangles. Le
résultat compte 26 116 contrôles et 51 584 triangles pour 80 sommets et
72 faces source. Il reste `PARTIAL_GUIDES`, sans admission du vêtement.

Les UV, triangles et XYZ des deux manches reproduisent exactement ceux du
POC. Les ancres anatomiques sont remesurées après translation. Les manchettes
conservent leur convention propre de bords distal/proximal ; elles n'ont pas
de prolongement ouvert. Leurs plages principales restent 0,9414–1,1742 à
gauche et 0,9484–1,1756 à droite, donc non admises. Leur nouvelle partition
ne permet pas de réutiliser une ancienne preuve de fitting.

Les reçus et cages du code produit sont sous
`program-sewn-domain-product-replay-v1/execution/`. Le refus préalable du
sandbox Windows est conservé séparément : il est survenu avant génération.
Le calcul produit a été exécuté une seule fois ensuite. Aucun état canonique,
patron ou corps n'a été modifié.

Les captures sont calculées à partir des coordonnées enregistrées et des
triangles natifs du corps opaque, sans Blender ni Cloth. Elles conservent le
même cadrage : face, dos, profil, trois-quarts et gros plans. Les candidats
refusés sont présentés avec leur statut.

Le replay du code intégré ajoute les quatre guides, dont les deux manchettes,
aux planches `program-sewn-domain-product-replay-v1/preview/before/` et
`preview/after/`. Neuf images sont conservées par série. Les séries
`details/before/` et `details/after/` ajoutent chacune neuf images pour les
gros plans des têtes et des manchettes ; leurs cadrages sont également communs.
Les quatre planches ont été affichées. Les vues montrent
encore le corps à travers les manchettes et des parties du tube ; les têtes
sont déployées mais ressortent au-dessus et à l'arrière des épaules. Il s'agit
d'une correction de la carte matérielle, pas d'un placement réussi.

La qualification logicielle du même commit termine avec **2 193 tests, aucun
SKIP, en 436,765 secondes**, et **14 contrats JSON**. Les sources de l'export
immuable sont inchangées après validation. Le reçu original du replay garde
son statut historique de suite complète en attente ; un reçu distinct
`program-sewn-domain-product-replay-v1/qualification-link.json` relie les
empreintes du replay et de la qualification terminée. Voir le
[manifeste de preuves](automation-placement-followup-evidence-20261008.json).
Ce lien qualifie le logiciel et ne change aucune admission du vêtement.

Fichiers sous `work/garment-automation-v1/program-limb-knot-partition-poc-v1/` :

- `preview/before/board-comparison.png` : carte historique ;
- `preview/after/board-comparison.png` : partie ouverte prolongée ;
- `sewn-domain-extension-v1/report.json` : métriques, source et attaches ;
- `findings.md` : expériences, coûts et limites.

Les vues montrent la tête de manche davantage déployée. Le tube reste
irrégulier, avec des zones occultées par le corps. Ces résultats sont des
guides de préparation, sans placement, contact ou fitting admis.

Le travail restant comprend la correspondance du torse depuis ses références
corporelles, les réserves et transitions régionales, la métrique du tube et
les raccords complets. Les quinze textiles et la boucle, l'enfilage, Cloth,
le drapé, les mouvements, la revue artistique et la préversion finale restent
à qualifier. Aucune nouvelle variante de coupe n'attend une décision humaine
dans ce lot. La prochaine revue visuelle du vêtement complet reste nécessaire.
