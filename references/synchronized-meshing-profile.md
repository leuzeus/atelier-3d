# Profil de maillage synchronisé

La préparation accepte un profil optionnel `meshing_profile`, version 1,
mode `SYNCHRONIZED_GRADED_V1`. Il active ensemble la gradation des bords source
et le noyau natif à références de naissance permanentes. Son absence conserve
le chemin historique et ses reçus. Le profil est contenu dans la spécification
de préparation déjà liée à l'opération autorisée ; changer ses arguments ou
son fichier prépare une nouvelle opération et invalide les preuves dépendantes.

Le profil déclare l'inventaire entier `piece_ids` et tous ses budgets : temps,
capture, sortie, travail, appels et slots de sampling, demandes de fractions.
Une pièce absente ou supplémentaire est refusée avant maillage. Le budget
d'insertions vient de la recette et s'applique au composant : contrôles de bord
et insertions intérieures le partagent. Les appels CDT et remesh ont des bornes
par pièce issues de la recette et des totaux calculés sur l'inventaire déclaré.
Une enveloppe fournie doit conserver exactement ces limites ; elle n'est pas
recréée entre pièces ni après rollback.
`a3d.meshing_profile.prepare_profile(data, recipe, regular_mesh, budgets)`
construit ce profil par code depuis l'inventaire source complet et les budgets
explicites. Réorganiser les pièces d'entrée conserve le profil. La fonction
prépare des données ; elle n'exécute pas l'opération native.

Le domaine de ce profil est explicite : au plus 128 pièces, 30 000 sommets au
composant, pas fin entre 0,2 et 1 cm, au plus huit passes et 4 000 insertions
déclarées dans `quality_refinement`. Les paramètres hors domaine sont refusés.
Ils ne sont pas tronqués. La limite de temps est au plus 90 secondes. Les
limites de capture/sortie sont au plus 500 000 nœuds et 8 Mio chacune. Les slots
de travail cumulés ne deviennent pas une limite de sommets présents par pièce.

Le caller natif conserve l'origine locale mesurée avant la capture des sources.
L'enveloppe couvre la capture et la construction du maillage jusqu'au contrôle
terminal du payload. Elle ne décrit pas le temps total du MCP, du rendu ou des
phases physiques ultérieures. Aucune échéance absolue n'est transportée entre
processus. Les contrôles coopératifs encadrent les anciennes allocations qui
ne peuvent être interrompues à l'intérieur ; une expiration après leur retour
refuse le résultat.

La gradation est suivie des contrôles existants de coins source et du rebinding
des crans. Le maillage intérieur conserve une référence permanente pour chaque
point né, y compris après remesh. Avant chaque pièce, le caller réserve la
place nécessaire aux bords des pièces restantes et réduit l'allocation locale
au budget disponible du composant. Les meilleurs candidats conservent tous
leurs tableaux ; les coûts déjà tentés restent débités.

Le payload contient l'empreinte du profil, l'inventaire source et le relevé de
l'enveloppe. Le reçu de préparation distingue une construction de maillage
terminée d'un calcul refusé ou incomplet. En cas d'échec, les coûts conservés
ne sont pas un snapshot attestant une réussite. Le maillage, la métrique, les
contacts, la couverture et les critères existants décident encore de `READY`.
Le profil ne donne aucune acceptation de Cloth, de fitting ou artistique.

Les spécifications existantes, le mannequin accepté, les patrons, les raccords,
les seuils d'admission et les permissions Blender restent liés à leurs propres
contrats. L'activation doit être choisie dans une nouvelle spécification liée
au candidat à contrôler ; elle ne réutilise pas les anciens PASS natifs.
