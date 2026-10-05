# Métriques affines sur un état interne frais

`a3d/material_surface_metrics.py` est une unité privée de test, de qualification
`NONE`. Elle observe uniquement le Jacobien affine et la matrice de Gram de
chaque face du porteur. Elle ne donne aucune admission de domaine, déplacement,
contact, supports physiques, Cloth ou fitting.

## Appel et responsabilité du caller

`observe_material_surface_metrics(state, *, originals, before, budget,
input_hashes=None, provenance=None)` reçoit directement l'état obtenu par
l'unique `material_surface_field._compile` du caller. Le caller conserve la
capture originale `[data, provenance, déclaration de budget, deadline]`, son
empreinte `before` et **le même** objet réel `field._Budget`. Les petites fixtures
de tests montrent cette chaîne capture → compilation → observation ; aucun
caller produit ou pilote du col n'est intégré dans cette unité.

La fonction ne crée pas de budget, d'horloge, de capture ou de compilation.
Le binding compact existant vérifie la capture, les déclarations, les sources et
la provenance. L'état dérivé est une interface interne : ses domaines et ses
parents ne sont pas revalidés par l'observateur. Un flag client « validé » ou un
fichier compact sérialisé ne remplace pas un état fraîchement compilé. La
provenance reste opaque et ne valide aucun raccord ou collider.

## Calcul et portée numérique

Le noyau reprend exactement la section métrique de `field._observe`, en
réutilisant `_jacobian` et `_psd`. Il compare sans epsilon les matrices
`G − min_stretch² I` et `max_stretch² I − G` à la condition PSD exacte. Les
coordonnées binaires capturées sont représentées par leurs rationnels exacts ;
les bornes binaires existantes 0,9 et 1,1 sont inclusives. Les limites plus
strictes déjà validées par le compiler sont conservées.

La sortie contient toutes les faces, leurs IDs, Jacobien et Gram rationnels,
les témoins PSD, puis des nombres typés de faces observées, satisfaites ou
violées et leurs IDs. Une translation peut satisfaire toutes les métriques
tout en violant un déplacement : `displacement`, `step`, `physical_stops` et
`contacts` restent donc `NOT_ASSESSED`. `constraints_3d` et `fitting` restent
`NOT_QUALIFIED`, `simulation` reste `NOT_EXECUTED`. Aucun `READY` n'est produit.

## Budget, identité et frontières de retour

Chaque face débite un `metric_faces` et 13 opérations `budget.q` du noyau
historique. Les opérations du binding, de l'encodage et de la sortie sont
débitées réellement sur le ledger cumulatif existant. Les caps et la deadline
du caller ne sont ni augmentés ni remis à zéro. Deux observations consomment
deux sorties complètes ; un refus ne rembourse aucun travail déjà effectué.

Le finalizer compact reste inchangé. Le nouveau module calcule lui-même le SHA
de ses bytes réels ; la sortie `metrics_code_sha256` et le champ reçu
`input_hashes.metrics_code` le lient explicitement. `metric_inputs_sha256` lie
les seules données utilisées : IDs, faces, triangles UV rationnels, coordonnées
3D rationnelles et limites. Les hashes compact/field/UV existants sont aussi
conservés. Un nouveau SHA du module désigne une observation différente ; cette
identité privée n'ajoute pas automatiquement une dépendance à un caller produit.

Après `_finish`, l'observateur relit son code, les originaux et ces données
utilisées, refuse leurs mutations, puis vérifie la même deadline juste avant
retour. Le reçu est explicitement le checkpoint du packer **avant** ces guards
de retour. Ses compteurs et son timestamp ne sont pas réécrits ensuite. Les
guards lisent, hashent et vérifient le temps ; `field._hash` ne débite pas de
nodes ou de travail de hash. Leur durée est contrôlée par la deadline mais
n'est pas un nouveau compteur de travail ni un timestamp final attesté.

La précondition existante demeure une horloge monotone coopérative en lecture
seule et des entrées sans auteur concurrent. Les tests injectent des mutations
avant les guards et démontrent leur refus ; ils ne promettent pas d'exclusion
mutuelle après la dernière frontière. Une deadline épuisée donne `INCOMPLETE`,
une mutation donne `REFUSED`, et aucune sortie partielle n'est retournée.

## Vérification et limites

Les tests ciblés comparent les observations exactes au noyau métrique legacy
sur rotations, windings, cisaillement et collapse. Ils distinguent les bornes
binaires et un ULP extérieur, le budget partagé, les caps, les sorties
cumulatives, les mutations du code/des originaux/de l'état utilisé et la
deadline terminale. Ils n'exécutent pas le col réel ou un calcul natif.

Cette capacité fournit un contrôle affine nécessaire aux travaux L4/L5. Les
domaines UV restent au compiler ; le champ à ses cassures, les traces et
contraintes, les contacts, la mise en volume physique et le vêtement complet
restent des acceptations séparées. Aucun succès de fixture ne qualifie les six
cages, les douze barres, Cloth, le fitting ou une livraison.
