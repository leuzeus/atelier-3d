# Généralité des automatisations de vêtements

Contrainte donnée par l'utilisateur le 5 octobre 2026 : tout script de
production doit être réutilisable pour les vêtements ; une limite doit être
expliquée lorsqu'une méthode ne peut pas couvrir tous les cas. Cette règle
complète le [programme en cours](automation-program.md).

## Entrées et responsabilités

Un algorithme de production reçoit des données structurées : pièces et rôles,
géométrie source, bords nommés, relations, couches, guides, corps et pose,
mesures homologues, recette et budgets. L'identité d'un vêtement ou d'une pièce
ne sélectionne pas un calcul particulier. Les chemins du projet, dimensions,
coordonnées et noms d'objets viennent des entrées vérifiées.

Une catégorie telle que manteau ne fournit pas automatiquement une aisance.
Une stature de 180 cm, un nombre de 15 pièces ou un nom de composant sont des
données du candidat courant, jamais des constantes du moteur. Les rôles
sémantiques et les domaines anatomiques servent à vérifier la correspondance
déclarée ; ils ne suffisent pas à affirmer qu'une méthode couvre toute coupe.

Les dossiers et manifestes propres à un vêtement enregistrent ses entrées,
décisions et preuves. Les anciens runners de campagne restent des témoins de
leur essai exact. Un nouveau runner destiné à être réutilisé prend ses chemins,
sélections et budgets en arguments ; ses résultats restent séparés des reçus
natifs et des décisions humaines.

## Domaines actuels et raisons des limites

| Capacité | Domaine pris en charge | Limite et justification |
| --- | --- | --- |
| Guides (`garment_guides`) | Torse, manche/manchette, ceinture, col, devant intérieur, capuche et empiècement, avec leurs repères source | Les autres rôles restent en attente. Le devant intérieur spécialisé exige actuellement une pièce centrale et un axe matériel vertical ; une autre construction nécessite un adaptateur explicite. |
| Intersection matière/plan (`intersect_guide_material_plane`) | Patron triangulé sourcé, guide par sections d'arc ou cage UV explicite, plan corporel mesuré et deux bords source déclarés | Une coupe doit former un chemin matériel unique entre ces bords. Un plan coplanaire, une branche, un domaine troué incompatible ou une couverture ambiguë est refusé : il ne définit pas la mesure unique demandée. Ce calcul n'est lié à aucune catégorie de vêtement. |
| Recherche UV (`CageLookup`) | Backend expérimental sur cage validée, bornes conservatrices des opérations barycentriques existantes | Le rejeu réel est plus lent ; le parcours exhaustif reste le comportement de production. L'index exige un opt-in explicite du noyau, sans interface publique d'activation. Les cas dont l'exclusion n'est pas prouvée gardent tous les candidats. Aucune catégorie de vêtement ni tolérance géométrique supplémentaire ne fournit une correspondance. Voir [la recherche de matière](cage-material-lookup.md). |
| Propositions de mesures (`propose_measurement_paths`) | Correspondances déclarées du torse ouvert, du col et des domaines de bras/poignet actuellement implémentés | Les rôles et domaines restent contrôlés. Un pantalon, une jupe ou un assemblage de manche différent réclame les correspondances nécessaires ; un rôle voisin ne fournit pas une homologie anatomique. Le noyau géométrique réutilisable ne constitue pas une prise en charge publique de ces correspondances. |
| Borne transverse (`transverse_capacity_bound`) | Manche ou manchette simple, une couture permanente unaire compatible, chemins homologues affines par morceaux | La preuve analytique concerne un segment matériel fermé par cette couture. Plusieurs panneaux, plis ou chemins portés obliques ne satisfont pas cette preuve. Une fermeture détachable n'est pas retypée pour entrer dans le domaine. |
| Régions corporelles (`body_region_sections`) | Domaines épaule–coude, poignet–coude et enveloppes de mains, explicitement reliés à l'adaptateur anatomique | Les régions de jambes ne sont pas déclarées par ce contrat. Un repère absent, une section ouverte ou une topologie incompatible reste non qualifié. Le vêtement ne choisit pas les mensurations et le code ne réduit pas le corps pour masquer un déficit. |
| Rejeu UV (`source_uv_witnesses`) | Writer régulier canonique et stockages `SOURCE_DOUBLE` ou `BINARY32` authentifiés | Le profil de maillage synchronisé reste explicitement refusé : son writer et son transport exacts ne sont pas encore rejoués par cette capacité. Une proximité numérique ne remplace pas cette provenance. |
| Provenance et reprise | Sources, recettes, code, reçus et checkpoints exacts | Une identité périmée ou une observation non authentifiée ne peut pas être admise par un raccourci propre au projet. La reprise conserve la portée du refus historique. |

Ces limites décrivent le domaine des capacités existantes. Elles ne valent
ni acceptation de placement, ni fitting, ni preuve que tout vêtement est déjà
pris en charge. Une extension ajoute ses données, ses correspondances et ses
preuves, puis requalifie le candidat concerné.

La revue du commit `aea7654` a également identifié deux dépendances de nommage
temporaires dans la borne transverse : les bords `underarm-front` /
`underarm-back` et l'identité `upper.<côté>.section.1`. Le commit `8e7a73d`
retire ces dépendances : les bords viennent de la relation unique déclarée,
et la section unique du côté demandé doit réellement appartenir au domaine
épaule–coude, au paramètre exact 0,5, avec statut mesuré. La concordance à
l'index authentifié reste vérifiée. Les 17 tests passent sous les deux Python,
avec revue indépendante ; les bornes de la même famille sont conservées
exactement après renommage. [Portée des preuves](automation-capacity-generality-evidence-20261005.json).

Le nom d'un bord ou d'une section ne justifie pas une restriction géométrique ;
la relation source, le domaine anatomique, le côté et le paramètre mesuré
portent cette vérification.

## Vérifier une correction réutilisable

Pour une modification de géométrie ou de mesure, vérifier le comportement sur
des contours ou guides distincts, des orientations différentes et des données
incompatibles. Un test qui renomme uniquement le même manteau ne démontre pas
la généralité géométrique. Conserver les contrôles de provenance, les refus,
les tolérances et les critères finaux ; optimiser le calcul ne les assouplit pas.

Un budget épuisé reste incomplet. Augmenter implicitement le temps ou supprimer
un contrôle ne constitue pas une correction générique. Les observations de
profilage doivent préciser les entrées et les phases réellement parcourues.
Une optimisation est comparée au calcul de référence sur son domaine et ne
réutilise pas un cache après changement de source, guide, corps, pose ou code.

Les exécutions Blender restent préparées par le dispatcher avec autorisation
exacte de l'utilisateur. Un diagnostic portable ou une réussite de fixture
ne remplace pas les essais natifs ni les revues humaines du vêtement.
