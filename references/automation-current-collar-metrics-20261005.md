# Observation affine du champ expérimental du col — 5 octobre 2026

Le calcul est terminé et son résultat complet est sauvegardé. **48 des 192 faces
observées dépassent les bornes d'étirement.** Ce résultat localise un défaut du
champ expérimental ; il ne donne aucune admission de placement ou de fitting.
Les patrons approuvés et le mannequin masculin à 180 cm restent identiques.

## Résultat mesuré

| Contrôle affine | Faces |
|---|---:|
| Évaluées | 192 |
| Respectant les deux bornes | 144 |
| Dépassant la borne haute | 48 |
| Échouant également à la borne basse | 17 |

Les 48 faces concernées portent les IDs `carrier:f0` à `carrier:f47`.
Les bornes utilisent les valeurs binary64 de 0,9 et 1,1, mises au carré
exactement. Les Jacobiennes, matrices de Gram et contrôles PSD sont conservés
en fractions rationnelles ; aucun epsilon ne transforme une violation en réussite.

La provenance compte 15 sommets / 13 faces source, 125 sommets / 192 faces du
porteur et une référence fraîche de 743 sommets / 1 098 triangles. Les 751
samples, sept marks et sept relations sont conservés. Cette référence vient
de `program-joint-neckline-cage-preflight-v1/original-full-cage-reference.json`.
Son ancienne préparation auxiliaire avait refusé la qualité des triangles
avant optimisation. Elle est distincte des essais natifs V2/V3 dont les arrays
complets n'ont pas pu être sauvegardés.

## Calcul et persistance

Une seule compilation fraîche et une seule observation partagent le même budget,
avec une échéance de 60 s. Le checkpoint du reçu métrique est à **48,672 s** ;
le contrôle après sauvegarde et hash est à **48,938 s**. Le processus observé
termine en **49,064676 s**, sous son watchdog hôte de 75 s. Ces instants ont
des portées distinctes ; aucun temps après le flush n'est attesté.

Le fichier complet compte **339 429 octets**. Le stdout physique compte
**4 679 octets UTF-8**, avec un LF exact. Le total déclaré est **344 108 octets
et 6 412 nœuds**, sous les plafonds conservés de 8 Mio et 500 000 nœuds.
Les **349 fichiers protégés** sont identiques avant/après. Aucun retry,
nouveau calcul natif ou appel Blender n'est effectué par la lecture du résultat.

Les [preuves liées au candidat](automation-current-collar-metrics-evidence-20261005.json)
conservent la revue du pilote, celle du lecteur hôte, les sorties et leur revue
de cohérence. Le refus du lecteur V1 reste conservé ; seul son successeur V2
revu a exécuté cet essai.

## Portée et suite

L'observation mesure les Jacobiennes fournies par l'état fraîchement compilé.
La lecture indépendante vérifie les Gram et PSD à partir de ces Jacobiennes ;
elle ne reconstruit pas les Jacobiennes depuis le domaine. Les domaines ne sont
pas revalidés par cette étape. Les contacts, contraintes 3D, Cloth, drapé,
mouvement et fitting restent non qualifiés.

La prochaine correction doit partir de la localisation de ces faces et d'une
référence complète contrôlée. Elle conserve les bords source, les crans, les
supports déclarés, le corps et les patrons approuvés. Un candidat corrigé
reste soumis aux gates de métrique, couverture et contacts avant Cloth.
Les 144 faces conformes ne constituent pas une acceptation du col ou du manteau
complet de 15 pièces textiles et une boucle.
