# Volume du cou et guides de col

Un tour anatomique, une longueur de couture et la hauteur matérielle du patron
ne décrivent pas toute la surface autour de laquelle le col doit être placé.
Conserver le corps accepté, les patrons et les décisions d’aisance ; compléter
les correspondances géométriques sans transformer une observation de contact en
nouvelle cible de taille.

## Limite actuelle vérifiée

Le guide `SOURCE_DEVELOPABLE_NECK_BAND` utilise une section transversale du
profil corporel. Cette section fournit centre, altitude et rapport largeur /
profondeur ; la largeur du patron fournit le périmètre auxiliaire. Deux rangées
reprennent cette même courbe aux extrémités de la hauteur du patron. Le guide
initial ne consomme pas la forme du chemin 3D approuvé à la base du cou, ni les
variations de la peau sur toute la hauteur du col.

Le placement rigide du col conserve les métriques. Le couplage des raccords
calcule ensuite des moyennes de positions entre partenaires : ces positions
communes peuvent étirer ou comprimer les éléments du guide. Les contrôles après
couplage restent nécessaires ; une couture coïncidente ne prouve pas un volume
correct ni une matière conservée.

Dans l’essai natif 0704, le patron de col accepté mesure 55,2154 × 7 cm. Une
paire à la même abscisse matérielle, V = 0 et V = 7, se retrouve séparée de
8,5531 cm dans le guide raccordé. Ce témoin prouve une déformation du placement.
La boîte englobante verticale de 13,7996 cm ne mesure pas la hauteur matérielle :
elle inclut les variations d’altitude et l’inclinaison du montage.

## Compléter les données avant admission

- Rattacher le chemin inférieur approuvé à la géométrie et à la pose exactes,
  avec sa phase devant / dos et ses correspondances aux segments de couture.
- Mesurer largeur, profondeur, centre et statut des contours de peau dans la
  zone traversée par le guide. `measured_native_skin_sections` produit ces
  contours depuis les artefacts natifs authentifiés, sans remplacer les tours
  anatomiques approuvés.
- Préparer une proposition visuelle de correspondance supérieure et de
  rangées intermédiaires, en conservant la hauteur source. Une mesure absente
  ou un contour incomplet reste non qualifié ; ne pas extrapoler une section
  pour faire disparaître un défaut. Présenter les nouvelles correspondances
  anatomiques avant leur adoption, sans faire réapprouver des patrons inchangés.
- Traiter col et encolure conjointement avec des limites de déplacement et de
  métrique explicites. Contrôler les valeurs avant raccord, après raccord et
  après la propagation dans les pièces. Une moyenne de positions ne remplace
  pas ces contraintes.
- Vérifier les triangles du candidat exact contre les surfaces corporelles,
  puis les étapes physiques et le fitting. Quelques sections horizontales ne
  constituent pas une preuve de réserve sur tout le volume.

Les outils publics de sections régionales ont actuellement un domaine de bras.
Des sections inclinées du cou demandent une extension explicite de ce contrat ;
ne pas employer des identifiants de bras pour contourner ce domaine.

## État et preuves

Le diagnostic séparé sur le corps accepté contient quinze sections dans la zone
du guide actuel : treize mesurables, deux incomplètes. Il porte uniquement sur
les obstacles géométriques. Le guide complet du cou, le placement et le fitting
restent non admis. Aucune nouvelle coupe ni modification du corps n’est produite.

[Mesures du guide et des contours](automation-collar-volume-diagnostic-evidence-20261007.json)
et [essai natif, candidat et restauration](automation-native-mesh-300-evidence-20261007.json).
