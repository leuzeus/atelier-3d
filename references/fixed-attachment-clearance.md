# Réserve des attaches avant couplage

Une cible anatomique immobile située à moins de la réserve du collider rend
les contraintes incompatibles. Corriger les sommets libres du tissu ne peut
pas résoudre cette contradiction. Le contrôle optionnel `attachment_clearance`
l'identifie avant `couple_source_seams` et conserve les guides pour diagnostic.

## Entrée publique

Le paramètre de composant est disponible dans les fonctions existantes de
préparation et de reconstruction de `garment-guide-policy` :

```json
{
  "attachment_clearance": {
    "method": "FIXED_SOURCE_TARGET_BODY_RESERVE_V1",
    "collider_object": "Nom explicite du collider mesuré",
    "recipe_ref": {"path": "recipe.json", "sha256": "empreinte du fichier"},
    "budgets": {"max_seconds": 30, "max_candidates": 128}
  }
}
```

La référence de recette doit être identique à celle des autres consommateurs
du composant. Les références anatomiques et les triangles natifs sont requis.
Le corps est vérifié contre le profil remesuré. L'identité pleine précision du
profil est distincte de l'identité native du collider Blender, calculée en
mètres arrondis à sept décimales ; les deux sont conservées dans le rapport.
La réserve provient du champ `outer_thickness_cm` de ce collider précis.

Les points contrôlés sont ceux déjà liés aux UV source par le producteur de
guides. Le contrôle ne choisit pas de région corporelle, ne crée pas d'attache
et n'en déplace aucune. Un conflit produit `PARTIAL_GUIDES` et
`NOT_EXECUTED_FIXED_ATTACHMENT_CLEARANCE_CONFLICT` pour le couplage. Un délai
ou un budget épuisé refuse le calcul sans lancer le couplage. En l'absence de
l'option, les rapports et coordonnées historiques restent identiques.

## Noyau réutilisable

`a3d.attachment_clearance` expose trois fonctions Python standard :

- `check_attachment_clearance` vérifie une cible fixe ;
- `check_attachment_clearances` vérifie une liste ordonnée avec un corps et
  un budget communs ;
- `propose_attachment_clearance` recherche une variante sur le seul rayon
  défini par un point de trajet et un décalage explicitement fournis.

Les bornes de boîtes et les distances aux triangles utilisent les valeurs
binaires représentées, converties en rationnels exacts. Chaque succès couvre
tous les triangles fournis. Un témoin exact suffit à prouver un conflit,
même si le contrôle s'arrête avant les triangles suivants. Les coordonnées
réellement arrondies d'une proposition sont recertifiées. Les entiers qui
perdraient de l'information lors de leur conversion sont refusés.

Les budgets bornent le temps, les cibles, les visites de triangles et la
taille du corps. Les observations terminées sont incluses dans les refus du
noyau. Les interruptions externes sont propagées. Le temps observé est retiré
du rapport de guide déterministe, mais reste disponible dans les reçus de run.

La recherche de variante ne suppose pas une distance monotone, ne promet pas
le déplacement minimal et n'adopte jamais automatiquement la proposition.
Elle garde la direction déclarée, les repères corporels et les patrons. Une
translation appliquée à une cage doit recertifier sa cible réellement
sauvegardée, puis reprendre les contrôles affectés du candidat entier.

## Portée

Ce contrôle établit uniquement une condition nécessaire aux points fixes.
Une distance non signée ne classe pas un point à l'intérieur ou à l'extérieur
du corps. Les faces textiles, auto-contacts, coutures, couches, matière, Cloth,
fitting et décision artistique gardent leurs contrôles propres. Une marge de
calcul explicitement déclarée n'est pas une aisance de conception.

Le [bilan du 8 octobre](automation-joint-placement-20261008.md) contient les
preuves sur les quinze attaches réelles et le candidat isolé du col.
