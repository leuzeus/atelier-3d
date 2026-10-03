# Assemblage PATTERN_SEWN par transitions natives

Commencer par [la préparation native des patrons](pattern-preparation.md).
Lorsque son reçu est `READY`, utiliser la recette et le plan retournés dans
`preposition` : l'assemblage consomme les coordonnées préparées, le repos et les
correspondances exactes sans revenir au placement initial.

Le parcours nominal distingue la préparation, le montage, la consolidation et
la qualification portée. Une surface continue peut être utile pour poursuivre
le travail avant d'être qualifiée pour le fitting, le mouvement ou l'export.
`GEOMETRY_READY` et `GEOMETRY_CONSOLIDATED` ne sont donc pas des PASS Cloth ni
des approbations artistiques.

Les résultats exécutés, leurs candidats et leurs limites figurent dans
[VALIDATION.md](../VALIDATION.md). Le protocole décrit ici ne qualifie pas à lui
seul un vêtement. Les essais sur fixtures ne se transfèrent pas au cas réel.

## Sources et représentations

Le package approuvé contient les patrons 2D métriques immuables : IDs, contours,
bords nommés, embu, droit-fil et liens `permanent`, `closure`, `detachable`.
Le [board](fabrication-board.md) conserve son rôle de revue de conception.
Un réglage technique ne demande pas une nouvelle approbation d'un board inchangé.
Une correction démontrée de coupe produit en revanche une variante du package,
avec sa propre revue ; elle ne réécrit jamais la source approuvée.

Le maillage dérivé garde les correspondances source versionnées. Les deux bords
d'une couture partagent les paramètres normalisés de longueur d'arc calculés
par `resample_parameters` et `prepare_boundaries`. La correspondance dépend
des IDs et de ces paramètres, pas de coordonnées monde ni d'indices repris
d'une ancienne triangulation. Les indices servent à exécuter le mapping courant,
lié par empreinte ; une nouvelle triangulation exige un nouveau mapping.

La préforme pilote uniquement le placement de ce maillage. Dans le contrat v1,
elle fournit par panneau soit un cadre local sourcé (origine, axes `u_axis` et
`v_axis`, décalage UV facultatif), soit une cage triangulée avec `uv_cm`,
`target_cm` et `triangles`. Les coordonnées source UV de chaque sommet dérivé
sont placées dans le cadre ou interpolées dans la cage ; la correspondance
est enregistrée. Une cage ambiguë ou ne couvrant pas un sommet source est
refusée. Ces placements ne définissent pas une nouvelle coupe ni une surface
finale procédurale. Les unités et repères doivent être cohérents avec la pose
cible, et le placement doit respecter les contrôles de déformation et de
contact. Une préforme ne garantit pas l'enfilage d'un vêtement complexe.

Après consolidation, la géométrie continue déclare un repos `assembled_3d`.
Les triangles 2D source restent enregistrés **par face**, y compris lorsque
plusieurs îlots aboutissent au même sommet 3D. Ils servent au contrôle des
longueurs et déformations. Ne pas moyenner les coordonnées UV de ces îlots
pour fabriquer une `A3D.FlatRest` soudée : ce serait un repos fictif.

## Recette générique

Préparer une recette Cloth selon `sewing-recipe.schema.json` et un plan selon
[`pattern-assembly.schema.json`](../schemas/pattern-assembly.schema.json).
Le [template de plan](../templates/pattern-assembly.json) illustre le contrat
sur deux petits panneaux synthétiques ; recalculer son mapping et sourcer ses
repères sur le package courant avant tout usage de production.
Conserver les unités en cm dans les contrats et l'échelle métrique native dans
Blender. Les seuils de la recette physique restent applicables.

