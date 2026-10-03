# Pièces absentes dans la préparation Blender : contrôler et afficher la complétude

Date : 2026-10-03 (America/Toronto)
Statut : présentation du rapport projet corrigée ; contrôle automatique implémenté et installé dans la version 0.6.8 ; vérification native de la correction non exécutée.
Priorité proposée : haute pour la fiabilité de la revue et des transitions de production.

## Demande utilisateur

« Le nombre de piece chargé dans blender devrait etre validé ».
L'utilisateur a compté dix pièces dans les dernières captures Blender alors que la planche approuvée comporte quinze pièces textiles et une boucle rigide.

## Résumé du problème

La dernière capture neutre montre bien dix panneaux du manteau. Elle ne couvre pas les cinq autres pièces textiles prévues au découpage. Les patrons de ces pièces existent ; leur préparation Blender n'a pas abouti.

Le rapport de progression mentionne dix panneaux et décrit séparément les blocages. Il manque cependant, dans la présentation observée, un bilan explicite et immédiatement visible de couverture globale : **10/15 pièces textiles préparées ; 5 absentes de ce résultat**. Une capture partielle peut ainsi être interprétée comme la préparation complète du vêtement.

Ce constat ne démontre ni une perte des patrons source, ni un échec d'import de cinq objets déjà construits. Il ne démontre pas non plus que tous les contrôles internes de cardinalité sont absents : leur couverture doit être auditée. Le bogue rapporté concerne la réconciliation entre découpage attendu, résultat réellement présent et information présentée à l'utilisateur.

## Cas observé et périmètre des preuves

- Dépôt : `G:/projets/atelier-3d`.
- Projet : `work/robe-bleu-nuit-nouveau-20261003`.
- Version de production rapportée dans le chat principal : Atelier 3D 0.6.7.
- Essai du manteau : `attempt-fc3d1e58157a48fe8f4acb7768b7f1ee`.
- Essai capuche/épaules : `attempt-f8885293f2494aa4ae58640f17908855`.
- Vérification de ce signalement : lecture du manifeste d'atlas et du rapport de progression, puis examen visuel de la capture neutre et de la planche contact des quinze patrons.
- Aucun inventaire de la session Blender vivante n'a été lancé dans cette conversation latérale. Les chiffres observés portent sur les artefacts de ces essais ; une scène modifiée ultérieurement doit être inspectée à nouveau.

## Inventaire attendu et observé

Les identifiants doivent être qualifiés par composant ; un nom d'objet Blender n'est pas une identité de pièce suffisante.

| Repère | Composant | Identifiant de pièce | Présence dans le résultat textile observé |
|---|---|---|---|
| A01 | garment.coat | front-left | Présente |
| A02 | garment.coat | front-right | Présente |
| A03 | garment.coat | back-left | Présente |
| A04 | garment.coat | back-right | Présente |
| A05 | garment.coat | inner-front | Présente |
| A06 | garment.coat | collar | Présente |
| A07 | garment.coat | sleeve-left | Présente |
| A08 | garment.coat | sleeve-right | Présente |
| A09 | garment.coat | cuff-left | Présente |
| A10 | garment.coat | cuff-right | Présente |
| A11 | garment.hood-yoke | hood-left | Absente |
| A12 | garment.hood-yoke | hood-right | Absente |
| A13 | garment.hood-yoke | yoke-upper | Absente |
| A14 | garment.hood-yoke | yoke-lower | Absente |
| A15 | garment.belt | belt | Absente |

Total textile : **15 attendues, 10 représentées, 5 absentes**.
La boucle `prop.buckle` constitue un seizième élément, rigide : elle doit être suivie séparément. Le rapport indique un GLB reçu, mais sans import ni qualification Blender ; elle ne doit pas augmenter le compteur textile.

## Blocages expliquant les absences

1. **Capuche et épaules — quatre pièces** : le rapport indique `NEEDS_CORRECTION`, aucun maillage produit. Des bords sont partagés entre les coutures de base de capuche et les attaches d'empiècement ; deux ambiguïtés de crans sur des coutures d'une même pièce sont également signalées.
2. **Ceinture — une pièce** : le contrat local refuse l'essai prévu avec un seul panneau et sa fermeture. Aucun essai natif de ceinture n'a été lancé.
3. **Manteau — dix pièces présentes** : le résultat est encore `NEEDS_CLARIFICATION` (cinq ambiguïtés de crans, préforme et appuis manquants). Sa complétude locale ne signifie pas qu'il est prêt pour la simulation.

