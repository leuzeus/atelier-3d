# Variantes et soumissions ComfyUI

`studio_prepare_workflow_variant` crée une variante de paramètres d'un template
enregistré. Le graphe, la définition du template, les paramètres, leur diff et
le rapport du validateur officiel sont conservés dans le projet. L'identité de
variante est immuable ; modifier un paramètre demande une nouvelle variante.

Les outils de soumission existants acceptent cet identifiant dans le même
projet. Les admissions de source, de package et de revue restent applicables.
Une compatibilité de graphe ne vaut pas acceptation de l'asset produit.

`studio_reconcile_comfy_job` récupère une soumission incertaine sans nouvel
envoi. La liste officielle des jobs doit contenir exactement un candidat lié
au chemin unique du graphe préparé ou à son empreinte. Le statut officiel doit
corroborer l'identité, le chemin et une date de soumission compatible. Le graphe
local doit rester identique. Les réponses fournisseur sont enregistrées avec
leur empreinte. Une preuve absente, ambiguë ou contradictoire ne rattache aucun
job. Les versions du fournisseur qui ne donnent pas ces informations exigent
un diagnostic supplémentaire ; elles ne provoquent jamais un réenvoi.

La validation officielle garde ses limites de couverture des entrées et de la
mémoire GPU. Le serveur et les modèles disponibles doivent être vérifiés avant
une exécution réelle. Les tests avec fournisseur simulé qualifient la gestion
des reçus et des erreurs, pas un cycle ComfyUI de production.
