# Récupération métrique et contacts d'une pièce

Ces helpers scientifiques génériques conservent le code de l'expérience locale
du col. Ils sont versionnés pour permettre sa reproduction et la préparation
du couplage, mais **ne sont pas inclus dans l'archive du plugin**. Le runtime
public reste fondé sur Python standard ; ce dossier exige un environnement
scientifique existant avec NumPy et SciPy. Il n'installe aucune dépendance.

Les commandes prennent une demande JSON structurée dont les références
d'entrée portent les empreintes SHA-256. Les fichiers source, la pièce, les
attaches, le corps, les budgets et le dossier de sortie sont explicites :

```powershell
python -B experiments/anatomical-placement/solve_piece_metric.py --request demande-matiere.json
python -B experiments/anatomical-placement/solve_piece_contact.py --request demande-contacts.json
python -B -m unittest discover -s experiments/anatomical-placement -p 'test_*.py' -v
```

Les demandes sont des entrées locales de développement préparées à partir des
reçus du projet. Le second outil vérifie notamment l'audit de contact d'entrée,
les références du corps et l'empreinte du noyau géométrique chargé depuis le
checkout explicitement sélectionné. Il ne constitue pas une interface serveur
d'importation de demandes tierces.

`solve_piece_metric.py` conserve le domaine UV, les triangles et les contrôles
fixes, avec factorisation QR normalisée. `solve_piece_contact.py` ajoute des
contraintes scalaires liées aux témoins des triangles du corps ; les métriques
et contacts sont remesurés aux positions réellement proposées. La réserve
physique, la bande d'activation et la marge de calcul restent trois valeurs
distinctes. Les budgets de mémoire refusent les grandes matrices denses.

Les helpers ne contiennent ni nom de vêtement ni coordonnées propres à ce
manteau. Leur domaine démontré est une pièce comportant moins de 1 024
variables libres dans le solveur dense de contact. Les grandes pièces et
plusieurs panneaux couplés nécessitent un autre traitement validé. Les coutures
avec d'autres pièces, les auto-contacts, Cloth et le fitting ne sont pas couverts.

Les deux premiers fichiers sont des copies identiques aux snapshots du calcul
de contact du candidat 06 et du helper métrique durci. Le helper
`solve_corner_contact.py` conserve également le calcul revu d'une égalité de
coin découlant des coutures source, sans soudure des UV ou de la topologie.

Les outils suivants sont des expériences de couplage, dont les cas réels
restent refusés. Ils ne constituent pas un parcours de production :

| Fichier | Portée et limite actuelle |
|---|---|
| `propose_partner_rigid.py` | Propose une rotation propre et une translation depuis les supports cousus, puis mesure matière, déplacement original et contacts. Le cas réel dépasse la limite de déplacement. |
| `prepare_sewn_band.py` | Prépare un bloc matériel avec halo numérique explicite et teste des conditions nécessaires. Ne fige que les supports unitaires exacts ; les autres restent explicitement non traités à ce stade. |
| `solve_sewn_band.py` | Résout un bloc préparé et réévalue la pièce entière ainsi que tous ses supports au col. La matière du devant intérieur réel reste refusée. |
| `sparse_metric_factor.py` | Propose un pas LSMR avec variables fixes éliminées, colonnes normalisées, budgets et résidus enregistrés. Pas de solveur conjoint validé ni de qualification des triangles fins. |

Les 25 tests numériques passent sur Python 3.11 ; ils sont distincts de la
suite standard du plugin. L'évaluation scientifique exige les demandes et les
reçus exacts ; des tests unitaires réussis ne remplacent pas les résultats
physiques, les contrôles du vêtement ou les refus de ces expériences.
Les reçus, les refus et les limites sont décrits dans le
[bilan du placement](../../references/automation-joint-placement-20261008.md).
