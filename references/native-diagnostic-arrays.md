# Stockage privé des tableaux de diagnostic natif

`NATIVE_DIAGNOSTIC_ARRAY_DTO_V1` est un codec portable **TEST_ONLY / NONE**. Il
n'est appelé par aucun chemin de production. Il ne remplace ni le DTO natif V3,
ni son consommateur, ni les contrôles de géométrie, de source ou d'admission.
Les essais natifs V2/V3 ont terminé leur construction mais n'ont pas livré de
payload complet après le refus commun de nœuds ou de profondeur. Ce module ne
localise pas rétroactivement ce refus et ne prouve pas que le payload réel tient
dans les plafonds. Aucun essai natif ni compilation réelle du col n'est requis
ou exécuté par ses tests.

Le module [native_diagnostic_arrays.py](../a3d/native_diagnostic_arrays.py) expose
deux fonctions internes : `pack_native_diagnostic_arrays` produit des bytes
JSON ASCIIescaped, encodés en UTF-8 avec un LF ; `unpack_native_diagnostic_arrays` reconstruit la donnée
native. Le résultat est complet ou une `StudioError` est levée. Il n'existe pas
de retour partiel admis, de `READY`, ni de qualification physique implicite.

## Format fermé et conservation

La racine comporte uniquement `discriminant`, `version`, `purpose`,
`qualification`, `codec_sha256`, `payload` et `receipt`. Le hash correspond aux
bytes réels du module, contrôlés de nouveau avant le retour. Le reçu compte la
racine, ses clés, le payload, les tags, son propre contenu et le LF. Son scope
`ENCODED_STORAGE_NOT_NATIVE_LEDGER` distingue ce compte du ledger natif observé
dans les essais précédents. Il ne reprend aucun de leurs compteurs.

| Donnée native | Représentation |
| --- | --- |
| Bloc homogène d'au moins huit éléments, une ou deux dimensions | `ARRAY`, shape entière exacte, dtype `BINARY64_LE` ou `INT64_LE`, types du conteneur et des lignes, données base64 canoniques |
| Map entièrement int→int, au moins quatre entrées dans INT64 | `INT_MAP_ARRAY`, shape `[N,2]`, clés explicites triées numériquement comme le DTO V3 |
| Petit bloc, valeurs mixtes, bool, int hors INT64 | Tags `LIST`, `TUPLE` ou `MAP` avec scalaires exacts ; aucune coercition vers INT64/float |
| Map à clés str | `MAP` avec ordre déclaré conservé |
| Map à clés int, fallback | `MAP` avec types des clés conservés et ordre numérique canonique V3 |
| Vector explicitement déclaré | `VECTOR` ou lignes `VECTOR` de deux ou trois float natifs finis |

Les float sont empaquetés par leurs bits binary64, dont `-0.0`, les valeurs
adjacentes, les subnormaux et les grandes valeurs finies. Les list et tuple
restent distincts. Les rapports et tableaux répétés restent présents ; il n'y
a ni fusion, ni déduplication, ni identité fondée sur la proximité. L'ordre
d'insertion original d'une map entière n'est pas une identité de transport V3 :
le codec utilise son ordre numérique canonique sans modifier le dictionnaire
source. Les maps à clés mélangées ou bool sont refusées.

Toutes les maps source sont encapsulées. Une map source qui contient `tag`,
`dtype` ou `discriminant` n'est donc pas interprétée comme un tag de transport.
Le décodeur refuse les champs inconnus, les doublons de clés JSON, les tags ou
formes incohérents, les alias de bool/float pour les dimensions, le base64
tronqué ou non canonique, les maps entières non triées ou dupliquées, et les
nombres non finis, y compris dans un bloc binary64.

`vector_type` est une précondition explicite du caller. Aucun import de
mathutils n'est effectué. Les tests utilisent un adaptateur portable et un
adaptateur simulant binary32. Après construction, les composantes du Vector
sont comparées bit à bit aux float stockés ; une perte lors de reconstruction
est refusée. Ce constructeur est fourni par le caller et doit être borné et
coopératif : le codec ne peut pas interrompre un constructeur arbitraire qui
ne retourne pas. Ces tests ne qualifient pas un Vector Blender réel.