| Partie du plan | Données et usage |
| --- | --- |
| `version`, `component_id`, `source_refs` | Version du contrat, composant exact et provenance des mesures et choix techniques. |
| `mapping_sha256` | Empreinte calculée par `map_digest` sur le mapping courant ; ne pas y recopier l'empreinte d'une autre triangulation. |
| `preform.panels` | Une entrée par ID source : cadre `source_ref`, `origin_cm`, `u_axis`, `v_axis`, éventuellement `offset_uv_cm` ; ou cage `source_ref`, `uv_cm`, `target_cm`, `triangles`. |
| `assembly` | `max_initial_gap_cm`, `max_displacement_cm`, `max_step_cm`, `iterations`, `neighborhood_rings` et `closure_support_release`. Budgets de préparation et de rapprochement, séparés du seuil de soudure. |
| `consolidation.weld_gap_cm` | Tolérance finale vérifiée avant chaque union permanente et sur les groupes transitifs. |
| `quality` | Angle, longueur minimale d'arête et plage de stretch admissibles. La géométrie doit rester contrôlée pendant le rapprochement. |
| `supports` | Listes séparées `temporary`, `drape`, `functional`. Chaque appui porte `id`, `source_ref`, `piece`, éventuellement `edge`, et `weight`. |
| `collision` | Nécessité du contexte (`required`), réserve `clearance_cm`, `source_ref` et mode `all_stages` par défaut ou `drape_only` explicite. Le corps et l'auxiliaire conservent aussi leurs identités natives. |

Choisir les budgets à partir du maillage, de la taille du vêtement et des
réserves mesurées. Un écart de montage de quelques millimètres peut dépasser
le seuil final de soudure. Il autorise un rapprochement contrôlé ; il n'autorise
jamais l'union des partenaires encore éloignés. Ne pas relever une tolérance
finale pour faire disparaître un refus.

Le contexte de collision doit être explicite. Pour un squelette ajouré,
conserver le corps source exact et préparer une enveloppe auxiliaire appropriée
selon [la préparation de fitting](fitting-preparation.md). Vérifier sa couverture,
ses normales, sa fermeture, sa pose et ses épaisseurs, puis examiner ses pixels.
Un proxy géométrique fermé n'est pas une anatomie validée. Ne pas réduire,
déformer ou remplacer le corps pour obtenir PASS.

Avec `collision.mode="drape_only"`, le corps et l'auxiliaire sont déclarés et
leurs identités vérifiées dès le départ, mais leurs collisions sont activées
seulement à l'entrée du drapé. Ce mode conserve explicitement le montage et
la détente libres. Il ne permet pas de changer de corps ou de recette entre
deux étapes. Le contrôle d'entrée porté conserve les exigences finales et
refuse tout contact profond avant le lancement du Cloth de drapé.

Les appuis temporaires maintiennent le montage. Les appuis de drapé représentent
les maintiens qui doivent encore agir pendant la détente portée. Les attaches
fonctionnelles décrivent les liens nécessaires au comportement final. Leur
provenance et leur rôle doivent rester lisibles ; un pin historique sans rôle
ne devient pas automatiquement une attache fonctionnelle.
Les appuis de drapé et attaches fonctionnelles restent actifs dès le montage ;
seuls les appuis temporaires suivent le retrait progressif.

`closure_support_release` décrit la réduction des appuis temporaires pendant
la fermeture. Les transitions suivantes doivent les retirer avant de qualifier
le drapé. Conserver les poids source et tracer les poids effectifs par étape.
Des partenaires permanents dont les appuis imposent des positions incompatibles
doivent produire un diagnostic de conflit, sans supprimer silencieusement un
maintien ou forcer une couture.

## Parcours natif et reprise

Utiliser `transition_pattern_assembly` à travers `studio_blender_operation`,
puis exécuter son code exact dans le Blender de travail isolé. Les étapes sont
`migrate`, `preposition`, `mount`, `close`, `consolidate`, `relax`, `drape`.
Conserver la recette, le plan, les mappings et les reçus retournés avec leurs
empreintes. Une étape suivante consomme le candidat courant, pas un résultat
copié depuis une autre construction.

```json
{
  "operation": "transition_pattern_assembly",
  "arguments": {
    "component_id": "garment.coat",
    "recipe_path": "sewing/recipe.json",
    "plan_path": "sewing/pattern-assembly.json",
    "stage": "preposition"
  }
}
```

