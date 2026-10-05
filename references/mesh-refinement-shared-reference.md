# Référence permanente du conditionnement intérieur

`a3d.mesh_refinement.improve_interior` accepte l'argument facultatif
`displacement_reference=None`. Lorsqu'il est absent ou vaut `None`, les points,
l'algorithme et les champs du reçu historique restent exactement inchangés.

Une référence explicite est une liste ou un tuple contenant autant de points
2D que les coordonnées d'entrée. Chaque coordonnée est un `int` ou un `float`
Python natif fini ; booléens et sous-types numériques sont refusés. La fonction
copie la référence en tuples immuables avant toute mesure ou optimisation.
Une entrée déjà au-delà de `max_displacement` depuis cette référence est refusée.

Chaque proposition est mesurée depuis la référence permanente, avec la borne
stricte `math.dist(reference[i], trial) <= max_displacement`. La fonction
n'ajoute ni epsilon, ni projection, ni nouveau plafond. Le retour est contrôlé
de nouveau après les mesures et la construction du reçu. Les critères
angulaires et leurs tolérances historiques restent inchangés.

Les indices explicitement fixes et tous les bords topologiques restent ancrés
sur les coordonnées **d'entrée de cet appel**. La référence de déplacement ne
remplace pas ce contrat d'ancrage et ne crée aucun pin physique. Elle peut
différer d'un ancrage d'entrée dans la limite de déplacement déclarée.

Le champ historique `maximum_displacement_cm` reste le déplacement depuis
l'entrée. Avec une référence explicite seulement, le reçu ajoute
`displacement_reference` : politique `EXPLICIT_PERMANENT`, empreinte complète
des coordonnées de référence, nombre de points, déplacement maximum déjà
consommé à l'entrée, déplacement cumulé maximum au retour, budget et contrat
d'ancrage depuis l'entrée. Le reçu ne contient aucun alias mutable de la
référence fournie.

Le témoin portable en deux étapes montre pourquoi cette option est nécessaire.
Après un premier mouvement de 0,494975 cm, un second appel à référence locale
peut atteindre 0,813173 cm depuis la naissance. Avec la référence permanente
et un budget de 0,5 cm, les propositions supplémentaires sont refusées et
l'objectif angulaire reste explicitement non atteint.

Cette capacité n'est pas encore raccordée au caller Blender. Aucun pilote
natif, schéma, gate, seuil ou package n'est changé. Les témoins portables ne
qualifient ni la triangulation native, ni les contacts, Cloth, fitting,
anatomie ou acceptation artistique du vêtement. L'intégration nécessitera
son propre précontrôle et ses preuves sur le candidat exact.
