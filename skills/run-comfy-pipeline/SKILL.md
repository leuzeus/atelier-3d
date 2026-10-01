---
name: run-comfy-pipeline
description: Exécuter les étapes ComfyUI d'un projet Atelier 3D via le MCP officiel local, avec jobs courts et provenance.
---

# run-comfy-pipeline

Lire [l'intégration officielle](../../references/comfy-official.md). Appeler studio_doctor, puis uploader les clean PNG exacts du package. Passer les input_name reçus aux paramètres du workflow. comfy_validate_workflow exige project_root et doit être compatible. comfy_submit_workflow utilise une request_key stable, attend seulement la soumission et renvoie job_id puis prompt_id. Poller avec comfy_job_status ; récupérer avec comfy_job_outputs(download=true). Une soumission inconnue ne doit jamais être répétée avec une nouvelle clé. Un job completed ne valide ni géométrie ni qualité visuelle. Les modèles payants, téléchargements, mises à jour et lancement/arrêt de ComfyUI ne sont pas autorisés par cette procédure.

Les références générées doivent consommer une image originale enregistrée et uploadée purpose=source ; conserver source_images dans la provenance. Une reconstruction acceptée ne doit pas être relancée. Un statut tardif de job échoué ne révoque pas une pièce déjà acceptée sur ses preuves.