Les entiers hors INT64 restent des int Python exacts en fallback. La limite de
conversion décimale du Python utilisé n'est pas relevée ; un entier qui dépasse
cette limite est refusé avec `INTEGER_TEXT_LIMIT`, sans conversion approchée.
Les sous-classes et types non déclarés, les cycles et les chaînes avec un
surrogate isolé sont refusés.

## Un budget fourni par le caller

Le caller crée une seule instance privée `CodecBudget(check=..., limits=...,
usage=...)`. Le callback `check(phase)` interroge son enveloppe et son horloge
existantes. Le codec n'importe pas `time`, ne crée ni origine ni délai et ne
réinitialise aucun compteur. Le callback est une observation en lecture seule ;
la mutation concurrente de données pendant leur lecture n'est pas supportée.
Les mutations détectées entre la capture et les guards de retour sont refusées.
Une erreur de stop/délai du callback se propage avec une qualification `NONE` ;
les autres exceptions de callback sont normalisées en `INVALID_CLOCK`.

| Plafond dur, resserrable seulement | Valeur | Portée |
| --- | --- | --- |
| `max_nodes` | 500 000 | Toutes les sorties du même caller, clés incluses |
| `max_bytes` | 8 MiB | Toutes les sorties du même caller, LF émis inclus |
| `max_depth` | 128 | Profondeur de la représentation encodée et de l'expansion |
| `max_work` | 100 000 000 | Débits cumulés des visites, caractères lus/hachés, cellules et tri des clés |
| `max_allocation_bytes` | 256 MiB | Réservations cumulées conservatrices des buffers, graphes et objets scalaires ; aucune restitution |

Les deux derniers plafonds sont des limites internes de travail et de
réservation, distinctes des plafonds de sortie et du ledger natif. Ils ne sont
pas une mesure de temps ni de RSS. Les réservations comprennent les lectures du
code, le plan de transport, le parser JSON, le base64, les graphes reconstruits,
les copies de sérialisation et les passages scalaires. Les objets et
allocations propres au constructeur externe restent une responsabilité
déclarée de l'adaptateur. Ces choix conservateurs peuvent refuser une donnée
avant son plafond de sortie ; ils ne garantissent pas qu'un payload réel soit
encodable. Aucun budget refusé n'est remboursé, même après stop ou échec.

Les compteurs `usage` initiaux permettent de reprendre les débits du before,
du reçu hôte ou d'une autre sortie déjà comptée. `reserve` permet de compter
l'enveloppe supplémentaire du caller avant sa création. Il faut garder cette
même instance pour toutes les pièces et artefacts. Un before ou reçu extérieur
non transmis au codec doit être explicitement réservé par ce caller ; il
n'existe pas de comptage implicite de données non reçues.

L'encodeur calcule la taille exacte de son JSON fermé avant les grands buffers
et la sérialisation, puis vérifie les bytes effectivement produits. Le reçu
interne ne copie pas les compteurs de travail/allocation susceptibles de
changer pendant les guards ; ceux-ci restent sur l'objet partagé. Les guards
relisent le code et la donnée source. Le checkpoint `codec_pack_return`
précède ces derniers guards, qui utilisent toujours le même callback/budget.

Le décodeur contrôle les champs fermés et compte **la représentation développée
équivalente au DTO V3** avant de décoder les buffers numériques. Les wrappers
tuple/Vector/maps entières, leurs clés et leurs valeurs sont inclus. L'échec de
ce quota survient avant l'allocation base64/numérique. Le coût en bytes développé
est calculé exactement après lecture des scalaires, avant construction du
résultat natif. Ce coût est une quota de stockage pour l'expansion explicite ;
aucun second fichier n'est émis gratuitement. Si le caller écrit ensuite un
artefact avec d'autres enveloppes ou un LF, il doit compter leurs bytes réels
dans la même instance. Encoder puis développer avec le même budget cumule les
deux sorties, sans crédit pour le JSON d'entrée lu.

Les opérations de bibliothèque non interruptibles — parser JSON, base64,
sérialisation et tri — ont des tailles réservées avant leur appel et des
contrôles aux frontières. Les grandes boucles de visite et de lecture contrôlent
le callback pendant leur progression. La garantie de temps est coopérative ;
ce module n'ajoute aucun watchdog ni promesse de deadline dure.