Fournir aussi `project_root` au Studio. Après la migration facultative, l'ordre
est strict. Chaque réussite écrit un nouveau mesh, un reçu de transition et
un reçu de vêtement immuables ; l'objet précédent est archivé. Les liens
incluent plan, recette, package, mapping source, mapping courant, mesh,
checkpoint et reçu précédent. La transition ne met jamais `accepted` à `true`.

1. **Migrer les preuves existantes.** Vérifier la source et conserver un témoin,
   ses reçus, leurs empreintes et leurs statuts. L'enveloppe de migration garde
   la provenance historique sans promouvoir un ancien PASS en preuve actuelle.
   Un montage libre déjà réussi reste une preuve de montage libre.
2. **Prépositionner.** Construire depuis les patrons approuvés, puis appliquer
   la préforme sourcée près de la position assemblée dans la pose cible. Vérifier
   appuis, qualité, réserve de collision et sens topologique des coutures.
   Les tangentes 3D renseignent le placement ; leur opposition locale ne prouve
   pas à elle seule une inversion de la correspondance source.
3. **Monter.** Exécuter un Cloth court avec ressorts permanents déclarés et
   appuis temporaires identifiés. Conserver les paramètres natifs, images
   réellement évaluées, écarts, déplacements et contrôles géométriques.
   Les segments suivent `cloth.mount_release_steps` (par défaut 0, 50, puis
   100 pour cent). Chaque segment repart sans vitesse héritée : c'est un
   rapprochement quasi statique traçable, pas une preuve de continuité dynamique
   entre segments. Les frames d'initialisation sont comptées dans le budget.
   La vraie détente continue qui suit ne bénéficie d'aucune exemption physique.
   Un échec d'admission signifie que Cloth n'a pas commencé.
4. **Fermer si nécessaire.** Une étape native bornée rapproche les partenaires
   permanents et leurs voisinages en respectant les longueurs, les appuis,
   le budget total, le pas maximal, les déformations et les collisions.
   Les candidats inadmissibles sont refusés. Cette étape ne téléporte pas
   chaque paire à sa moyenne et ne remplace pas un Cloth par un PASS physique.
5. **Consolider.** Vérifier la tolérance des seules paires permanentes, ainsi
   que le diamètre de chaque groupe transitif. Refuser les faces effondrées,
   doublons, orientations incompatibles et arêtes non manifold. Garder les
   ouvertures, `closure`, `detachable` et couches distinctes. La surface devient
   une géométrie continue de travail, sans acceptation implicite.
   Un sommet fixé reste l'ancre du groupe ; deux positions fixes contradictoires
   sont refusées. Le mapping conserve toutes les origines de chaque cohorte,
   même lorsqu'un indice représentatif est nécessaire au diagnostic.
6. **Détendre.** Exécuter un vrai Cloth sur cette géométrie continue avec son
   repos 3D déclaré, sans ressorts de couture. Garder les métriques 2D source
   par face pour le contrôle de déformation et retirer les appuis temporaires.
   `A3D.AssembledRest` porte le repos continu ; le profil de phase `drape`
   fournit les paramètres de cette détente.
7. **Draper sur le corps.** Exécuter la phase portée avec le contexte exact,
   les seuls appuis de drapé et attaches fonctionnelles justifiés, puis mesurer
   le fitting. Vérifier emmanchures, ouvertures, couches et comportement prévu.
   La qualification requiert le mannequin déclaré, les capacités mesurées sur
   le corps source et une revue explicite de l'auxiliaire. Épaisseur et
   subdivision viennent après la simulation.

Chaque mutation garde une transition et un checkpoint natifs. Après un refus,
lire le diagnostic conservé et suivre la récupération native ; ne pas modifier
les reçus, le pending ou SQLite pour forcer la poursuite. Reprendre depuis le
dernier candidat valide avec une nouvelle entrée sourcée si elle est nécessaire.
Les fichiers et objets antérieurs restent des témoins, pas des sources de PASS
à transférer vers le nouveau candidat.

