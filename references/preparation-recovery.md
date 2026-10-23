# Reprendre après un refus de préparation

Un refus du plugin ne prouve pas que la conception approuvée est incorrecte.
Avant de proposer une suite, confronter le diagnostic, les patrons et raccords
source, la planche approuvée et les capacités de la version réellement utilisée.
Appliquer ce protocole après un refus de préparation, d'essai local ou de
complétude ; le statut technique et ses preuves restent inchangés jusqu'au
nouveau contrôle.

## Distinguer la cause et annoncer la suite

| Cause établie | Information à donner à l'utilisateur | Suite à préparer |
| --- | --- | --- |
| Limite du logiciel ou de l'essai, alors que la technique approuvée est cohérente | Nommer l'opération refusée, la règle incompatible et ce que la technique approuvée demande. Dire explicitement que ce refus ne démontre pas un défaut de conception. | Présenter deux choix concrets : conserver la technique approuvée avec un parcours compatible ou une correction de capacité à qualifier ; revenir au contrat actuellement supporté avec les adaptations nécessaires. Attendre le choix avant de changer de technique ou de contrat. |
| Erreur confirmée dans les données préparées | Nommer les pièces, bords et raccords concernés, le défaut mesuré et la source qui permet de le corriger. | Proposer une correction ciblée de la recette, du mapping ou du maillage dérivé, ou refaire la préparation des seuls patrons concernés. Conserver le découpage approuvé. |
| Pièces ou patrons manquants | Donner leurs identités exactes et distinguer absence de source, absence de dérivation et absence dans Blender. | Proposer de produire ou refaire les seuls éléments manquants à partir des sources approuvées, puis les intégrer et recontrôler la complétude. |
| Cause encore indéterminée | Décrire le refus et les observations disponibles sans attribuer la faute au patron. | Préparer une inspection ciblée ou un petit cas reproductible. Demander seulement l'information de conception qui manque réellement. |

Ne pas s'arrêter au message « contrat du plugin » ou au statut
`NEEDS_CORRECTION`. Fournir une proposition réalisable avec la portée des
changements, les sources utilisées et les vérifications attendues. Une capacité
absente doit être annoncée comme telle : ne pas promettre une exécution immédiate
si elle exige d'abord une évolution du plugin.

## Limite technique : choix utilisateur

Pour une ceinture approuvée comme une bande unique se fermant sur elle-même,
un essai qui exige deux panneaux distincts et une couture permanente ne teste
pas cette construction. Expliquer cette incompatibilité, puis présenter :

1. **Conserver la technique approuvée.** Préparer un essai adapté au panneau
   unique et à sa fermeture source, si la version courante le supporte ; sinon
   proposer l'évolution nécessaire et sa qualification avant de l'utiliser.
2. **Revenir au contrat supporté.** Montrer concrètement les adaptations que
   l'essai exige et leurs effets sur le découpage, la fermeture et le résultat.
   Faire choisir cette voie avant toute modification de conception.

La décision de poursuivre ne transforme pas une fermeture `closure` en couture
`permanent`, ne crée pas de panneau fictif et ne désactive pas un contrôle.
Une modification du découpage ou de l'intention de raccord produit une variante
et une revue des différences avant production. Une réparation du logiciel qui
conserve ces intentions exige de nouvelles preuves techniques, sans faire
réapprouver un découpage inchangé.

## Erreur de préparation : correction ou reprise ciblée

Pour la capuche et les épaules, vérifier les IDs, partenaires, intervalles de
bord, sens et types de chaque raccord avant de modifier les données. Un même
secteur utilisé par une couture permanente et une attache détachable n'est pas,
à lui seul, la preuve d'une erreur : confronter ce montage à l'intention
approuvée et au support du logiciel. Si le refus vient du support, appliquer
le choix utilisateur ci-dessus. Si deux affectations réellement incompatibles
sont établies, montrer les raccords concernés et proposer la réparation.

Préparer une variante traçable avec une liste explicite des éléments concernés.
Réutiliser les contours, IDs, crans, longueurs et intentions approuvés pour
corriger les partenaires, l'orientation, l'échantillonnage ou le placement.
Quand un dérivé est absent ou inutilisable, refaire sa préparation depuis le
patron source ; conserver les autres pièces et leurs preuves encore valides.
Ne pas supprimer un raccord approuvé pour faire passer un contrôle.

Pour les pièces manquantes, distinguer trois reprises :

- Patron source présent : produire son maillage dérivé ou son package manquant,
  avec les correspondances et preuves liées à cette source.
- Dérivé déjà produit mais absent de Blender : proposer son intégration native
  et vérifier son identité ; ne pas régénérer une pièce déjà acceptée.
- Patron source absent : préparer une proposition depuis les références
  originales, signaler les données ou intentions indéterminées et faire revoir
  les différences de conception avant de produire le dérivé. Ne pas inventer
  silencieusement des contours ou des crans.

Après correction, recontrôler les raccords concernés et la couverture
locale/globale, puis refaire les étapes dont les preuves ont été invalidées.
Présenter le résultat et les vues avant toute conclusion de fitting ou
d'acceptation artistique. Une pièce présente mais non qualifiée ne donne aucun
PASS Cloth.

## Autorisations et compte rendu

Préparer les options et les fichiers techniques dans le périmètre déjà autorisé.
Une correction technique conservant la conception peut suivre l'autorisation
de travail existante ; elle ne réclame pas une nouvelle validation du board.
Le choix entre technique approuvée et contrat supporté reste une décision de
l'utilisateur, jamais une décision implicite tirée de son silence.

Avant toute exécution via `execute_blender_code` ou sa variante CLI, présenter
l'opération exacte et attendre l'autorisation selon
[le protocole Blender](blender.md). Le choix d'une technique ne remplace pas
cette autorisation. Respecter checkpoints, admissions et restauration native.

Le compte rendu doit indiquer : cause établie ou incertaine ; pièces/raccords
touchés ; options ou correction proposée ; effets sur la conception ; prochaine
vérification ; décision ou autorisation encore nécessaire. Ne pas déclarer
« corrigé » sur la seule rédaction d'une proposition ou d'un fichier source.
