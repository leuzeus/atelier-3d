# Reprise cousue et fitting séparé — 0.6.1

Un essai local PASS est un résultat physique sur les seuls panneaux déclarés.
La copie principale conserve auparavant leur placement initial. Pour reprendre
ces coordonnées, utiliser les opérations natives suivantes dans
`studio_blender_operation`, puis transmettre son code exact au MCP Blender.
Le bootstrap doit identifier la version installée et sa racine. Aucun script de
développement, modification du cache ou collage de coordonnées n'est nécessaire.

## 1. Appliquer le résultat local sans collider

```json
{
  "operation": "apply_sewn_result",
  "arguments": {
    "component_id": "garment.coat",
    "recipe_path": "recipe-free.json",
    "result_path": ".a3d/blender/sewing/attempt-ID/result.json",
    "result_sha256": "SHA256_DU_RESULTAT_IMMUABLE"
  }
}
```

Fournir aussi `project_root` à l'outil. Garder la recette exacte du PASS, son
package, sa géométrie de départ et son mapping. Le résultat doit être local,
PHYSICS_ONLY, sans collider ni bâti. Son binding natif inclut recette, phase,
mesh, mapping, contexte et version Blender ; un résultat périmé est refusé.
Les résultats 0.6.0 restent compatibles : les cm et l'ordre croissant des indices
source se déduisent de ce binding et des panneaux sélectionnés. Les nouveaux
résultats les déclarent explicitement.

L'opération crée une copie de simulation, un mapping et des reçus immuables.
Seuls les indices du sous-ensemble reçoivent les coordonnées du PASS ; les autres
gardent leurs coordonnées Blender actuelles. L'objet précédent est archivé.
Rest 2D, faces, limites/bords source, coutures et poids de maintien sont conservés.
Le reçu porte `PARTIAL_ASSEMBLY`, pas une qualification de tout le vêtement.
Le contrôle global des orientations peut encore refuser le prochain essai.

## 2. Terminer l'assemblage libre

Pour préparer une autre recette depuis les coordonnées cousues :

```json
{
  "operation": "prepare_sewn_stage",
  "arguments": {
    "component_id": "garment.coat",
    "recipe_path": "recipe-next-assembly.json",
    "stage": "assembly"
  }
}
```

Cette transition conserve la géométrie actuelle. Elle interdit de changer mesh,
placements source, coutures et pins. La recette reste sans collider, fitting_plan
ou fitting_tacks, avec une raison explicite. Un `experimental_prefit` optionnel
opère sur cette copie, sans reconstruire les panneaux à plat. Avec
`preserve_reference_positions: true`, les panneaux de référence gardent leurs
positions actuelles et les partenaires mobiles visent leurs points de couture.
Ce maintien ne modifie ni les pins source ni les coutures. Les contraintes
contradictoires, triangles déformés, orientations opposées et budgets dépassés
restent des refus ; ce solveur ne garantit pas de placement admissible.

Après changement de recette ou de placement, passer un nouvel essai local qui
couvre les interfaces à compléter, notamment les emmanchures. Puis appeler
`simulate_sewn` avec la recette exacte, `phase: "mount"`, `scope: "full"` et
`purpose: "assembly"`. Sans changement, le reçu de transfert peut reprendre le
PASS local d'origine. Un nouveau FAIL au binding actuel interdit cette reprise.
La règle de deux échecs complets reste active.

Full évalue tous les panneaux et toutes les coutures permanentes du composant.
La simulation désactive les collisions ambiantes : seules les collisions
déclarées interviennent. Un PASS libre donne `ASSEMBLY_PHYSICS_ONLY`, conserve
les coordonnées complètes et leur résultat immuable. `freeze_sewn` le refuse :
le fitting est une étape distincte. Une courte convergence ne prouve pas une
stabilité longue, le mouvement de jeu ou une acceptation artistique.

## 3. Entrer dans le fitting sur le corps identifié

Préparer une copie de recette avec le mannequin réel ou le proxy explicitement
identifié, son mesh/pose/dimensions/épaisseurs de collision, et les sections
homologues du [fitting mesuré](measured-fitting.md). Appeler
`prepare_sewn_stage` avec `stage: "fitting"`. La transition exige le résultat
full assembly PASS lié au mesh actuel, au mapping et à la recette précédente.
Elle conserve l'assemblage complet, vérifie les colliders et refuse les contacts
initiaux inadmissibles. Elle ne remodèle pas le corps pour faire passer le vêtement.

Une réparation initiale optionnelle peut être déclarée dans cette recette :

```json
"contact_recovery": {
  "source_ref": "mesure-et-hypothese-de-contact",
  "clearance_cm": 0.02,
  "max_displacement_cm": 0.2,
  "max_passes": 2
}
```

Elle projette les sommets non fixés hors des surfaces déclarées. Les poids 1
restent immobiles ; le budget ne dépasse jamais la limite existante de la recette.
Chaque candidat repasse les mêmes contrôles de qualité, orientation et contact.
Le reçu expose déplacement mesuré, contexte et contrôles. Une réparation de
placement PASS n'accorde aucun PASS Cloth : requalifier local, puis full avec
`purpose: "fitting"`, avant `freeze_sewn`. Le fitting physique sur proxy n'établit
pas la compatibilité dimensionnelle d'un corps cible non mesuré.

## Reçus, refus et récupération

Conserver les chemins/SHA retournés pour les reçus de stage et de construction,
les mappings et les résultats d'essai. La transition ne réutilise pas de reçu
modifié, de map périmée ni de full d'une autre recette. Un échec de préparation
conserve un diagnostic `stage_transition`, sans accepter le candidat temporaire.
Lire `inspect_garment_failure`, ou `inspect_sewing_failure` après Cloth, puis
`restore_checkpoint` avant toute autre mutation. Les preuves historiques restent
sur disque. Aucun nouveau board n'est demandé pour cette reprise technique si
la coupe approuvée n'a pas changé.

Les pièces amovibles restent des composants indépendants. Une fermeture source
reste réversible ; seuls les liens permanents sont consolidés au freeze. Ne pas
interpréter un PASS de la robe principale comme une validation de la capuche,
du rig, de la collision en combat, de l'export Unreal ou du modèle final.
