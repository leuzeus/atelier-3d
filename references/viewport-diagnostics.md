# Cadrage visuel et diagnostic des échecs Cloth — 0.5.4

## Cadrer un candidat sans modifier sa construction

Lire les noms exacts par `inspect`. Demander à `studio_blender_operation` :

```json
{
  "project_root": "<racine absolue du projet>",
  "operation": "frame_view",
  "arguments": {
    "component_id": "garment.coat",
    "object_name": "<nom exact du mesh actuel>"
  }
}
```

Transmettre le code retourné exactement à `execute_blender_code`. Le dispatcher
vérifie la scène connectée, son chemin de travail, l'identité du mesh et le SHA du
package. Pour une partie MULTIVIEW_PART assemblée, il vérifie le SHA de l'artefact
sur le mesh ou son parent de composant. Un préfixe de nom seul ne suffit pas.

Le mesh doit déjà être visible et sélectionnable dans le view layer courant ;
rester en mode Objet, dans une vue 3D normale sans verrou. Les scènes étrangères,
archives, objets masqués, mode Édition, vues caméra/quad et verrous sont refusés.
Le cadrage restaure la sélection et l'objet actif, conserve orientation et
projection, et ne modifie ni caméra, transforms, géométrie, matériaux ni visibilité.
Il désactive momentanément l'animation du cadrage, puis restaure cette préférence.
Il ne sauvegarde aucun fichier et ne crée pas de mutation en attente.

Capturer ensuite `get_screenshot_of_area_as_image(area_ui_type="VIEW_3D")` et ouvrir
ses pixels contre la référence originale. Les objets voisins restent visibles et
peuvent masquer le candidat : le cadrage n'est pas une isolation automatique.
Une capture, un cadrage ou un diagnostic ne constitue jamais une acceptation.
Les rendus écrits sur disque suivent les contrats de preuves du projet.

## Conserver un échec réellement évalué

Depuis 0.5.9, lire aussi [les mesures de déplacement](cloth-motion.md) : sommet
source/pièce responsable, excursion depuis le départ et incrément réellement
évalué. Le dépassement de budget demeure un FAIL et ne prouve pas seul une instabilité.

Quand `simulate_object` échoue après évaluation, avant retrait de Cloth et du
mesh temporaire, la tentative conserve `diagnostic.json` et, si les coordonnées
sont finies et correspondent à la topologie, `diagnostic.svg`. `failure.json`
référence le diagnostic par chemin/SHA ; le diagnostic référence son SVG.

Le JSON contient le package, la recette complète et son SHA, le mapping source,
le binding technique, le checkpoint et le contexte physique réellement exécuté,
les frames évaluées, positions initiales/évaluées/rest, faces, panneaux, pins,
coutures et indices du mesh complet. Il localise les arêtes compressées/étirées,
arêtes courtes, faces dégénérées, écarts initiaux/finals par paire de couture et
pénétrations au-delà du seuil, avec l'objet collider. Les profondeurs utilisent
le même test signé de proximité que le contrôle physique ; elles ne constituent
pas une preuve générale d'intersection pour une surface ouverte.

Le SVG montre les projections XY, XZ et YZ des positions réellement mesurées,
les arêtes hors limites en rouge et les pénétrations en violet. C'est un tracé
technique d'un échec, jamais une image générée du vêtement ni une vue d'acceptation.
Les valeurs non finies sont conservées comme `null` et interdisent ce tracé.

L'essai reste **FAIL**, sans nouveau reçu local PASS ni autorisation de full.
Le pending d'échec reste protégé jusqu'à `restore_checkpoint`. L'exception
d'origine est conservée ; une collecte impossible ajoute une note explicite.
Un échec survenu avant évaluation peut ne pas disposer de positions de diagnostic.

Demander `inspect_sewing_failure` avec `component_id` et `attempt_dir`, chemin
relatif `.a3d/blender/sewing/attempt-...`. Il vérifie chemin, SHA, composant,
statut FAIL, scope et binding, puis retourne les mesures et le chemin du tracé.
Ouvrir le SVG et lire les positions complètes dans le JSON si nécessaire.
Cette lecture reste possible avec pending, après restauration, et après
modification de la recette : elle décrit un état historique, pas le candidat actuel.
Les anciens échecs dépourvus de diagnostic ne sont pas reconstitués artificiellement.

## Taille de l'essai local

`trial_pieces` sélectionne des **pièces entières**. La version 0.5.4 en rapporte
les étendues, les coutures omises, les correspondances globales et les supports
existants. Un panneau de buste prolongé en jupe reste long ; ce sous-ensemble ne
doit pas être présenté comme un coupon spatialement limité à l'emmanchure.

Un coupon régional peut être justifié après localisation du défaut, mais exige
des limites dans les coordonnées du patron, mapping de tous les sommets/faces,
coutures tronquées et supports temporaires vérifiables. L'ajouter maintenant
sans ces données risquerait de déplacer le problème par une fixation inventée.
Cette version conserve le découpage et les supports approuvés ; elle n'introduit
pas de découpe spatiale automatique. Ajuster d'abord le placement ou la physique
sur la base des mesures, puis refaire l'essai local correspondant.
