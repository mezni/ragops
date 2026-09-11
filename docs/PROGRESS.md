Step Tracker — RAG Indexing Pipeline

Un tableau par étape. Copier le gabarit pour chaque nouvelle étape (Step 0.1, Step 0.2, Step 1.1, ...), en s'alignant sur les phases de execution_plan.md.

Gabarit (à copier pour chaque nouvelle étape)
Field	Details
Step ID & Name	Step X.Y: <nom court>
Phase	<Setup / Indexing / Resilience / Testing / ...>
Files Modified	<fichiers créés ou modifiés>
Problem	<pourquoi cette étape est nécessaire>
Approach	<décision de conception + tech utilisée>
Result	<critère de sortie visé → résultat obtenu>
Next	<prochaine étape ou limite connue>
Step 0.1: Project Bootstrap
Field	Details
Step ID & Name	Step 0.1: Project Bootstrap
Phase	Setup
Files Modified	pipeline/config.py, core/db.py, docker-compose.yml, migrations/versions/0001_init.py
Problem	Pas de squelette exécutable — impossible de tester une stage sans config ni connexion DB partagées.
Approach	PipelineConfig (Pydantic) comme source unique de config ; engine SQLAlchemy avec pool de connexions ; migration 0 = activation de l'extension vector.
Result	Visé : docker-compose up démarre Postgres+pgvector, pipeline db upgrade passe sans erreur. Obtenu : (à renseigner)
Next	Détection des changements filesystem (Step 1.1 — Phase 1 de execution_plan.md).  to docs/PROGRESS.md