# Qualification du diagnostic de montage 0.5.5

Blender 5.2.2 LTS, Windows, processus indépendants, sources et artefacts de tests
sur G:. Aucun Blender ni fichier du projet consommateur modifié.

## Reproduction

```text
python -B -m unittest discover -s tests -v
pwsh -NoProfile -File scripts/validate_contracts.ps1
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_placement_smoke.py
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_failure_smoke.py
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_smoke.py
```

Ces scripts n'ouvrent pas de scène utilisateur et écrivent sous `work/native-*`,
exclu de l'archive publique. Lire les JSON et logs ; le code de sortie seul ne
constitue pas la preuve. Le rendu natif avant Cloth a été ouvert et examiné.

## Résultats et limites

187 tests Python et 8 contrats distribués passent ; la configuration privée
est vérifiée séparément et reste exclue du package.

La nouvelle fixture contient deux patrons de manche effilés (largeurs 20/16 cm,
longueur 40 cm), deux coupons d'emmanchure et un collider fermé incliné de 35°.
Les panneaux sont triangulés à partir de leurs contours ; seul le collider est
une primitive auxiliaire. Les coupons décrivent un raccord annulaire synthétique,
pas un buste anatomique ni une coupe utilisable pour une robe réelle.

Le placement à plat présente 22 trajets de couture traversants et un écart maximal
de 24,4131 cm sur la couture longitudinale. L'enroulement cylindrique existant
réduit ces mesures à 0 trajet traversant et 3,9345 cm. Le taper laisse une ouverture :
aucun PASS local Cloth ni fitting n'est revendiqué par cette fixture.

Les inspections conservent base SQLite, mapping, mesh, repos, frame et sélection.
Rebuild conserve le package, le board et l'ancien mesh. Les dérives du collider et
Cloth actif sont refusés. Les tests d'échec évalué et de restauration vérifient le
rapport initial conservé, son SHA et l'absence de PASS local/admission full.
La régression physique précédente passe avec probes, local/full et freeze.

Le rapport expose les données nécessaires à la correction du placement réel.
Il n'identifie pas une cause confirmée de ses anciens échecs, ne constitue pas
une nouvelle preuve de solver, et ne prouve pas la robe réparée. Le retest natif
dans le projet consommateur reste NOT_EXECUTED pour cette version.
