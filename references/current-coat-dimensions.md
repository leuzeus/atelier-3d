# Réconciliation dimensionnelle du manteau — 5 octobre 2026

L'image originale est présente dans le projet composé, à
`references/original-triptyque.png`. Ses pixels ont été examinés et son empreinte
correspond au dossier. La planche éclatée et le découpage approuvé conservent leur
portée ; les annotations initiales de dimensions sont des hypothèses de départ,
pas une mesure de capacité des patrons actuels.

Le corps masculin accepté à 180 cm reste inchangé. L'intention est un manteau
ample porté sur un haut léger. Les cibles de marge restent 20 cm à la poitrine,
10 cm à la taille avant ceinture, 18 cm aux hanches, 6 cm au cou, 8 cm au haut
du bras et 7 cm au poignet. Pour les ouvertures du torse et du col, une enveloppe
spatiale de référence ne vaut pas une circonférence fermée de matière.

| Région | Corps mesuré | Donnée du patron actuel | Portée du résultat |
|---|---:|---:|---|
| Haut du bras gauche | 37,439902 cm | maximum transversal 45,439902 cm | Borne nominale de famille, correspondance exacte encore refusée |
| Haut du bras droit | 37,476989 cm | maximum transversal 45,476989 cm | Borne nominale de famille, correspondance exacte encore refusée |
| Poignet gauche | 17,395739 cm | bord distal de manchette 25 cm | Proposition de chemin homologue, marge nominale 7,604261 cm |
| Poignet droit | 17,441566 cm | bord distal de manchette 25 cm | Proposition de chemin homologue, marge nominale 7,558434 cm |
| Poitrine, taille, hanches | Corps accepté remesuré | Chemins actuels non admis | Provenance UV native à réconcilier et couverture ouverte à établir |
| Cou | 42,900103 cm | Deux lignes extrêmes du col évaluées | Aucune ligne entière ne correspond au plan du cou |

Dix des douze sections corporelles supplémentaires sont mesurées. Les deux
sections à l'épaule restent refusées pour contour ouvert ou branché. Les
enveloppes de main sont des projections géométriques conservatrices ; elles ne
qualifient pas le passage physique. La largeur maximale d'une manche et le bord
proximal de 29 cm d'une manchette ne deviennent pas une aisance portée au poignet.

Le compilateur source corrigé, exécuté en lecture seule sur les entrées exactes
V3, retourne deux propositions de chemins aux poignets et six diagnostics. Les
propositions restent `admissible_for_fit: false`, avec revue humaine de la
correspondance requise et qualification `NONE`. Le runtime MCP installé reste
`dev.2026100503` ; ce résultat ne prétend pas que le correctif y est chargé.

L'ancienne décision numérique est conservée avec son dossier d'origine. Le
raccordement au dossier composé actuel est une proposition non approuvée ;
aucune approbation historique n'est transférée silencieusement.

Le candidat natif du manteau reste `NEEDS_CORRECTION`, avec 10/15 textiles et
la boucle encore absente. Les défauts de placement visibles ne démontrent pas à
eux seuls un déficit de capacité des patrons. Les prochaines preuves portent sur
les chemins du torse, la couverture, le col et le haut des manches, puis sur le
placement admis avant Cloth. Aucun fitting n'est exécuté.

Preuves : [réconciliation actuelle](automation-current-dimension-reconciliation-evidence-20261005.json),
[candidat natif conservé](automation-coat-native-preparation-v2-evidence-20261005.json),
[correctif des guides de mesure](automation-measurement-guide-dispatch-evidence-20261005.json).

Après le correctif de lecture UV, le diagnostic source V3 produit aussi deux
propositions pour les hauts de bras : 45,204894 et 45,240336 cm de matière,
soit des différences nominales de 7,764992 et 7,763347 cm avec les sections
corporelles. La revue d'homologie demeure requise. Les trois chemins du torse
épuisent maintenant leur budget de calcul de 15 secondes chacun ; aucun chemin
complet ni capacité de torse n'est obtenu. [Preuves UV](source-uv-storage.md).

Le correctif des périmètres corporels conserve les résultats métriques Python
3.11 exactement et produit les mêmes nouveaux résultats sous Python 3.13.
L'ancien supplément reste intact et refusé pour identité de code périmée.
Un supplément séparé `body-region-supplement-current-v2.json` et une fiche
proposée V4 portent la nouvelle identité ; le descripteur V2 est effectivement
authentifié sous les deux runtimes. Le corps, les cibles, les dix sections
valides et les deux sections refusées restent identiques. La compilation
publique complète V4 et le fitting restent à exécuter.
[Preuves de portabilité](automation-body-region-portability-evidence-20261005.json),
[références V2 actuelles](automation-current-body-v2-evidence-20261005.json).
