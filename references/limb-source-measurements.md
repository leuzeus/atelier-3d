# Régions corporelles préparées et capacités nominales des manches

Ces deux capacités lisent des sources structurées. Elles ne changent ni le
corps approuvé, ni les patrons, ni les cibles d'aisance. Aucune mesure de matière
ne devient un fitting accepté et aucune enveloppe de main ne devient un tour
anatomique.

## Préparer les régions corporelles

`a3d.body_region_policy.build_body_region_policy(profile, geometry, triangles,
adapter, source_geometry, refs, options)` prépare le contrat
`body-region-sections`. Les options sont décrites par
`schemas/body-region-policy-options.schema.json` : régions upper/forearm,
côtés, fractions et domaine, axe de référence du plan, présence des enveloppes
de mains, tolérance numérique et budgets sont tous explicites.

Le générateur remonte aux appartenances `region_to_bone` de l'adaptateur
anatomique exact. Les contours de membre utilisent le domaine complet du même
côté upper_arm + forearm + hand. Les mains conservent uniquement leurs propres
appartenances, paume et doigts inclus. Les axes proviennent des anneaux source
épaule/coude/poignet et du centre de paume sourcé. Aucune coordonnée de vêtement
ou classification homme/femme ne sert à fabriquer un repère.

L'adaptateur conserve son empreinte métrique originale. La variante doit garder
les faces, régions et identités de sommets. Les repères de la variante sont
comparés aux centroïdes de leurs sommets source ; le rapport expose le résidu et
la borne de représentation float32 des sommets natifs en mètres. Cette borne
numérique ne constitue pas une tolérance anatomique ou physique.

Le résultat est `BODY_REGION_POLICY_PREPARED_NOT_MEASURED`. Les données absentes
produisent `NEEDS_DATA`, les incohérences de source sont refusées. Le générateur
portable ne vérifie pas le journal natif : l'intégration publique doit vérifier
les SHA des fichiers et l'origine canonique prepare_body_target ou
introduce_body_target avant d'appeler la mesure. Le consommateur authentifié
reste `measure_project_body_regions` puis `body_region_descriptor`.

`prepare_project_body_region_policy(project, options_path, profile_ref)` assure
ce chaînage pour préparer les entrées en lecture seule. Il retrouve le reçu de
l'opération terminée dans SQLite, vérifie les fichiers natifs et le contexte
exact d'introduction lorsqu'il existe, puis dérive les références de
l'adaptateur et de la géométrie originale depuis ce reçu. Les seules entrées
client sont le profil exact et les options explicites ; un wrapper signé ou une
preuve ordinaire ne remplace pas l'origine native. Le résultat conserve
`PREPARED_NOT_MEASURED`, l'origine, le contexte et les options exactes. Il ne
crée aucun événement SQLite ni approbation.

Une dérivation en lecture seule du mannequin principal a reproduit exactement
la politique existante : quatre régions et deux enveloppes de mains. Le reçu
`program-main-body-region-policy-proposal-v1/receipt.json` conserve les
empreintes des sources et de SQLite inchangées. Cela prouve la préparation
automatique des entrées, sans transférer l'acceptation corporelle ou de fitting.
Le reçu v2 de cette campagne vérifie également la façade canonique, liée à
l'événement natif 47 d'introduction du corps dans le laboratoire principal.

## Borner les chemins de matière

`a3d.fit_capacity_bounds.transverse_capacity_bound(compiled, piece_id)` accepte
une seule couture permanente unaire underarm-front/underarm-back, avec
orientation reverse, dans une manche ou manchette sourcée. Chaque chemin est
un segment matériel entre deux fractions homologues de longueur d'arc ; la
couture le ferme sans ajouter de matière.

L'union des ruptures des deux chaînes partage le domaine en cellules. Les deux
extrémités y sont affines. Le maximum de leur distance est aux extrémités de
chaque cellule ; le minimum est obtenu analytiquement par projection sur la
différence affine. Le code contrôle également que la famille entière reste
dans le patron simple : il partage chaque cellule aux contacts avec les sommets
du contour, puis contrôle les chemins critiques et chaque intervalle ouvert.
Il n'utilise ni boîte englobante, ni somme des couches, ni valeurs de coupe
supplémentaires.

La portée est `NOMINAL_TRANSVERSE_CAPACITY_BOUND`, à étirement matériel nominal
nul. Cette famille ne qualifie pas toutes les sections possibles du vêtement
porté. La concordance native de la couture, l'homologie complète au corps, les
conditions matière, l'enfilage et le fitting restent à vérifier.

`project_capacity_bounds` recompile le dossier actuel avant de mesurer. Pour un
signal corporel, il exige la politique et le supplément exacts, authentifiés et
remesurés ; une enveloppe conservative de main est refusée comme tour corporel.

Sur les sources actuelles, les deux manches donnent 29 à 36 cm et les deux
manchettes 25 à 29 cm. La proposition v2 utilise le supplément corporel v3 : les
sections médianes des bras sont 37,439902 et 37,476989 cm. Les deltas nominaux au
maximum de 36 cm sont donc -1,439902 et -1,476989 cm. Ces signaux justifient une
revue de la capacité source pour le manteau ample ; ils ne prouvent aucune
impossibilité physique et ne définissent aucune cible numérique d'aisance.

Les propositions v1 et v2 sont conservées séparément dans
`program-production-main-v1/preparation/limb-capacity-bounds-proposal-vN.json`.
La v1 ne réutilise pas le supplément corporel périmé ; la v2 référence le
supplément v3 réellement remesuré. Aucun patron ni corps n'a été modifié.
