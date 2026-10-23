# Enveloppe commune du maillage synchronisé

`MeshingEnvelope` est une interface interne détenue par le caller. Elle ne crée
ni opération native, ni permission, ni admission. Son origine et son échéance
absolue appartiennent au même processus local. Le caller l'ouvre avant capture
et la conserve entre préparation et triangulation ; aucune nouvelle origine
n'est créée dans les services consommateurs.

Les limites sont explicites : `reserve(kind, amount, owner=piece_id)` débite
le travail avant sa consommation. Chaque compteur respecte sa limite globale
et, lorsqu'elle est fournie, une limite supplémentaire par pièce. Aucun retour
au meilleur candidat ne restaure les compteurs. Un arrêt ou une expiration
après réservation conserve le débit. Les réservations refusées avant travail
n'inventent pas une allocation.

`observe_material_controls(component_id, keys_by_piece)` compte l'union des
identités matérielles nouvelles depuis le baseline déclaré. Elles partagent
le compteur global `attempted_insertions` avec les nouvelles insertions
intérieures. Un replay identique n'ajoute pas une deuxième identité ; les
appels, slots et autres coûts de ce replay restent débités séparément.
Le mapping `material_controls` est en lecture seule. Un snapshot ne permet
pas de rembourser le travail courant.

Les identités sont des données JSON finies et conservées exactement. Les clés
des objets sont obligatoirement textuelles ; les tuples, types natifs non JSON,
cycles et chaînes UTF-8 invalides sont refusés avant débit. Chaque identité est
limitée à 64 niveaux, 4 096 nœuds et 4 096 octets après encodage. Aucun
arrondi de paramètre, recherche par proximité ou pin n'est effectué ici.
Le consommateur reste responsable de leur lien au source approuvé. Cette
union de contrôles ne constitue pas une preuve de leur présence physique.

`native_point_slots` et `sampling_point_slots` sont des coûts cumulés de
travail. Ils ne remplacent pas la limite de sommets présents **au composant**,
que le caller doit vérifier séparément. Les statistiques par pièce ne
multiplient pas le plafond global d'insertions. Les appels CDT et remesh peuvent
avoir des bornes locales supplémentaires ; le caller déclare leurs bornes
totales à partir de l'inventaire complet.

`check(phase)` vérifie une horloge finie monotone, la limite stricte et l'arrêt
contrôlé. `snapshot()` conserve les portées, limites et débits, avec
`qualification=NONE` et `admission=NONE`. Il refuse après expiration : ce reçu
ne transforme pas un calcul incomplet en réussite. Un bilan d'échec doit
conserver les diagnostics sans leur attribuer une qualification.
Une horloge absente, non finie, non représentable ou dont le callback échoue
produit un refus structuré `INVALID_CLOCK`. Un callback d'arrêt défaillant
produit `INVALID_ENVELOPE`. Ces refus ne remboursent pas une réservation déjà
débitée.

Le lisseur `improve_interior` accepte désormais un callback optionnel `check`.
Les appels sans callback gardent les mêmes résultats géométriques et reçus.
Les appels coopératifs contrôlent la capture, la topologie, les faces mesurées,
les passes, sommets, cibles, essais et le retour après le dernier rapport.
Une exception d'arrêt est propagée sans modifier les tableaux du caller.

Cette unité ne fournit pas encore le profil d'activation ni le raccord aux
callers de production. Ceux-ci doivent lier le candidat, la recette, le code
et les preuves, conserver les anciens chemins et exécuter les gates existantes.
