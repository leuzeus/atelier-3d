# Stockage UV natif et mesure des patrons

Le writer Blender restaure les ancres exactes du sampler source avant
d'enregistrer `rest_cm`. Le lecteur historique attendait exclusivement une
conversion en binary32. Le candidat actuel contient pourtant 2 236 ancres
exactement conformes au sampler en double précision. Le refus numérique du
lecteur ne démontrait aucune erreur de géométrie du patron.

Le lecteur rejoue les frontières canoniques et compare les sources, la recette,
les paramètres réguliers, les inventaires, les appartenances, l'ordre des
frontières et des coutures et leurs clés. Deux modes homogènes sont reconnus :
`SOURCE_DOUBLE` exact et le stockage historique `BINARY32` exact. Aucune
tolérance, projection ou recherche par proximité n'est ajoutée. Les sommets
source et le dernier passage du sampler à une clé partagée restent authentifiés.

Le contexte de rejeu est interne : le wrapper le reconstruit depuis les
références authentifiées du reçu natif. Un marqueur fourni par un client ne
constitue pas une preuve. Le profil de maillage synchronisé n'est pas encore
supporté par ce rejeu et reste refusé explicitement.

La compilation source V3 sous Python 3.11 produit quatre propositions de
correspondance : hauts de bras 45,204894/45,240336 cm et poignets 25/25 cm.
Les mesures corporelles associées sont 37,439902/37,476989 cm et
17,395739/17,441566 cm. L'homologie reste à examiner ; aucune proposition
n'est admissible pour fitting. Les trois chemins du torse épuisent le budget
actuel de 15 secondes de l'intersection de guide. Le col reste sans ligne
entière correspondant au plan du cou. Aucune circonférence fermée du torse
ni capacité complète des patrons n'est démontrée.

Sous Python 3.13, le même appel public refuse plus tôt le supplément corporel,
qui diffère de sa remesure canonique. Ce problème distinct reste localisé et
ne devient pas un PASS inter-runtimes de la compilation produit.

Les 45 tests ciblés passent sur les deux Python. Les entrées du diagnostic
produit restent inchangées. Aucun writer, patron, corps, runtime installé ni
état d'acceptation n'est modifié par ce correctif.
[Preuves exactes et limites](automation-source-uv-storage-evidence-20261005.json).
