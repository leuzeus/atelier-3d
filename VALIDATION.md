# Validation d'Atelier 3D

## État de la version 0.6.0

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 204 tests | Contrat opt-in, budgets, permanent seulement, binding et mesures finales |
| Contrats indépendants | PASS : 9 distribués + config privée | Recette historique compatible ; aucun seuil physique assoupli |
| Prépositionnement natif guardé | PASS sur fixture | Écart réduit, contours/rest/topologie/pins/package intacts ; fermeture préservée |
| Références fixes contradictoires | PASS du refus | Simulation existante non archivée ; diagnostic et checkpoint conservés |
| Raffinement natif | PASS / refus borné | Ancrages et aire conservés ; budget insuffisant refusé |
| Raffinement du cas réel isolé | PASS technique | Angle minimal 2,2483° → 4,0195°, 6647 → 6649 sommets, contours et sources intacts |
| Diagnostic final de qualité | PASS sur fixture | Qualité FAIL, couture FAIL et contact PASS visibles ensemble ; restauration vérifiée |
| Régression physique native | PASS sur fixture | Probes, local/full/freeze et refus existants |
| Prépositionnement du cas réel isolé | Précontrôle PASS | Fraction 0,125 ; aucun PASS Cloth ou fitting déduit |
| Cloth après prépositionnement réel | FAIL à l'image 48 | Déformations et coutures encore hors limites ; essai expérimental, production intacte |
| Validation visuelle/humaine du nouveau placement | NOT_EXECUTED | À réaliser dans le projet consommateur, après inspection des mesures |

