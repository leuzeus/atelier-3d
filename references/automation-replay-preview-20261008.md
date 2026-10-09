# Reprise logicielle et aperçu anatomique du 8 octobre 2026

Le placement du manteau reste **refusé**. Les corrections logicielles permettent
de reprendre le calcul et d'en voir les résultats intermédiaires ; elles ne
constituent pas une correction visuellement acceptée des épaules ou du col.

## Corrections vérifiées

- `path_direction: 1 | -1` distingue sens de parcours et phase d'une bande sur
  une courbe anatomique. La correspondance source du centre-dos du col conserve
  les 4 cm d'aisance déjà choisis et les coordonnées du patron.
- `studio_revalidate_source_adoption` authentifie les sources, leur ascendance
  et les décisions après changement de logiciel. Seules les empreintes des
  producteurs peuvent différer ; dossier et packages doivent se recalculer à
  l'identique. Les bases ancêtres sont réservées et les fichiers recontrôlés
  après écriture. Les preuves physiques ne sont pas revalidées.
- Le raffinement matériel calcule ses barycentres depuis les valeurs binaires
  exactes des sommets, puis arrondit une seule fois. L'ancien calcul arrondissait
  les produits avant leur somme et pouvait sortir un contrôle de sa droite
  source. Le contrôle strict de couverture reste inchangé.
- Les refus de géométrie conservent les indices et coordonnées de leur
  diagnostic dans l'enveloppe publique MCP.

Le commit `83723ab40eacef4806332a554469d5297c88417b` passe **2 127 tests** en
487,173 s, sans échec ni SKIP, et **14 contrats** dans un export Git figé.
La revue indépendante ciblée est close. Les deux manches réelles conservent
chacune 32 segments, 1 089 contrôles et 1 920 triangles lors du test matériel.
Ce test ne mesure pas leur placement contre le bras.

## Recalcul réel et aperçus

L'adoption du projet `execution-project` a été recalculée à l'identique avec le
code courant. Son epoch `19ca533d…`, ses composants et ses décisions restent
conservés. La révision canonique passe de 97 à 98 pour l'attestation seule.
Aucune opération Blender n'a été préparée ou exécutée dans cette reprise.

La compilation complète franchit le contrôle des manches, puis atteint le
budget de 60 secondes du couplage. Une variante de diagnostic distincte emploie
8 itérations, dont 4 rigides, et un plafond de 120 secondes. Les objectifs de
métrique et de raccord restent conservés. Elle produit les guides et le plan,
puis s'arrête avant les templates natifs : `PARTIAL_GUIDES`,
`PROPOSAL_INCOMPLETE`, `ITERATION_BUDGET_EXHAUSTED`.

L'écart maximal des raccords passe de 20,17 à 16,96 cm sur cet essai limité.
Les attaches anatomiques restent conservées, mais les déformations extrêmes
et les réserves corporelles sont insatisfaisantes. Le meilleur résultat retenu
provient de la phase de translations rigides. Aucune admission n'en découle.

Les 16 images actuelles sont des projections avec tampon de profondeur des
coordonnées enregistrées : dix pièces du manteau, corps accepté opaque, puis
compagnons « guides seuls ». Capuche, empiècements, ceinture et boucle ne sont
pas représentés sur cette planche. Une planche V5 séparée est marquée historique.
Les images actuelles montrent encore les occultations du torse et du dos et
les plis anormaux du col ; elles ne sont pas une simulation ni une nouvelle
capture de la scène Blender active.

## Diagnostic régional distinct

Sur les anciennes cages V5, les régions attestées sont `1=spine.upper`,
`20=upper_arm.right`, `21=upper_arm.left`, `17=head`. L'enveloppe limitée à la
région 1 omet des supports du haut du bras. L'union avec le bras du même côté
réduit les contrôles non résolus de 1 274 à 341 dans le même domaine, mais aggrave
les déformations médianes pondérées par l'aire source : 18,7 à 28,6 % et 20,4 à
30,4 % au dos ; 14,4 à 26,1 % devant à gauche, 14,6 à 23,9 % devant à droite.
Cette proposition reste refusée. La tête n'a pas été ajoutée à ces domaines.

Les sondes intérieur/extérieur sont des diagnostics séparés. Le corps est fermé
et orienté, mais des intersections sont observées hors du haut du torse. Les
votes et distances ne créent aucune qualification globale nouvelle du mannequin.
Il reste conservé tel qu'accepté.

## Consigne visuelle et suite

À la demande directe de l'utilisateur : afficher les captures au fur et à
mesure, **y compris les candidats refusés**, sans attendre une admission.
Prévoir face, dos, profil, trois-quarts et gros plans avant/après ; indiquer le
candidat, les pièces montrées et absentes, le statut et l'origine des images.
Les fichiers exacts examinés restent liés à leur manifeste. Les phases physiques
produiront leurs propres vues et vidéos lorsqu'exécutées.

La prochaine correction doit traiter la continuité et la métrique des guides
avec leurs supports corporels ; une projection indépendante ou une augmentation
de budget ne suffit pas. Le diagnostic causal du col et des triangles fortement
déformés est poursuivi avant un nouvel essai natif.

Le stage `0.7.0-rc.2.dev.2026100802` est préparé depuis le commit validé :
741 fichiers vérifiés. Il n'est pas installé ; le MCP connecté reste 0801.
Aucun redémarrage ni publication finale n'a été déclenché par cette reprise.
Le vêtement complet, l'enfilage, Cloth, le fitting, les mouvements et les revues
de coupe/artistique applicables restent des étapes distinctes à réaliser.

Voir [les reçus et fichiers exacts](automation-replay-preview-evidence-20261008.json).