`freeze_sewn` connaît le repos continu : il exige le reçu actuel de drapé
`FITTING_PHYSICS_ONLY`, les mêmes identités de plan, recette, source et géométrie,
un fitting toujours qualifié et aucun ressort ou appui temporaire. Il crée une
copie de rendu sans souder une seconde fois. Les jalons de comportement, de
revue visuelle et d'export restent applicables ; cette copie n'est pas acceptée
automatiquement.

La revue d'une enveloppe auxiliaire identifie sa géométrie et celle du corps
cible, déclare explicitement `collision_use: SUITABLE`, et référence les images
face, profil, dos et trois quarts par chemin et SHA. Des noms de vues seuls ou
une revue signalant des défauts ne suffisent pas. Cette qualification technique
ne constitue pas une approbation artistique de l'anatomie ou du vêtement.

## Distinguer les causes

| Classe | Observation qui l'établit | Conclusion permise et suite |
| --- | --- | --- |
| Montage libre | Cloth évalué sans corps, avec coutures et budgets mesurés. | Peut qualifier l'assemblage libre exact. Ne qualifie ni contact, ni capacité sur le corps, ni enfilage. |
| Placement / enfilage | Intersection initiale, pose incompatible, ouverture ou trajet impossible avant Cloth. | Reprendre la préforme, les repères ou la séquence d'enfilage. Une pénétration profonde n'est pas un manque de tolérance. |
| Conflit d'appuis | Partenaires ou voisinages retenus vers des cibles incompatibles, poids et résidus identifiés. | Réviser explicitement le rôle ou la transition des appuis. Ne pas confondre appui temporaire et attache finale. |
| Défaut de coupe démontré | Chemins homologues et capacité source mesurés sur le corps exact, avec aisance et incertitude, montrent un déficit. | Proposer une variante de coupe à revoir. Un vêtement mal placé ou un Cloth divergent ne suffisent pas. |
| Échec physique | Cloth réellement lancé, images évaluées, paramètres natifs vérifiés, déformation/contact/déplacement hors limites. | Conserver l'échec du candidat et diagnostiquer le sous-ensemble concerné. Un refus avant solveur n'est pas un échec Cloth. |

Une couture fermée géométriquement ne prouve pas la convergence des ressorts.
Une détente courte ne prouve pas la stabilité longue. Un fitting sur proxy
ne prouve pas la capacité sur le corps cible sans mesures homologues.
L'acceptation finale et l'export restent conditionnés au fitting et au
comportement qualifiés sur le candidat exact, puis à la revue visuelle humaine.

## Ce que la méthode historique apporte

La lecture de `01f_fit.py`, `tailor_common.py` et `02_sewn_relax.py` du projet
historique buste/manches montre une séquence utile : panneaux prépositionnés,
ressorts courts, géométrie continue, puis 24 images de détente Cloth sans
ressorts. Les rendus face/profil/dos/trois quarts et la séparation entre source
et surface cousue restent des pratiques utiles.

Cette implémentation historique n'est pas reprise telle quelle. Elle fabriquait
ses métriques à plat par UV unwrap de panneaux 3D puis réconciliation des
longueurs ; cela ne respecte pas l'immuabilité de patrons déjà approuvés.
Son `freeze_sewn` fusionnait les paires et moyennait leurs groupes sans limite
de distance, alors qu'un résidu jusqu'à **65,9 mm** était documenté après les
ressorts. Il supprimait les faces réduites à moins de trois sommets distincts
au lieu de refuser l'union. Les projections sur le mannequin et les pins choisis par coordonnées
absolues étaient propres à cette scène. Aucun de ces raccourcis ne constitue
une fermeture générique admissible ou une qualification physique transférable.

