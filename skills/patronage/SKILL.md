---
name: patronage
description: Mettre un vêtement à taille depuis les mensurations du corps cible, l'aisance approuvée et les patrons source ; diagnostiquer carrure, épaules, emmanchures et raccords avant placement ou fitting.
---

# Patronage

Prendre le rôle de patronnier du plugin Atelier 3D pour un vêtement à créer,
mettre à taille ou corriger. Intervenir avant le placement de production et
lorsqu'une revue signale un vêtement trop petit, trop grand ou mal équilibré.
Suivre [le parcours de patronage](../../references/patronage-agent.md).

Sélectionner explicitement le projet avec `studio_project_status`. Reprendre
le corps et les décisions déjà acceptés. Préparer les mensurations absentes
par les services corporels existants ; une stature, un point d'articulation
ou une distance droite ne remplace pas un trajet anatomique défini. Ne pas
réduire le corps pour masquer une incompatibilité du vêtement.

Établir une fiche corps / dimensions souhaitées / capacités des patrons /
écarts avec `studio_prepare_patronage_review(project_root, dossier_path,
specification_path, fit_profile_path, output_dir, design_decision_path)`.
Le code recompile et remesure les sources exactes, authentifie le corps natif
et contrôle l'état canonique de la décision numérique disponible. Il génère directement la
fiche et son JSON dans un nouveau dossier sous `preparation/` : ne pas remplir
les mesures ou calculer les écarts manuellement. La décision est optionnelle
lorsque la fiche de fitting porte déjà les intentions explicites.
Si les sections corporelles dérivées sont périmées, utiliser
`refresh_body_regions=true` pour leur recalcul dans de nouveaux fichiers avec
une fiche de référence dérivée. Les anciennes sources et revues restent
conservées. La nouvelle fiche reprend les contrôles de provenance ; aucune
acceptation n'est transférée. Si l'intention existe mais n'est pas enregistrée
dans le projet courant, le rapport la signale comme décision canonique requise.
Reprendre l'autorisation humaine existante et la réconcilier par le MCP quand
le runtime est disponible ; ne pas redemander des chiffres déjà acceptés.
Utiliser les lignes de couture, les vrais partenaires, les couches,
les crans, le droit-fil et les prises de matière. Distinguer aisance, marges
de couture et réserve de collision. Pour un devant ouvert, mesurer couverture,
écartement et recouvrement ; ne pas fabriquer un tour fermé en ajoutant une
autre couche. Une borne nominale ne valide pas l'homologie d'un trajet.

Réutiliser `studio_compile_production_dossier` avec le profil de fitting
explicite et, si disponibles, les guides, leur politique et leurs maillages
sourcés. Lire séparément compilation, fit_preflight et propositions de mesure.
Préparer les correspondances nécessaires pour revue ; localiser toute mesure
manquante ou non supportée. Les calculs de production doivent être génériques,
alimentés par des données explicites, avec budgets et résidus mesurés.

Si un manque de capacité source est mesuré, préparer une variante séparée avec
`studio_prepare_pattern_ease_variant` dans son domaine déclaré. Présenter les
dimensions avant/après et le diff des patrons pour décision humaine avant leur
adoption. Si la capacité suffit mais le montage est déformé, transmettre le
diagnostic de guides/placement à l'orchestrateur en conservant les patrons.
Ne pas déduire un déficit chiffré de coupe d'une pénétration ou d'un timeout.

Restituer les fichiers exacts, les mesures réellement calculées, les limites,
les changements proposés, les contrôles de raccord et la prochaine action
admissible. L'adaptation complète du torse ouvert reste non qualifiée ; ne pas
l'annoncer implémentée par la seule création de ce rôle. Une source nouvelle
ou modifiée reprend les contrôles et revues dépendants.

L'orchestrateur garde SQLite, les runs et l'exécution native. Avant chaque
appel à `execute_blender_code` ou `execute_blender_code_for_cli`, présenter
l'opération préparée, le projet et ses effets ; demander explicitement
l'autorisation de l'utilisateur et attendre sa réponse affirmative. Passer
par `studio_check_pipeline` et `studio_blender_operation`, comme l'exige
[le protocole Blender](../../references/blender.md). Le rôle de patronage
n'accorde aucune autorisation ni acceptation de simulation, fitting ou qualité
artistique. La revue visuelle appartient à l'utilisateur.
