# Refus certain avant une admission métrique complète

Le solveur de récupération des guides peut refuser plus tôt un candidat dont
une déformation principale dépasse déjà les limites déclarées. Ce contrôle
économise des évaluations complètes répétées pendant les itérations. Il ne
produit aucune admission : en l’absence de témoin certain, le validateur
complet reste obligatoire.

## Calcul réutilisé

`a3d/guide_metric_solver.py` emploie directement `principal_stretches` de
`a3d/cloth_metrics.py`. Les triangles UV viennent de `face_sources`, déjà
contrôlé par le parcours de récupération, avec la correspondance par face
et les rotations cycliques prévues par ce service. Le parcours examine les
faces dans leur ordre canonique. Un témoin est certain uniquement si une
valeur finie est strictement inférieure à `min_stretch` ou strictement
supérieure à `max_stretch`. L’égalité ne constitue pas un refus.

Une géométrie non finie ou de taille incohérente, une correspondance ambiguë,
un calcul principal absent ou non fini renvoie au validateur complet. Les
angles, les aires, les petites arêtes et la topologie restent contrôlés par
ce validateur ; leurs calculs ne sont pas recopiés dans le raccourci.

## Sortie et limites conservées

Chaque résultat retourné reçoit une validation métrique complète, y compris
après un arrêt pour qualité UV immutable ou pour une borne de points fixes
impossible. Le résultat complet sert également au rapport métrique final,
dont la forme existante est conservée. Les contrôles de déplacement, de
trajectoire linéaire, de points protégés, de coutures permanentes et
d’immutabilité des entrées restent actifs.

Les budgets de temps, d’itérations, de pas, de déplacement et de résolution
linéaire ne changent pas. Le corps, les patrons et leurs seuils ne changent
pas. Aucun nouveau chronomètre n’est ajouté au parcours : les appels à
l’horloge fournie par le demandeur restent identiques. Une performance
n’est revendiquée qu’après mesure sur les entrées concernées.

`SOURCE_METRIC_RECOVERED` reste une observation géométrique de préparation,
avec `qualification: NONE`. Les contacts, Cloth, fitting et contrôles du
vêtement complet conservent leurs propres conditions d’admission.

## Vérification

`tests/test_metric_admission_fast_rejection.py` compare le résultat booléen
au validateur complet existant. Les cas comprennent le cisaillement invisible
aux seules longueurs d’arêtes, la compression, l’égalité exacte des seuils,
les défauts d’angle, d’aire, d’arête et de topologie, les données non finies,
la correspondance UV explicite, les rotations cycliques, les faces d’une
pièce non sélectionnée et l’absence de faces. Les candidats neutres et les
poses rigides valides doivent appeler le validateur complet.

Les tests comparent aussi les coordonnées, l’énergie, l’historique et la
décision finale avec le parcours antérieur sur un coupon simple et des
coupons couplés. Les entrées restent identiques. Les représentations double
et float32 sont comparées au même validateur ; cette comparaison portable
ne remplace pas une exécution native Blender.

La suite affectée comprend également les tests existants du solveur, des
métriques Cloth et des entrées de récupération. Le profil source qui a
motivé cette unité est conservé dans
`work/garment-automation-v1/program-metric-recovery-investigation-v1`.
Son témoin principal à la face 57 porte sur un candidat refusé ; il ne
qualifie aucun vêtement et ne prouve aucun gain sur une nouvelle exécution.
