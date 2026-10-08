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

Les captures sont calculées à partir des coordonnées enregistrées et des
triangles natifs du corps opaque, sans Blender ni Cloth. Elles conservent le
même cadrage : face, dos, profil, trois-quarts et gros plans. Les candidats
refusés sont présentés avec leur statut.

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