Voir [le contrat expérimental et le protocole d'essai](references/experimental-prefit.md).
La fixture guardée teste l'intégration ; le cas réel est une reproduction isolée
et ne constitue pas une qualification du projet consommateur.

## État de la version 0.5.9

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 201 tests | Maxima distincts, mapping local/source, historique sans incrément, non-mutation et régressions |
| Contrats indépendants | PASS : 9 distribués + config privée | Aucun contrat ou seuil physique assoupli |
| Arrêt natif de déplacement | PASS du diagnostic | Image d'arrêt conservée, excursion/incrément source mesurés ; coupon FAIL demeure FAIL |
| Conservation/restauration native | PASS | Inspection historique intacte après nettoyage/restauration ; aucun full accordé |
| Régression native physique | PASS sur fixture | Probes, local/full/freeze et contrôles de copie inchangés |
| Reproduction isolée du cas réel | FAIL du vêtement, télémétrie mesurée | Arrêt reproduit à l'image 44 ; excursion 30,0746 cm, incrément maximal 2,3367 cm, sommets différents |
| Retrait des deux appuis faibles du dos | Hypothèse rejetée | FAIL à l'image 18 ; pas de recommandation de retrait des appuis |
| Translation initiale de 3 cm | Refus natif | Pénétration initiale ; aucun Cloth lancé |
| Proposition bornée par contacts | Précontrôle PASS, Cloth NOT_EXECUTED | Translation 0,5600 cm ; légère baisse d'écarts au col/épaules, hausse d'un écart latéral ; aucun fitting accepté |
| Fitting, cause physique, production consommateur | NOT_QUALIFIED / NOT_ESTABLISHED / NOT_EXECUTED | Proxy et homologues supposés ; pas de déficit de coupe certifié ni modèle de production modifié |

Voir [les mesures et leurs limites](references/cloth-motion.md).
Les expériences réelles sont des fixtures isolées de diagnostic, pas une
qualification via le dispatcher du consommateur. La continuité obtenue par
une union géométrique de partenaires éloignés ne se transfère pas à une preuve
de convergence Cloth. Aucun mode d'assemblage assisté, préformage anatomique
ou montage progressif nouveau n'est livré par ce correctif.

## État de la version 0.5.8

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 199 tests | Chemins fermés homologues, marge/aisance, incertitude, sections séparées et attaches |
| Contrats indépendants | PASS : 9 distribués + config privée | fitting-plan ajouté ; recette historique compatible |
| Mesure native et déficit connu | PASS sur fixture | Corps cible distinct du collider, 32 cm mesurés, déficit 4 cm, full refusé |
| Proposition bornée | PASS sans mutation | Allocation de capacité en cm et coutures liées ; pas de dessin ou application automatique |
| Bâti closure natif | PASS | Écart contrôlé, durée/force observées, lien closure préservé et freeze sans permanent refusé |
| Essai local avec bâti | PASS sur fixture | Mesh jetable nettoyé, principal/rest/package intacts ; construction seulement, full refusé |
| Corps/fiche périmés | PASS du refus | Pose/géométrie target et SHA fiche vérifiés ; binding des essais actualisé |
| Régression physique | PASS sur fixture | Probes, local/full/freeze inchangés sans bâti |
| Montage/fitting manteau réel | NOT_QUALIFIED | Capacité homologuée, corps cible et assemblage consommateur non acceptés |

Voir [le contrat et les limites du fitting](references/measured-fitting.md).

## État de la version 0.5.7

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 190 tests | Statuts probe/vêtement, intégrité des preuves et régressions |
| Contrats indépendants | PASS : 8 distribués + configuration privée | Probes, seuils et patrons inchangés |
| Échec natif du probe sewing | PASS du diagnostic | 24 images évaluées sur coupon ; recette vêtement 48 ; essai vêtement NOT_EXECUTED |
| Nettoyage et restauration | PASS | Diagnostic, profil, supports, géométrie et preview conservés et vérifiés |
| Qualification locale et full | PASS du refus | Projection PASS synthétique antérieure invalidée ; full refusé pour absence de PASS local actuel |
| Échec local évalué du vêtement | PASS du diagnostic | Régression de conservation et restauration toujours valide |
| Régression native physique | PASS | Probes, local/full et freeze sur fixture synthétique |
| Vêtement réel / défaut Cloth | NOT_ESTABLISHED | Aucun projet consommateur modifié ; retest séparé |

Voir [le protocole et les limites](references/probe-diagnostics.md).

## État de la version 0.5.6

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 189 tests | Tangente locale/chorde globale, historique, intégrité et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun seuil ni contrat de patrons assoupli |
| Rejet natif d'orientation | PASS du diagnostic | Couture/bords, paires, indices, rest UV, positions et cosinus -0,5 localisés |
| Rejet natif de qualité | PASS du diagnostic | Maillage dérivé rejeté avant objet/reçu ; arêtes hors limites conservées |
| Rejet natif de contact initial | PASS du diagnostic | Pièce/sommet/collider, surface et profondeur mesurée conservés |
| Restauration obligatoire / lecture historique | PASS | Diagnostic intact avant/après restauration ; inspection ne libère pas pending |
| Régression native Cloth | PASS | Probes, local/full et freeze sur fixture synthétique |
| Robe de production, faux positif d'orientation ou bug Cloth | NOT_ESTABLISHED | Projet consommateur laissé intact ; aucun fitting qualifié |

Voir [le protocole et la reproduction](references/garment-rejections.md).

## État de la version 0.5.5

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 187 tests | Mesures, admission, contrats et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun contrat de patrons ou seuil modifié |
| Inspection native Blender 5.2.2 LTS | PASS : processus isolé | Deux panneaux effilés, coupons d'emmanchure, bras incliné ; état, fichiers, sélection et frame préservés |
| Comparaison flat/cylinder | PASS du diagnostic | 22 segments traversants → 0 ; écart 24,4131 → 3,9345 cm dans la fixture ; aucun PASS de couture |
| Refus natifs | PASS | Collider modifié et Cloth actif refusés |
| Rapport initial après échec et restauration | PASS | `placement.json` conservé et lié par SHA au diagnostic, aucun déblocage full |
| Régression native Cloth | PASS | Probes, local/full et freeze sur fixture antérieure |
| Montage et fitting de la robe réelle | NOT_EXECUTED | Projet et Blender consommateur intacts ; retest après mise à jour |
| Placement conique / coupon spatial découpé | NOT_IMPLEMENTED | Diagnostic et recette native existante d'abord ; pas de géométrie substituée au patron |

Voir [le protocole](references/sewing-placement.md) et
[les essais 0.5.5](references/validation-placement-0.5.5.md).

## État de la version 0.5.4

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 185 tests | Admission de cadrage, diagnostics, mappings et régressions |
| Contrats JSON indépendants | PASS : 8 distribués + configuration locale privée | Aucun contrat de fabrication modifié |
| Cadrage natif Blender 5.2.2 LTS | PASS : processus isolé | ORTHO/PERSP, sélection/transforms/mesh/fichiers/état préservés ; cas étrangers et éditrices refusés |
| Capture de viewport synthétique | PASS | Pixels issus de Blender ; aucune validation artistique d'un asset réel |
| Vrai échec local après 32 frames Cloth | PASS du test de refus | Qualité hors limites, positions et zones conservées ; essai reste FAIL |
| Nettoyage puis restauration | PASS | Diagnostic encore inspectable, original/mesh/gates préservés, aucun PASS local ni admission full |
| Régression complète native de couture | PASS | Probes physiques, local/full, circuit d'échec et freeze sur fixture synthétique |
| Projet et Blender consommateur | UNTOUCHED | Retest du cadrage et d'un nouvel échec nécessaire après rechargement |
| Coupon limité à une région du patron | NOT_IMPLEMENTED | Étendues de pièces et coutures omises exposées ; supports/découpes régionales non inventés |

Voir [le protocole](references/viewport-diagnostics.md) et
[les essais 0.5.4](references/validation-viewport-0.5.4.md).

## État vérifié en version 0.5.3

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 176 tests | Reçus distincts, immutabilité, récupération et régressions des contrats/hooks |
| Contrats JSON indépendants | PASS : 8 fichiers distribués | Neuvième contrôle local de la configuration privée, exclue du package |
| Trois imports réels 0.4.0 dans Blender 5.2.2 LTS | PASS | Reçu du manteau remplacé par celui de la ceinture, puis manteau densifié par un script guardé |
| Vérification native du checkpoint | PASS | Objet initial, identité composant/package et topologie vérifiés ; contexte et datablocks conservés après lecture |
| Migration et rebuild multicomposants | PASS : fixture isolée | Mesh/rest et voisins préservés, nouveaux mappings, quatre reçus immuables pour trois composants et un rebuild |
| Checkpoint réel du consommateur | PASS : lecture seule isolée | Objet d'import retrouvé dans le checkpoint historique ; aucun fichier consommateur ni Blender ouvert modifié |
| Reprise dirty et ancien runtime en mémoire | PASS : régression 0.5.3 | Anciennes fonctionnalités de reprise conservées |
| Migration réelle et physique du manteau | NOT_EXECUTED | Retest nécessaire dans le projet consommateur après rechargement de l'installation |

Voir [le rapport 0.5.3](references/validation-receipts-0.5.3.md) et
[le protocole de récupération](references/blender-continuity.md).
Les résultats antérieurs restent historiques et ne qualifient pas un asset réel.

## État vérifié en version 0.5.2

| Vérification du correctif | Résultat | Portée |
| --- | --- | --- |
| Suite Python Windows | PASS : 170 tests | Contrats, hooks, admission, chargement de version, reprise, migration et recettes |
| Contrats JSON indépendants | PASS : 8 fichiers distribués | Un neuvième contrôle local vérifie la configuration privée, exclue du package |
| Continuité Blender 5.2.2 LTS | PASS : deux processus isolés | Modules 0.4.0 réellement chargés puis remplacés, scène dirty sauvegardée en copie, refus d'une scène étrangère |
| Ancien mesh brut et variante densifiée | PASS : fixtures synthétiques | Archivage avec géométrie/rest conservés, mapping nouvellement dérivé, décisions et sources inchangées |
| Inversion cylindrique `mirror_u` | PASS | Formule attendue, rest 2D inchangé et ancien maillage invalidé après changement de recette |
| Régression du cycle de vie Blender | PASS | Erreur après mutation, blocage, restauration et assemblage séparé |
| Projet consommateur et Blender déjà ouvert | UNTOUCHED | Les essais utilisent leurs propres projets et processus ; aucune migration réelle revendiquée |
| Nouvelle simulation physique, fitting et export Unreal | NOT_EXECUTED | Ce correctif ne qualifie pas la robe ni les recettes de production |
| Mise à jour de l'installation active dans Codex | NOT_EXECUTED pour ce correctif | Publication, installation et rechargement sont des étapes distinctes |

Voir [le rapport 0.5.2 et sa reproduction](references/validation-continuity-0.5.2.md).
Les résultats antérieurs ci-dessous restent historiques, sans être transférés à
une nouvelle recette ou à un asset réel.

## Socle vérifié en version 0.5.0

Le socle logiciel, les contrats et des opérations natives Blender ont été
vérifiés. **La qualification de production d'un asset complet reste non exécutée.**
Les contrôles automatisés ne prouvent pas la fidélité artistique des références,
l'ajustement des patrons ou la qualité d'un export de jeu.

| Vérification | Résultat connu | Portée |
| --- | --- | --- |
| Suite Python sous Windows | PASS : 158 tests | Contrats, packages, refus, parcours autorisés, MCP, hooks, board, recette de couture synthétique et profil d’installation Windows |
| Rendu du board synthétique | PASS : pixels examinés | Lisibilité, légende, repères et échelle relative ; aucune qualification d'un vrai vêtement |
| Blender 5.2.2 LTS | PASS : essai natif indépendant | Import, panneaux existants, erreur après mutation, blocage, restauration et reprise |
| Recette native de couture | PASS : fixtures isolées, deux résolutions pour les trois sondes physiques | Gravité, couture, contact réellement sollicité, sous-ensemble local puis complet, consolidation et conservation des ouvertures ; voir le rapport 0.5.0 |
| Revue des rendus natifs | Effectuée sur les fixtures synthétiques | Contact et assemblage de fragments cylindriques ; aucune qualification d'une vraie emmanchure ni d'une robe |
| Distribution 0.5.0 | Archive source vérifiée localement | Voir la release GitHub et les contrôles de version de l’installation locale |
| Installation Codex sous Windows | PASS lors de l'installation locale 0.4.0 | Nouveau serveur : 29 outils et fichiers de runtime vérifiés ; rechargement d'une conversation existante à vérifier séparément |
| Connexion Comfy officielle | PASS lors du diagnostic local antérieur | Découverte du serveur existant ; ne prouve pas la compatibilité de chaque workflow GPU |
| Image de production via Codex Image | NOT_EXECUTED dans les tests du plugin | Fournisseur explicitement simulé ; pas de reçu réel inventé |
| Génération GPU, fitting, bake Cloth complet | NOT_EXECUTED | À qualifier sur références, nœuds et modèles réels |
| Rig, animation et import Unreal d'un vrai asset | NOT_EXECUTED | À qualifier selon la destination |
| Installation Codex macOS/Linux | NOT_EXECUTED | Distincte de l'exécution des tests Python sur ces systèmes |

Les rapports des corrections [0.2.0](references/validation-pipeline-0.2.0.md),
[0.3.0](references/validation-lifecycle-0.3.0.md) et
[0.4.0](references/validation-fabrication-0.4.0.md) et
[0.5.0](references/validation-sewing-0.5.0.md) décrivent les essais locaux.
Les journaux `work/` mentionnés dans ces rapports sont conservés localement et
**ne sont pas distribués**. Pour une preuve publique reproductible, consulter
[les exécutions CI et leur commit](https://github.com/leuzeus/atelier-3d/actions/workflows/ci.yml).
Ne pas transférer le résultat d'un ancien commit vers un nouveau.

## Reproduire les contrôles logiciels

Depuis la racine du dépôt avec Python 3.11+ :

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/studio.py tools
pwsh -NoProfile -File scripts/validate_contracts.ps1
New-Item -ItemType Directory -Force dist | Out-Null
python -B scripts/package_plugin.py --output dist/atelier-3d-validation.zip
```

Les tests n'appellent aucun moteur de génération et ne nécessitent pas de GPU.
La CI exécute la suite sous Windows/Python 3.11 et Linux/Python 3.13, avec
construction de l'archive. Deux tests cmd/PowerShell sont explicitement sautés
sur Linux. L'installation du plugin dans Codex n'est pas testée par ces runners.

La validation indépendante JSON requiert PowerShell 7 (`Test-Json`). Les schémas
externes des manifestes peuvent être passés à `scripts/validate_contracts.ps1`
avec `-OfficialSchemaDirectory` ; ils ne sont pas téléchargés par la CI.

`tests/native_lifecycle_smoke.py`, `tests/native_sewing_smoke.py` et
`tests/native_continuity_smoke.py` et `tests/native_multigarment_smoke.py` sont des essais
Blender séparés : ils doivent s'exécuter
dans un processus Blender dédié, avec scène vide et son dossier de travail de test,
jamais dans la scène de production ouverte. Examiner ce script avant exécution.
Ils ne font pas partie de `unittest discover` ni des jobs GitHub Actions. Utiliser
`--background --factory-startup --disable-autoexec --python-exit-code 1` pour que
les erreurs Python échouent réellement au niveau du processus. Pour le script
de couture, consulter [les commandes et limites](references/validation-sewing-0.5.0.md).

## Qualification de production à effectuer

Conserver versions, licences, modèles, paramètres et preuves dans le projet.

1. Vérifier les connexions effectives et les nœuds/modèles de chaque template avant
   de lancer un job ; qualifier les limites mémoire et l'usage des images originales.
2. Scénario vêtement : références réelles approuvées, dossier technique, packages,
   vue éclatée Codex Image, proportions et board humainement validé ; placement,
   mannequin de collision, drapé borné et comparaison des pixels aux originaux.
3. Scénario articulé : composants séparés, références multivues cohérentes, jobs
   indépendants, validation d'identité/échelle, assemblage par ancrages et articulation.
4. Provoquer une erreur limitée dans une copie, vérifier le blocage et la reprise.
   Une soumission Comfy incertaine doit être réconciliée sans envoi en double.
5. Vérifier retopologie, UV, matières, rig, poids et dégagements selon le besoin.
   Pour un jeu, inspecter l'import dans le moteur, les animations et le budget.
6. Présenter les livrables et preuves du candidat exact avant la décision finale.

Ces scénarios restent `NOT_EXECUTED` tant que leurs preuves réelles ne sont pas
produites. Un champ `PASS`, une empreinte ou un compte rendu rédigé par l'assistant
ne remplace pas une mesure, une image examinée ou une acceptation humaine.
