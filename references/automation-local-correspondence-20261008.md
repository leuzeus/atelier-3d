# Correspondances locales : axes et surface

## Axe d'un segment corporel déclaré

Le diagnostic des manchettes distingue l'axe épaule–poignet de l'axe
coude–poignet : environ 9,3° dans le cas réel. Une rotation rigide autour du
poignet déplace les centres proximaux d'environ 3,24 cm sans changer la métrique
du tissu. Le témoin de pénétration plane à V20 diminue d'environ 3,90 cm à
1,36 cm. Ce contrôle de sections ne qualifie pas les contacts des faces complètes.

Le mode produit `LIMB_SEGMENT_AXIS_V1` permet de choisir un segment depuis deux
repères du profil exact. Il est distinct d'une attache sur la peau. La politique
de pièce figure dans les références anatomiques de la politique publique de guides :

```json
{
  "guide_kind": "LIMB_SEGMENT_AXIS_V1",
  "anatomical_region": "lower_arm.left",
  "axis_landmarks": ["elbow.left", "wrist.left"],
  "transverse_direction_body": [0, 1, 0],
  "source_end_edges": {"proximal": "proximal", "distal": "distal"},
  "source_anchor_end": "distal"
}
```

Les noms de bords et de repères doivent exister dans les entrées. Le premier
repère est proximal, le second distal. Les deux bords source sont distincts,
à V constant et aux extrémités du domaine matériel. Le signe de V est dérivé
de ces bords. L'extrémité choisie conserve son repère axial ; l'autre avance
de la longueur source en centimètres. Si elle n'atteint pas le second repère,
le résidu est mesuré, sans mise à l'échelle. La direction transverse est
projetée dans le plan normal à l'axe ; les cas parallèles ou dégénérés sont refusés.

Cette primitive accepte aussi un rôle `panel`, des noms arbitraires et un
repère corporel tourné. Le côté, la région et les repères doivent être cohérents.
Les régions hors catalogue exigent un nom `custom:` explicite. Elle réutilise
la couture unaire source compatible et peut être combinée avec
`SOURCE_SEWN_DOMAIN_V1`. Elle ne fournit pas une initialisation universelle des
pièces ayant d'autres topologies ou des extrémités obliques. Aucune contrainte
cutanée fixe n'est ajoutée ; une pièce ayant déjà une attache cutanée garde
`LIMB_ATTACHMENT_V1`. Le comportement historique est inchangé sans sélection
du nouveau mode.

Les identités du corps, du patron, de la politique et du noyau sont conservées
dans le reçu. Le noyau appartient à la fermeture de code de la politique
publique ; sa modification invalide cette politique. Le contrôle géométrique
reste une hypothèse de préparation, sans admission de fitting.

## Limites observées sur les membres

La rotation ne suffit pas. À V10, une section de manchette offre 27 cm de
largeur source contre environ 24,37 cm de périmètre convexe corporel, mais le
cercle centré sur l'axe traverse encore le corps. C'est une limite de forme
ou de centrage sous cette correspondance, pas une preuve de manque de tissu.
À V15/V20, des bornes de longueur plus grandes que la source sont observées,
mais dépendent de la correspondance longitudinale, de la pose et de la couche.
Elles ne déclenchent aucune modification de patron.

La carte analytique du tube de manche reste elle-même déformante : extrema
environ 0,605–1,760 dans la bande terminale. Le raffinement réduit l'erreur
d'interpolation mais ne supprime pas ce cisaillement. Ce résultat n'établit
pas l'impossibilité d'une configuration avec plis.

Un essai unique combine les quatre nouvelles cages de membres et les six
autres guides, sur le commit 376c598. Il est refusé au budget de 120 secondes,
après quatre itérations rigides et quatre matière sur huit. Son meilleur
état interne conserve les quinze attaches et réduit l'écart maximal de
raccord de 20,5537 à 16,8181 cm ; la matière reste refusée. Les quatre planches
avant/après, dont les gros plans, ont été affichées. Il ne s'agit pas d'un
résultat runtime achevé. Reçus : `program-sewn-domain-coupling-replay-v1/`.

## Continuation locale du col

Un POC distinct suit un chemin projeté explicite depuis les incidences natives
vérifiées du trajet du cou, dans la région 1 déjà déclarée. Les dix tests
synthétiques couvrent nappes proches, plis, frontières, ambiguïtés et
subdivisions coplanaires. Les quatre témoins réels sont atteints en 1,547 s,
sans déplacer leurs cibles ni l'attache fixe. Les coordonnées interrogées
sont les cibles homologues col–torse proposées, pas les guides initiaux.

Le succès porte sur ces chemins locaux. Il ne constitue pas une carte de
l'intérieur des panneaux. Les 27 segments d'encolure sous la réserve de
0,3 cm restent à traiter. Le POC n'est pas intégré au produit ; son raccord
doit lier les graines, coutures, UV et cibles exactes aux entrées publiques,
et conserver les refus si un domaine ou une continuation manque.
Artefacts : `program-seeded-surface-continuation-poc-v1/`.

## Reprise et revues

Les sources, le corps et l'état canonique sont conservés. Aucun Blender,
Cloth, fitting ou changement d'installation n'a été exécuté dans ces essais.
Aucune nouvelle variante de coupe n'attend une validation humaine. La revue
artistique du vêtement complet demeure à réaliser, après les correspondances,
les contacts et les essais physiques réellement admis.