Le cas réel plus récent a déjà un montage libre full réussi. Le diagnostic
historique distingue un écart de couture de **1,75213 mm** d'une pénétration
sur l'ancien proxy de **12,346239 cm**. Avec l'enveloppe R21, le contact mesuré
avant pose atteignait **9,572296 cm**, puis **7,811482 cm** après la préparation
de pose, pour un seuil conservé de **0,05 cm**. Les 973 sommets en excès et les
rayons intérieurs du pire sommet documentent un problème de placement profond.
La correction de couture 0.6.6 ne déplaçait pas ce pire sommet.

Dans cette même copie de diagnostic, deux paires d'emmanchure restaient à
**1,65213 mm** et **1,55352 mm**, au-delà du seuil de soudure de **1,5 mm**.
Ce résidu local peut relever d'un rapprochement borné ; sa résolution ne
résout pas les **78,1 mm** de contact au buste. Ces mesures sont des preuves
antérieures conservées, pas des résultats du nouveau parcours. Voir les états
0.6.2 à 0.6.6 de [VALIDATION.md](../VALIDATION.md). Les assets et rapports
consommateurs privés restent sous `work/` et hors de la distribution.

## Table de conservation et de migration

La dépréciation retire les entrées redondantes du parcours nominal. Elle ne
supprime ni la lecture des anciens reçus, ni leurs tests, ni les preuves.
La présence d'un reçu historique encore consommé interdit sa suppression sans
migration vérifiée. Aucune suppression destructive n'est requise pour cette refonte.

| Fichier / fonction ou entrée | Décision | Raison et migration |
| --- | --- | --- |
| `a3d/sewing.py` : `chain_lengths`, `sample_chain`, `resample_parameters`, `prepare_boundaries` | Conserver | Primitives source et mapping ID/longueur d'arc commun. Réutiliser leur résultat versionné ; ne pas réapparier par proximité. |
| `blender/sewing.py` : `triangulate`, `build_mesh` | Conserver | Construction dérivée des patrons approuvés. Une nouvelle résolution écrit un nouveau mapping et invalide les preuves liées à l'ancien. |
| `a3d/sewing.py` : `permanent_support_groups` | Conserver | Cohortes explicites permanentes, utiles au diagnostic des appuis ; ne pas y introduire les fermetures réversibles. |
| `a3d/pattern_assembly.py` : `validate_plan`, `preform_coordinates`, `bounded_close`, `consolidate` | Remplacer le pilotage nominal | Un plan versionné et des étapes distinctes portent la préparation, les budgets et la consolidation ; les patrons restent la source. |
| `blender/pattern_assembly.py` : `transition_pattern_assembly` | Remplacer le pilotage nominal | Une transition native par étape, avec checkpoint et reçu. Migrer les preuves historiques avant de poursuivre le nouveau candidat. |
| `blender/sewing.py` : `apply_physics`, `simulate_object`, `context_colliders`, diagnostics et snapshots | Conserver | Primitives natives de Cloth, de collision et de mesure. La simulation continue déclare son repos 3D et conserve les métriques source par face. |
| `a3d/sewing.py` : `weld_permanent` et `blender/sewing.py` : `freeze_sewn` | Conserver pour compatibilité ; remplacer au stade intermédiaire | Le freeze historique reste une sortie gardée. La consolidation intermédiaire est séparée de l'acceptation finale et renforce le contrôle transitif ; aucun reçu de consolidation ne vaut freeze final. |
| `blender/sewn_stages.py` : `apply_sewn_result`, `stage_receipt`, `save_copy` | Conserver les primitives et la lecture | Transport de coordonnées et continuité historiques. La migration conserve recette, mapping, source et statut d'origine, sans promouvoir un ancien essai. |
| `blender/sewn_stages.py` : accumulation de `prepare_sewn_stage` | Déprécier dans le parcours nominal | Remplacer l'enchaînement implicite des préparateurs par les étapes explicites. Les anciens appels et reçus restent lisibles pendant la migration. |
| `blender/prefit.py` : `solve_prefit`, `apply_prefit` / `experimental_prefit` | Déprécier l'entrée nominale | Réutiliser les contrôles utiles, conserver les tests et les preuves ; migrer le placement obtenu comme état historique, puis déclarer le nouveau plan. |
| `blender/interfaces.py` : `interface_candidate`, `prepare_interfaces` / `interface_preparation` | Déprécier l'entrée nominale | Le nouveau rapprochement agit sur partenaires et voisinages avec budgets explicites. Garder diagnostics et mappings des essais anciens. |
| `blender/panel_mount.py` : `mount_candidate`, `mount_panels` / `panel_mount` | Déprécier l'entrée nominale | Éviter plusieurs mécanismes d'attraction superposés. Conserver leurs reçus et refus ; aucune translation automatique de leurs PASS vers `close`. |
| `blender/donning.py` : `rigid_frame`, `place_for_fitting` / `fitting_placement` | Conserver la primitive de cadre ; déprécier l'entrée nominale | Décrire les repères sourcés dans la préforme. Les cadres ne qualifient ni anatomie ni enfilage. |
| `blender/fitting_pose.py` : `basis`, `pose_field`, préparation sourcée | Conserver les primitives et les témoins | Repères liés au corps, influences continues et conservation des partenaires restent utiles. Un artifact préparé reste `PREPARED_NOT_APPLIED` tant qu'aucune transition ne l'applique et ne le contrôle. |
| `blender/sewn_stages.py` : `contact_recovery` | Déprécier l'entrée nominale | Une projection indépendante des sommets ne résout pas un contact profond. Conserver les anciens refus et exiger une correction de placement/enfilage sourcée. |
| `blender/clean_construction.py`, `blender/legacy.py`, `blender/body_source.py`, `blender/fitting_envelope.py` | Conserver | Témoins, reprise, migration et identités du corps/auxiliaire restent nécessaires. Ne pas toucher à la scène consommateur pour obtenir un départ propre. |
| Anciens reçus, checkpoints, mappings, essais de refus | Conserver | Documents de provenance ; migration additive avec empreinte et statut originaux. Aucun effacement automatique. |
| Entrées et fichiers redondants après migration de tous leurs consommateurs | Supprimer ultérieurement seulement | Une suppression exige inventaire des références, migration vérifiée et tests de lecture historiques. Rien à supprimer avant cette preuve. |

