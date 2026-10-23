# Distinguer un probe raté d'un vêtement non exécuté

Avant l'essai local du vêtement, `simulate_sewn(scope=local)` exécute les probes
gravité, couture et contact dans une scène séparée. Leur résultat décrit le
mécanisme synthétique sous les paramètres physiques de la recette ; il ne
qualifie pas le vêtement. Un probe peut légitimement échouer selon le rapport
force/rigidité. Le rejet ne prouve pas un bug Cloth ni un faux positif.

En cas d'échec, lire `failure.json`, puis appeler `inspect_sewing_failure` via
le code exact de `studio_blender_operation`, avec le composant et le répertoire
`attempt-*`. L'inspection reste possible pendant pending et après restauration.

- `execution_stage=backend_probe` situe le rejet avant l'essai du vêtement.
- `backend_probe_simulation=FAIL`, `garment_simulation=NOT_EXECUTED` empêchent
  de transférer au vêtement les défauts observés sur un coupon.
- `probe.case`, `profile`, `mass_input`, `mesh_limits`, `limits`, `colliders`
  et `supports` décrivent le mécanisme exécuté. Les supports sont les pins du
  coupon synthétique, pas ceux des panneaux du vêtement. `executed` conserve
  les paramètres réellement observés dans Blender ; `final_quality` est présente
  seulement si ce contrôle a été atteint.
- `requested_phase_frames` décrit la recette du vêtement ; `configured_frames`
  décrit le probe. Les durées existantes restent 12 images pour gravité/contact
  et 24 pour couture. `frame` et `frames` conservent l'évaluation réellement atteinte.
- `mapping_domain=synthetic_coupon` concerne positions, rest, faces et indices
  de la géométrie du probe. Package, mapping et placement au niveau parent lient
  la demande du projet ; ils ne font pas du coupon une partie du vêtement.

Le probe sewing utilise deux carrés de 10 cm séparés de 1 cm, avec supports
extérieurs maintenus sur 21 cm pour 20 cm de tissu. Ses seuils, supports et durée
n'ont pas été changés par ce correctif. Adapter les paramètres de recette
séparément, sans faire passer un échec en supprimant le probe ou en relâchant ses limites.

Chaque probe raté conserve une preuve dans
`backend-probes/failed-CAS-IDENTIFIANT/diagnostic.json` et sa preview. Une demande
gérée la lie par SHA au diagnostic principal de la tentative, que l'inspection
vérifie avec ses previews. Les contrôles qui rejettent après une évaluation
terminée conservent aussi les dernières positions et le contexte d'exécution.
Une erreur de setup sans évaluation indique zéro frame, sans inventer de résultat.

La preview annonce explicitement PROBE FAIL et vêtement NON EXÉCUTÉ.
Restaurer le checkpoint avant la prochaine mutation. La projection locale
`COMPONENT-local.json` devient FAIL après une tentative locale ratée ; les reçus
des anciennes tentatives restent intacts. Un ancien PASS ne permet donc pas full
après ce nouvel échec. Refaire un essai local réussi sur la recette courante.

## Reproduction et preuves 0.5.7

```text
python -B -m unittest discover -s tests -v
pwsh -NoProfile -File scripts/validate_contracts.ps1
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_probe_failure_smoke.py
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_failure_smoke.py
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python tests/native_sewing_smoke.py
```

190 tests Python passent. La fixture native Blender 5.2.2 LTS emploie un rapport
force/rigidité volontairement insuffisant (force/kg 5000, tension/compression 40)
pour obtenir un vrai écart de couture hors tolérance à la frame 24. Ce n'est pas
une reproduction exacte de la recette du consommateur. Gravité passe ; couture
échoue ; contact et vêtement ne sont pas lancés. Une projection PASS synthétique
est préchargée uniquement pour vérifier son invalidation et le refus full ; elle
ne constitue pas une réussite physique. Mesh/package/gates/original restent intacts.
La preuve est lue avant/après nettoyage et restauration. Les régressions de
diagnostic du vêtement et de physique local/full/freeze passent.
Les artefacts sous `work/native-*` sont exclus de la distribution publique.
