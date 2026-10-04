# Fonctionnalités et limites

Présentation des parcours disponibles dans les sources. Leur qualification est décrite dans [VALIDATION.md](../VALIDATION.md) ; une capacité présente ne vaut pas acceptation d’un asset.

## Ce que fait le plugin

- Analyse les références, les pièces, les matériaux, les proportions, les parties
  cachées et les articulations ; distingue observations et hypothèses.
- Propose une pipeline par composant, explique les alternatives et conserve la
  décision humaine avant de construire les packages.
- Produit un dossier technique et un board à examiner avant la reconstruction.
- Orchestre les jobs Comfy locaux et les opérations Blender avec preuves,
  copies de travail, checkpoints et reprise après erreur.
- Exige des validations liées au candidat actuel avant finition, comportement
  et livraison. Pour un jeu, l'import dans le moteur fait partie des contrôles.

| Méthode | Usage | Données de construction |
| --- | --- | --- |
| `PATTERN_SEWN` | Vêtements et composants textiles | Patrons polygonaux en cm, panneaux, coutures, matières et simulation préparée |
| `MULTIVIEW_PART` | Pièces volumiques séparées | Vues propres cohérentes, dimensions, ancrages et reconstruction par pièce |

Un même asset peut utiliser les deux méthodes. Une dépendance indisponible ne
permet pas de substituer discrètement une autre méthode à celle approuvée.

## Board textile en trois parties

Le board est construit depuis **les images de référence originales**, puis
présenté à l'utilisateur pour valider le découpage avant la 3D.

1. **Vues orthographiques** : face, profil et dos, cadrage et échelle communs,
   proportions comparées aux références et zones extrapolées signalées.
2. **Décomposition du vêtement** : illustration produite avec **Codex Image** à
   partir des originaux et de la liste exacte des pièces. Le compositeur ajoute
   IDs, noms, traits de rappel, matières, dimensions et caractéristiques.
3. **Patrons 2D de fabrication** : contours issus des packages, avec coupe,
   couture/piqûre, plis ou milieu, droit-fil, marges, quantités et repères
   d'assemblage appariés. Toutes les pièces utilisent la même échelle.

`studio_prepare_exploded_view` prépare la demande d'image ; Codex appelle ensuite
le générateur intégré et `studio_register_exploded_view` enregistre son résultat
réel. Studio ne lance pas lui-même ce générateur. Le board final est un SVG autonome
accompagné d'un dossier HTML. Il sert à la revue du découpage pour la 3D ; ce n'est
pas une certification de patronage ni une planche de coupe à imprimer en taille réelle.

Une modification des images, du dossier, des packages ou du board invalide
l'approbation correspondante. Voir [le contrat de fabrication](fabrication-board.md).

## Templates ComfyUI réutilisables

Le [catalogue des templates](../workflows/comfy/README.md) décrit les deux bases
enregistrées : `reference-sd15` pour préparer une image de référence depuis un
original et `hunyuan-multiview` pour reconstruire une partie volumique depuis
les vues de face et de gauche. Il fournit les paramètres, exemples et limites.

Studio charge le graphe API enregistré dans `workflows/comfy/registry.json`,
applique les paramètres déclarés et conserve le workflow exact de chaque job.
Réutiliser une base adaptée au besoin ; une nouvelle structure ou un workflow
externe exige une variante revue et enregistrée. La compatibilité doit être
validée sur les modèles et nœuds installés avant exécution. Les bases fournies
restent à qualifier ; elles ne génèrent pas les panneaux `PATTERN_SEWN`.

## Préparation et reprise

La [reprise après un refus](preparation-recovery.md) distingue une
limite technique des erreurs de préparation. Une limite impose de présenter
le choix entre technique approuvée et contrat supporté ; un défaut confirmé
ou une pièce manquante appelle une correction ou une préparation ciblée qui
conserve le découpage approuvé.

Le [contrôle de complétude des pièces](piece-completeness.md)
affiche la couverture locale et globale du candidat Blender, détecte absences
et doublons et empêche qu'un composant complet valide tout le vêtement.
Voir [la portée testée](../VALIDATION.md) pour la vérification native restante.

Avant d’exécuter du code via Blender MCP, le plugin demande explicitement
l’autorisation de l’utilisateur et attend sa réponse affirmative. Voir
[le protocole Blender](blender.md). Cette consigne ne modifie pas
les permissions MCP de Codex.

La [préparation native des patrons](pattern-preparation.md) contrôle
la coupe et les correspondances, dérive un maillage régulier et mesure sa
préforme autour du corps avant tout Cloth. Elle conserve les patrons approuvés,
produit les vues neutres/wireframe et transmet sa géométrie exacte à l'assemblage.
Ses états `READY`, `NEEDS_CORRECTION` et `NEEDS_CLARIFICATION` restent distincts
d'une qualification physique ou d'une acceptation finale.

Le parcours `PATTERN_SEWN` dispose d'une [refonte locale de l'assemblage](pattern-assembly.md) :
préforme sourcée, Cloth court, fermeture bornée, consolidation géométrique,
détente continue et drapé distinct. Les patrons approuvés restent immuables.
Voir [VALIDATION.md](../VALIDATION.md) pour la portée réellement testée ; une
consolidation ne qualifie pas le fitting, le comportement ou l'export.

Les [renforcements après l'étude OpenSew](opensew-improvements.md)
ajoutent la métrique source par face pendant Cloth, les contacts entre frames,
un enfilage mesuré et l'ordre explicite des couches. Leurs coupons ont une
portée limitée ; les anciens PASS gardent leur périmètre et le fitting réel
reste non qualifié. Ces améliorations locales de la version 0.6.7 sont
incluses dans la version 0.6.8.

## Limites actuelles

Les exemples sont synthétiques : ils ne démontrent pas la fidélité d'un vêtement.
Les templates SD1.5 et Hunyuan doivent être adaptés et qualifiés sur les nœuds et
modèles présents. Aucun modèle n'est téléchargé automatiquement.

La recette native sépare contours précis, maillage de simulation et surface
cousue. Elle vérifie masse par sommet, contexte de collision et essais physiques
locaux avant la toile complète, puis conserve les ouvertures et pièces amovibles.
Les placements sont limités aux panneaux plats ou enroulés ; le fitting complexe,
le bake d’animation, la retopologie, les UV, le rig et les exports restent des travaux
assistés à exécuter et à vérifier sur chaque asset. Les contrôles numériques
ne certifient pas l'apparence ni la véracité d'une preuve déclarée.

Les hooks et les scripts Blender ne constituent pas un bac à sable du système.
Une mutation interrompue bloque la suite jusqu'à restauration contrôlée. Un job
Comfy dont la soumission est incertaine n'est pas renvoyé automatiquement.

[Retour à la documentation](index.md).