Ces blocages de préparation et le défaut de présentation de la complétude doivent être traités séparément. Ajouter un compteur ne produit pas les pièces manquantes et ne résout pas les contrats de couture.

## Reproduction à partir des artefacts existants

1. Ouvrir `work/robe-bleu-nuit-nouveau-20261003/preparation/atlas/index.html` et son `manifest.json` : quinze entrées A01 à A15, réparties 10 + 4 + 1.
2. Comparer avec la planche approuvée `.a3d/outputs/construction-c1f0612ceb914bb284d2129480439984/board.svg` sous ce projet.
3. Ouvrir `.a3d/blender/pattern-preparation/attempt-fc3d1e58157a48fe8f4acb7768b7f1ee/neutral-front.png` : dix formes distinctes, correspondant au manteau.
4. Consulter `production/etat-construction.html` : dix panneaux à plat ; aucun maillage capuche/épaules ; essai ceinture non lancé.
5. Constater que l'utilisateur doit rapprocher plusieurs sections et documents pour obtenir le bilan global 10/15 et la liste des cinq absentes.

Il n'est pas nécessaire de relancer Blender ou ComfyUI pour reproduire ce défaut de présentation.

## Comportement attendu

### Contrôle de présence et d'identité

- Construire l'inventaire attendu depuis les packages liés à la révision approuvée et le dossier de construction ; vérifier leur cohérence avec la planche. L'atlas est une aide de lecture, pas une nouvelle autorité.
- Inspecter le résultat Blender réel et sa correspondance avec les pièces source, avec les identifiants `(component_id, piece_id)` et leur provenance.
- Comparer les identités et multiplicités attendues aux identités réellement représentées. Rapporter pièces absentes, doublons, pièces inattendues et identités sans correspondance.
- Ne pas compter les objets Blender : un objet peut contenir plusieurs panneaux. Ne pas compter seulement les îlots connexes : l'assemblage peut relier plusieurs pièces tout en préservant leur identité source.
- Exclure mannequins, supports, témoins et objets d'anciennes variantes. Un objet homonyme ou une pièce provenant d'un ancien package ne doit pas satisfaire le contrôle.
- Distinguer présence dans le maillage, présence dans la scène, visibilité dans la capture, et acceptation technique. Une pièce masquée n'est pas automatiquement perdue ; une pièce visible n'est pas automatiquement qualifiée.
- Si la correspondance source est indisponible ou ambiguë, indiquer « non vérifiable » au lieu de déduire la complétude du seul nombre de formes.

### Périmètre local et global

- Chaque opération indique explicitement son périmètre. Pour cet essai : « Manteau : 10/10 panneaux présents ».
- Le bilan projet reste visible : « Vêtement : 10/15 pièces textiles préparées ; manquent les deux demi-capuches, les deux empiècements et la ceinture ».
- Un aperçu partiel reste autorisé et utile ; il doit être étiqueté partiel, avec ses exclusions et blocages. Il ne constitue pas une validation de complétude globale.
- Une transition qui exige le vêtement complet ne doit pas passer si une pièce requise manque ou si son identité n'est pas vérifiable. Un essai volontairement limité à un composant doit garder sa portée locale explicite.
- Appliquer le contrôle après préparation/import et avant les jalons qui dépendent de la présence complète des pièces, notamment assemblage global, simulation globale et validation finale.

### Restitution utilisateur et preuve conservée

- Afficher le décompte attendu/présent et les absences près des captures, dans le rapport et dans le message du chat principal.
- Conserver un résultat structuré avec révision du projet, empreintes des packages et de l'artefact Blender inspecté, périmètre de contrôle, identifiants attendus/observés, anomalies et raisons des absences.
- Invalider un ancien résultat de complétude lorsque la scène, les packages ou la correspondance source changent ; ne pas réutiliser une preuve d'une autre variante.
- Séparer les statuts « inventaire complet », « préparation acceptée », « assemblé », « simulation exécutée » et « validation visuelle ».

## Critères d'acceptation proposés pour la correction