## Recette de vérification et livrables

Exécuter les essais dans des processus Blender dédiés, avec profil et caches
configurables sur **G:**, `--background --factory-startup --disable-autoexec
--python-exit-code 1`. Ne pas envoyer une réinitialisation à la scène Blender
ouverte. Cloner les données et la base canonique en lecture seule vers un nouveau
répertoire G:, réécrire la session du clone, puis vérifier les empreintes des
sources avant et après. Les données consommateurs originales ne sont pas une
zone de travail.

Vérifier d'abord un buste à cinq panneaux, puis un vêtement sans manches ou
asymétrique. Fixer une graine et journaliser les translations de quelques
millimètres et rotations de quelques degrés, avec des budgets déclarés avant
l'essai. Les perturbations doivent conserver les mêmes patrons, bords, types,
correspondances et exigences finales. Une variante hors budget doit être
refusée explicitement ; elle ne doit pas disparaître du bilan.

Par fixture, conserver le cycle complet, les reçus, l'état des appuis par étape,
le maillage continu, le Cloth sans ressorts, le drapé et les refus provoqués.
Tester une correspondance source périmée, une orientation topologique inversée,
des appuis contradictoires, une union à distance, un groupe transitif trop large,
une face effondrée, une couture réversible et un contact profond. Examiner les
pixels de face, profil, dos et trois quarts, avec des vues rapprochées des
emmanchures. Une métrique ou un hash ne remplacent pas cette inspection.

Rejouer ensuite le parcours sur une **nouvelle copie isolée du vêtement réel**,
sans lui attribuer les PASS des fixtures. Conserver un master `.blend` versionné
au dernier stade réellement obtenu, les rendus de revue et un bilan des défauts
résiduels. Si la fermeture, le fitting ou la physique refusent le candidat,
livrer aussi le refus et son diagnostic ; ne pas nommer le master « final
qualifié » et ne pas exporter un vêtement encore non qualifié.
