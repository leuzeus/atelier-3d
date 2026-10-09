# Fitting mesuré et bâti temporaire — 0.5.8

Le premier incrément compare des capacités et permet un maintien temporaire.
Il ne dessine ni n'applique automatiquement des retouches de patron et ne fournit
pas encore de montage progressif. Les mesures de largeur à un même V et la boîte
englobante d'un mannequin ne constituent pas un tour fini.

## Fiche de mesures

Déclarer d'abord [la catégorie, l'intention de coupe et l'aisance](garment-fit-intent.md).
Un vêtement ample nécessite des cibles de volume et de mouvement explicites,
distinctes des réserves de collision. Les mesures d'un devant ouvert conservent
leur couverture et leurs recouvrements ; elles ne deviennent pas un tour fermé.

Préparer `templates/fitting-plan.json` dans le dossier du projet. Le template est
volontairement incomplet : il doit retourner NOT_QUALIFIED. Le plugin prépare
les données techniques ; il ne demande pas à l'utilisateur de remplir un formulaire.

Via `studio_blender_operation`, obtenir puis exécuter le code exact de :

```json
{"operation":"inspect_garment_fit","arguments":{"component_id":"garment.coat","recipe_path":"recipe.json","fit_path":"fit.json"}}
```

Le corps et l'enveloppe sont nommés et liés à leur SHA géométrique évalué, donc
à leur pose. `body.role=target` distingue le corps cible d'un proxy. L'enveloppe
doit être le collider effectivement déclaré par la recette. Échelle appliquée
et mètres Blender sont vérifiés. Des sections horizontales explicites utilisent
`height_cm` et un `seed_xy_cm` intérieur : une seule boucle fermée contenant ce
repère est retenue. Les boucles séparées des bras sont exclues. Une section
coplanaire/ambiguë ou sans boucle unique reste NOT_QUALIFIED. Cette version ne
mesure pas automatiquement l'épaule, les longueurs de bras ni les sections
obliques d'un membre. Les repères anatomiques ne sont pas inférés d'une boîte.

Chaque mesure déclare son `landmark_status` (assumed ou validated), sa provenance,
sa cible minimum/style, son incertitude, l'aisance en cm et la prise en compte des
couches/marges autour de l'enveloppe sous forme de `envelope_clearance_girth_cm`.
Ce dernier nombre est une allocation explicite de tour, pas une conversion
automatique de l'épaisseur de collision en périmètre.

Un `pattern_path` traverse les pièces à la **ligne de couture source**. Chaque
segment nomme la pièce, les deux bords et leurs paramètres d'arclength `t` dans
[0,1], avec des points intermédiaires 2D facultatifs. Les segments doivent rester
dans le polygone source. `joins` nomme les correspondances de couture/fermeture
entre la fin de chaque segment et le début du suivant, y compris le dernier vers
le premier. Paramètres et orientation doivent être homologues. Un lien detachable
ne certifie pas ce chemin fermé. Les reprises de plis/chevauchements sont des
`takeup` chiffrés et sourcés ; la marge de coupe n'est jamais ajoutée au volume.

Exemple de segment, seulement illustratif :

```json
{"piece":"front","from":{"edge":"left","t":0.5},"to":{"edge":"right","t":0.5}}
```

Le tableau retourné donne corps, enveloppe, capacité, cible, écart, incertitude
et données manquantes. Cible minimale = maximum de corps + aisance et enveloppe
+ allocation de tour. Un déficit supérieur à l'incertitude est DEFICIT_MEASURED
et le rapport INCOMPATIBLE. Une cible de style est STYLE_DELTA, sans conclusion
d'incompatibilité. Proxy, repères supposés, chemin/fermeture/aisance manquants :
NOT_QUALIFIED. CAPACITY_SUFFICIENT ne certifie ni l'essayage porté, ni le drapé.
Les signaux mesurés de placement, les supports déclarés et la physique non établie
restent séparés du diagnostic de coupe. Un échec Cloth seul ne mesure pas un déficit.

Pour lier la fiche à une recette :

```json
{"fitting_plan":{"path":"fit.json","sha256":"SHA256_DU_FICHIER_EXACT"}}
```