1. Cas présent : le contrôle local du manteau établit 10/10 ; le bilan global affiche 10/15 et les cinq identifiants manquants exacts. Aucun verdict de vêtement complet.
2. Nombre total correct mais une pièce remplacée par un doublon : détection du doublon et de l'identité absente.
3. Quinze panneaux dans un seul objet : contrôle fondé sur la correspondance source, sans faux échec lié au nombre d'objets.
4. Pièces cousues dans un maillage connecté : leur identité reste vérifiable sans exiger quinze îlots.
5. Objet témoin, mannequin ou ancienne variante : ne contribue pas à la complétude du candidat courant.
6. Pièce présente mais masquée ou hors cadre : diagnostic de visibilité distinct de la présence, capture explicitement partielle.
7. Boucle rigide : inventaire distinct, jamais comptée comme seizième panneau textile.
8. Package ou scène changé : l'ancien contrôle ne vaut plus preuve pour le nouveau candidat.
9. Correspondance source manquante : résultat non vérifiable ; aucune validation globale implicite.
10. Sorties utilisateur : alerte de pièces manquantes visible dans la page de revue et résumée dans le chat, sans consultation obligatoire des logs.

Ces tests sont des exigences proposées, pas des tests exécutés dans ce signalement.

## Limites et suite

### Correction dans les sources — 2026-10-03

Le contrôle `a3d/piece_inventory.py` et son adaptateur natif
`blender/piece_inventory.py` réconcilient les identités des packages liés à la
planche approuvée avec les faces du candidat. Les opérations retournent un
bilan local/global, avec absences, doublons et correspondances non vérifiables.
La préparation crée une page de revue avec ce bilan près des images ; les
skills demandent de le restituer aussi dans le chat. L'inspection inclut les
candidats qui portent uniquement `a3d_source_component_id`. Les cartes source
sont conservées au gel, y compris après consolidation explicite des coutures.

Les admissions natives vérifient la couverture du composant avant Cloth et
montage, et la couverture globale avant validation/export/comportement ou
après import d'assemblage global. Les jalons canoniques d'assemblage et de
validation finale exigent une preuve actuelle liée aux fichiers de scène,
packages et correspondances. Le [protocole](references/piece-completeness.md)
précise la portée et les limites des observations sur disque.

Les tests automatisés couvrent le cas 10/15, la substitution par un doublon,
plusieurs pièces dans un objet, un maillage connecté avec identités source,
les témoins/anciennes variantes, les pièces masquées, la séparation des
accessoires rigides, l'invalidation et les sorties de revue. Les appels
Blender sont simulés dans ces tests : aucun nouvel inventaire de la scène
vivante ni qualification du vêtement réel n'est revendiqué par cette correction.

### Limites du signalement initial

Le signalement documente les preuves disponibles et le contrôle attendu. Aucune correction du plugin, aucun changement des patrons approuvés, aucune manipulation de la scène ni relance de simulation n'a été effectué. L'emplacement précis du défaut dans le code et les contrôles déjà existants restent à auditer avant implémentation.

## Suivi dans le chat principal — 2026-10-03

Le rapport `work/robe-bleu-nuit-nouveau-20261003/production/etat-construction.html` affiche désormais « 10/15 pièces textiles préparées ; 5 manquantes » en tête et près des deux aperçus. Il nomme les cinq pièces absentes et distingue couverture locale, globale, présence dans la scène, visibilité et qualification. Le contrôle structuré des artefacts est conservé dans `production/coverage-audit.json`.

Une inspection native de la session vivante a été exécutée en lecture seule. Son résultat `objects=[]` est incomplet pour ce cas : `blender/operations.py:inspect` filtre les objets portant `a3d_component_id`, alors que `prepare_pattern_assembly` n'attribue cette propriété qu'à un résultat `READY`. Le candidat actuel conserve `a3d_source_component_id` et reste `NEEDS_CLARIFICATION`.

Les outils généraux Blender ont confirmé un seul objet maillé `A3D.Prepared.garment.coat`, visible, sans modificateur, et aucun objet de capuche/épaules, ceinture ou boucle dans la hiérarchie courante. La liste native vide ne prouve donc pas une scène vide. Les résumés disponibles ne fournissent pas une nouvelle correspondance par panneau dans le mesh vivant ; cette limite reste explicitement `NOT_REMEASURED`. La capture courante du viewport est distante et presque de profil, insuffisante pour compter chaque panneau. Voir `production/coverage-live-inspection.json`.

La comparaison par identité et multiplicité concerne le maillage dérivé sauvegardé, lié aux packages approuvés ; elle ne se fonde pas sur le seul nombre d'objets. Aucun jalon global n'a été validé. Aucun patron, code du plugin ou objet de la scène n'a été modifié par ce suivi. Les dix critères d'acceptation ci-dessus restent des exigences pour une future correction du plugin, et non une suite de tests produit déjà passée.