La revue V1 a démontré une réserve insuffisante pour la sérialisation Unicode :
un emoji après 100 000 caractères ASCII peut élargir toute la chaîne Python à
quatre octets par caractère. Le gel V1 et son FAIL restent historiques. Le
correctif V2 réserve `9 * taille_UTF8_exacte + 256` avant la sérialisation : deux
chaînes Python à quatre octets par caractère, les bytes UTF-8 et leurs en-têtes.
Chaque nombre de caractères est borné par cette taille UTF-8 déjà calculée.
Cette réserve remplace `3 * taille + 128` ; aucun plafond n'est relevé, et le
témoin à l'ancien cap refuse désormais avant d'allouer ces buffers. Le
conservatisme supplémentaire peut provoquer un refus plus tôt ; ce n'est pas
une preuve que le payload natif réel pourra être stocké.

Le correctif V3 change uniquement la représentation JSON privée encodée et
son compte exact. `ensure_ascii=True` conserve la valeur Unicode après parse,
avec six caractères ASCII pour un codepoint BMP et douze pour un codepoint
astral. Quotes, backslash et caractères de contrôle gardent les échappements
JSON exacts. Les surrogates présents comme code units restent refusés, y
compris une paire de code units ; aucune normalisation n'est ajoutée.
Le caractère DEL U+007F est aussi échappé sur six caractères, comme l'impose
le sérialiseur ASCII Python ; il ne suit pas le compte UTF-8 natif d'un octet.
`_stats` compte les clés et chaînes de ce DTO encodé dans cette convention.
La taille inclut le LF effectivement émis et le reçu complet stabilisé.

La réserve des trois buffers de sérialisation est maintenant
`3 * taille_ASCII_exacte + 256`, débitée avant `json.dumps` : deux chaînes Python
ASCII d'un octet par caractère, puis les bytes et leurs en-têtes. Les autres
réserves de matérialisation, parsing, lecture de code et hash final persistent.
Un refus conserve les débits sans remboursement. La nouvelle représentation
augmente les bytes du Unicode dense et peut atteindre les 8 MiB plus tôt.
Elle évite l'élargissement de toute la chaîne Python par un seul emoji ; cela
ne garantit ni un gain de temps ni la réussite de stockage du payload réel.

Les fonctions `_utf8_size`, `_scalar_size`, le hash natif et `_expanded_stats`
conservent leur convention UTF-8 et leurs comptes de l'expansion équivalente
au DTO natif V3. Aucun conteneur, ordre de map, rapport, ID ou bit IEEE n'est
supprimé ou modifié. Le nouveau code a une identité propre : les anciens
packets et preuves restent liés à leur codec exact. Une future préparation
expérimentale devra lier cette nouvelle identité et sa revue ; aucun caller
historique n'est modifié par ce module.

L'essai encodé réel avec le codec V2 a refusé l'allocation sans sauvegarder de
payload complet. Son calcul et la géométrie des pièces restent inconnus ou
non attestés. La réserve JSON est une piste analytique parmi les réserves de
matérialisation et de guards ; le diagnostic ne démontre pas une cause unique.
La V3 reste un candidat portable à revoir, sans nouvel essai natif exécuté.

Les refus de quota distinguent `NODES`, `DEPTH`, `BYTES`, `WORK` et `ALLOCATION`.
Le diagnostic fournit un chemin limité à douze composants de 48 caractères,
un indicateur de troncature et, lorsque pertinent, la profondeur et les débits
utilisés/demandés/plafond. Il ne capture pas le gros payload au refus.

## Vérification et limites

[test_native_diagnostic_arrays.py](../tests/test_native_diagnostic_arrays.py)
compare les types, bits, clés et comptes exacts à un petit oracle de stockage
V3 écrit séparément. Il couvre aussi les plafonds exacts et cap−1, l'usage
initial et deux sorties, les formes hostiles, les refus avant expansion, les
callbacks de stop/délai, les mutations aux frontières et l'identité du code.
La portée de ces tests est le codec portable ; le DTO/API historiques restent
inchangés et aucun caller n'est intégré.

Une baisse analytique des nœuds d'une matrice n'est pas un gain mesuré du
runtime. Les petites valeurs int peuvent coûter plus de bytes en base64 que
leur texte JSON. La préparation et la revue indépendante de ce module devront
précéder toute proposition d'usage natif. Une future intégration devra inclure
son identité réelle dans les dépendances du caller, sans transférer les PASS
portables à l'observation native, aux patrons, au Cloth, au fitting ou au
vêtement complet.