La fiche et les identités du corps/enveloppe lient le trial. Changer fiche,
recette, pose ou patron invalide les preuves dépendantes ; les anciens essais
restent sur disque. Un déficit démontré bloque full si cette fiche est référencée.
Une fiche incomplète permet l'investigation locale, sans conclusion de fitting.
Une recette historique sans fiche conserve sa voie physique ; elle ne fournit
aucune certification d'aisance. Refaire local avant full après passage à 0.5.8 :
le binding actuel inclut le fitting.

## Proposition de retouche

`propose_pattern_adjustment` prend les mêmes arguments et reste en lecture seule.
Pour un déficit mesuré seulement, `adjustment_sites` peut nommer des bords, parts
du déficit (`share`, somme 1), limites de capacité en cm et provenance. Les sites
ne sont pas multipliés implicitement par symétrie. Le rapport alloue la capacité
à ajouter, nomme les coutures dépendantes et signale un dépassement des limites.

Une allocation de capacité n'est pas un décalage normal universel du bord :
angle, courbe et construction changent cette relation. Le plugin ne transforme
pas arbitrairement cette allocation en contour. Si une retouche est justifiée,
préparer une **variante séparée** avec la voie native des packages existante,
redessiner localement avec raccords lisses, préserver droit-fil/embu/pièces liées,
remesurer et revalider les coutures, puis montrer le board des différences.
L'approbation du découpage doit porter sur cette variante exacte avant production.
Changer seulement la marge de coupe ne corrige pas la capacité cousue.

## Attache temporaire d'une fermeture existante

Une entrée de recette explicite :

```json
{"fitting_tacks":[{"id":"baste-a06","seam_id":"fermeture-proposee-a06","phase":"mount","source_ref":"Demande d'essayage fermé, correspondances A06 source","force_mode":"shared_native_sewing","sewing_force_per_kg":20000,"frame_start":1,"frame_end":48}]}
```

Adapter phase, durée et force à la recette exacte. Seules les paires source
existantes d'un lien closure peuvent servir d'attaches ; les deux panneaux doivent
rester dans le sous-ensemble local. Le bâti couvre la phase locale entière. Blender
emploie une force de sewing commune à l'objet Cloth : force/kg doit donc égaler
le profil de phase ; cette version n'offre pas une force indépendante par lien.
La durée doit égaler celle de la phase. Aucun bouton/zip final n'est inventé.

Les arêtes de bâti n'existent que sur le mesh local jetable. Les paramètres
observés, leur identité, les gaps et la tolérance sont conservés dans le résultat
ou diagnostic. Après nettoyage, le mesh principal et la forme de repos restent
intacts ; closure/detachable ne sont ni retypés ni soudés. Un PASS avec bâti porte
CONSTRUCTION_FITTING_ONLY. La recette contenant ces attaches est refusée pour
full/freeze. Les retirer, actualiser la recette puis obtenir un **nouveau PASS
local** avant full ; la stabilité sans ces supports reste à démontrer.

## Limites et reprise du manteau réel

Le template incomplet peut diagnostiquer les données manquantes dès maintenant.
Pour le manteau, utiliser les repères connus comme **assumed**, l'enveloppe exacte
comme proxy, puis définir les chemins homologues avant de conclure sur la coupe.
Aucune augmentation de patron ou réduction du mannequin n'est justifiée tant
qu'un déficit n'est pas mesuré. Un seul essai de bâti ciblé peut tester le maintien
A06 ; son succès ne qualifie pas le torse ni son raccord aux manches. Lire les
preuves et restaurer après FAIL ; ne pas enchaîner des profils sans hypothèse.

## Vérification

199 tests Python ; fixture Blender native de mesure/déficit, proposition sans
mutation, fermeture mécanique, nettoyage local et refus full ; régressions
physiques local/full/freeze et conservation des diagnostics de probes. Ce sont
des preuves synthétiques, pas une qualification du vêtement consommateur.

La méthode de comparaison des repères corps/patrons et de l'aisance est décrite
par [NMSU C-220](https://pubs.nmsu.edu/_c/C220/index.html). Les retouches locales
et leurs techniques sont présentées dans [NMSU C-228](https://pubs.nmsu.edu/_c/C228/index.html).
Leurs valeurs de vêtements féminins ne deviennent pas des constantes pour ce manteau.
